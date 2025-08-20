import os
import pathlib
import json
import re
import streamlit as st
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import weasyprint
import streamlit_ace

# Internal libraries
from file_management import (
    extract_text_from_pdf,
    get_all_users,
    check_user_exists,
    get_user_info,
    create_user,
    create_new_job,
    get_user_jobs,
    save_dict_in_db,
    get_chat_history,
    save_chat_history,
)

from llm_agent import LLMAgent  # LLM wrapper
from llm_agent import LLM_Chat  # Optional chat wrapper

from resume_optimizer import ResumeOptimizer

# -----------------------
# Paths
# -----------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"
API_KEY_FILE = BASE_DIR / "API_KEY.txt"
OUTPUT_DIR.mkdir(exist_ok=True)
(TEMPLATES_DIR / ".keep").touch(exist_ok=True)

# -----------------------
# Jinja environment
# -----------------------
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    extensions=['jinja2.ext.do']   # <-- enable 'do' tag
)
template = env.get_template("cv_template.html")

# -----------------------
# Helpers
# -----------------------
URL_RE = re.compile(r'https?://[^\s)]+', re.IGNORECASE)

def find_links(text: str):
    return list(set(URL_RE.findall(text or "")))

def pick_profile_links(resume_text: str, linkedin_text: str):
    all_text = " ".join([resume_text or "", linkedin_text or ""])
    urls = find_links(all_text)
    linkedin_url = next((u for u in urls if "linkedin.com" in u.lower()), None)
    github_url = next((u for u in urls if "github.com" in u.lower()), None)
    candidates = [u for u in urls if u not in [linkedin_url, github_url]]
    website_url = candidates[0] if candidates else None
    return {"linkedin": linkedin_url, "github": github_url, "website": website_url}

def slim_skills(structured_result):
    skills = structured_result.get("skills") or []
    out = []
    for s in skills:
        if isinstance(s, dict) and "skill" in s:
            out.append(s["skill"])
        elif isinstance(s, str):
            out.append(s)
    seen = set()
    deduped = []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped

def ensure_summary_text(structured_result):
    summary = structured_result.get("summary")
    if isinstance(summary, dict) and "description" in summary:
        return summary["description"]
    if isinstance(summary, str):
        return summary
    return ""

def filter_sections(structured_result, include_flags):
    data = dict(structured_result)
    if not include_flags.get("volunteer", True):
        data["volunteering"] = []
    if not include_flags.get("projects", True):
        data["projects"] = []
    return data

def clean_text_fields(cv_dict):
    """
    Clean up project and volunteering entries:
    - Collapse accidental internal spaces in titles and roles
    - Remove redundant 'Independent Project'
    - Normalize hyphens, dates, and locations
    """
    for proj in cv_dict.get("projects", []):
        if "project_title" in proj and proj["project_title"]:
            title = proj["project_title"]
            # Normalize hyphens and dashes
            title = re.sub(r'\s*[-–—]\s*', '-', title)
            # Collapse multiple spaces
            title = re.sub(r'\s+', ' ', title).strip()
            # Remove spaces inside words but preserve spaces before numbers or capital letters starting a new word
            title = re.sub(r'(?<=[a-z]) (?=[a-z])', '', title)
            proj["project_title"] = title

        # Clean role
        if "role" in proj and proj["role"]:
            proj["role"] = re.sub(r'\s+', ' ', proj["role"]).strip()
        else:
            proj["role"] = ""

        # Clean organization
        if "organization" not in proj or not proj["organization"]:
            # Only fill if role is empty, avoid redundancy
            proj["organization"] = "Independent Project" if not proj["role"] else ""
        else:
            proj["organization"] = re.sub(r'\s+', ' ', proj["organization"]).strip()

        # Clean dates and location
        for key in ["start_date", "end_date", "location"]:
            if key in proj and proj[key]:
                proj[key] = re.sub(r'\s+', ' ', proj[key]).strip()

    for vol in cv_dict.get("volunteering", []):
        if "role" in vol and vol["role"]:
            vol["role"] = re.sub(r'\s+', ' ', vol["role"]).strip()
        if "organization" not in vol or not vol["organization"]:
            vol["organization"] = "Independent Project"
        else:
            vol["organization"] = re.sub(r'\s+', ' ', vol["organization"]).strip()

        # Clean dates and location
        for key in ["start_date", "end_date", "location"]:
            if key in vol and vol[key]:
                vol[key] = re.sub(r'\s+', ' ', vol[key]).strip()

    return cv_dict

def extract_titular_certifications(structured_dict):
    """Extract certifications that should appear after the name"""
    titular_certs = {
        "PMP": ["pmp", "project management professional"],
        "CSM": ["csm", "certified scrum master"],
        "CPA": ["cpa", "certified public accountant"],
        "MBA": ["mba", "master of business administration"],
        "PHR": ["phr", "professional in human resources"],
        "CFA": ["cfa", "chartered financial analyst"],
        "PE": ["pe", "professional engineer"],
        "PMI-ACP": ["pmi-acp", "agile certified practitioner"],
        "CISSP": ["cissp", "certified information systems security professional"],
        "Six Sigma": ["six sigma black belt", "six sigma green belt"]
    }
    
    found_titular = []
    certifications = structured_dict.get("certifications", [])
    
    for cert in certifications:
        cert_text = ""
        if isinstance(cert, dict):
            cert_text = (cert.get("title", "") + " " + cert.get("issuer", "")).lower()
        else:
            cert_text = str(cert).lower()
        
        for abbrev, keywords in titular_certs.items():
            if any(keyword in cert_text for keyword in keywords):
                found_titular.append(abbrev)
                break
    
    return list(set(found_titular))  # Remove duplicates

def format_name_with_certifications(name, certifications):
    """Add certifications after the name"""
    if not certifications:
        return name
    cert_string = ", ".join(certifications)
    return f"{name}, {cert_string}"

def has_relevant_certifications(structured_dict):
    """Check if there are any certifications to display"""
    certifications = structured_dict.get("certifications", [])
    if not certifications:
        return False
    
    # Filter out empty certifications
    valid_certs = []
    for cert in certifications:
        if isinstance(cert, dict):
            if cert.get("title") and cert.get("title").strip():
                valid_certs.append(cert)
        elif isinstance(cert, str) and cert.strip():
            valid_certs.append(cert)
    
    return len(valid_certs) > 0

def render_and_write_pdf(
    structured_result,
    header_location,
    out_dir: pathlib.Path,
    filename_base: str,
    include_projects: bool = True,
    include_volunteer: bool = True,
    resume_text: str = "",
    linkedin_text: str = ""
):
    data = dict(structured_result)
    
    # Extract titular certifications before processing
    titular_certs = extract_titular_certifications(data)
    
    # Update name with certifications
    original_name = data.get("name", "Unknown Name")
    data["name"] = format_name_with_certifications(original_name, titular_certs)
    
    if not include_volunteer:
        data["volunteering"] = []
    if not include_projects:
        data["projects"] = []
    
    data["linkedin"] = data.get("linkedin") or None
    data["github"] = data.get("github") or None
    data["website"] = data.get("website") or None
    data["location"] = header_location or data.get("location")
    
    if "certifications" not in data or data["certifications"] is None:
        data["certifications"] = []

    # Existing certification extraction logic...
    def extract_certifications(text):
        found = []
        if not text:
            return found
        txt = text.lower()
        known = [
            ("Project Management Professional (PMP)", ["pmp", "project management professional"]),
            ("Export Compliance Certification", ["export compliance", "citi program", "citi"]),
            ("Certified Scrum Master (CSM)", ["scrum master", "csm"]),
            ("Lean Six Sigma", ["six sigma", "lean six sigma"]),
            ("Certified Information Systems Security Professional (CISSP)", ["cissp"]),
            ("Professional in Human Resources (PHR)", ["phr"]),
            ("Chartered Financial Analyst (CFA)", ["cfa"])
        ]
        for title, keys in known:
            for k in keys:
                if k in txt and title not in [c if isinstance(c,str) else c.get("title") for c in found]:
                    found.append({"title": title, "issuer": ""})
                    break
        
        # Look for certification patterns in text
        lines = [l.strip(" -•*") for l in re.split(r'[\r\n]+', text) if l.strip()]
        for line in lines:
            low = line.lower()
            if ("cert" in low or "certificate" in low or "certification" in low) and len(line) < 120:
                if not any((isinstance(c,str) and c==line) or (isinstance(c,dict) and c.get("title")==line) for c in found):
                    found.append({"title": line.strip(), "issuer": ""})
        return found

    auto = extract_certifications(resume_text) + extract_certifications(linkedin_text)
    existing_titles = set()
    cleaned = []
    
    for c in data.get("certifications", []) or []:
        t = c.get("title") if isinstance(c, dict) else str(c)
        if t and t.strip() and t not in existing_titles:
            existing_titles.add(t)
            cleaned.append(c)
    
    for ac in auto:
        title = ac.get("title") if isinstance(ac, dict) else ac
        if title and title.strip() and title not in existing_titles:
            cleaned.append(ac)
            existing_titles.add(title)
    
    data["certifications"] = cleaned
    
    # Add flag for template to know if certifications exist
    data["has_certifications"] = has_relevant_certifications(data)

    rendered_html = template.render(structured_result=data)
    out_html = out_dir / f"{filename_base}.html"
    out_pdf = out_dir / f"{filename_base}.pdf"
    out_html.write_text(rendered_html, encoding="utf-8")
    weasyprint.HTML(string=rendered_html).write_pdf(str(out_pdf))
    return out_html, out_pdf

# -----------------------
# Streamlit App
# -----------------------
st.set_page_config(page_title="ATS TAILORING SYSTEM (LLM)", layout="wide")
st.title("ATS TAILORING SYSTEM (LLM)")

# Sidebar: Model & Toggles
st.sidebar.header("Settings")
st.sidebar.subheader("Sections")
include_volunteer = st.sidebar.checkbox("Include Volunteer Experience", value=False)
include_projects = st.sidebar.checkbox("Include Project Experience", value=True)

st.sidebar.subheader("Location")
location_mode = st.sidebar.radio("Header Location", ["Open to relocation", "Specific location"], index=0)
specified_location = ""
if location_mode == "Specific location":
    specified_location = st.sidebar.text_input("Location (e.g., Glendale, CA)", value="")

# API key
api_key_path_input = st.sidebar.text_input("Path to API key file", value=str(API_KEY_FILE))

# Session state initialization
for key in ["user_id","user_name","resume_text","linkedin_text","job_id","selected_job_text","generated_cv","rendered_html","chat_history","website","github"]:
    if key not in st.session_state:
        st.session_state[key] = None if key in ["user_id","job_id","generated_cv","chat_history"] else ""

# -----------------------
# Step 1: User selection/creation
# -----------------------
st.header("1) Choose or Create a User")
all_users = get_all_users()
if all_users:
    df_users = pd.DataFrame(all_users, columns=["User ID","Created"])
    st.dataframe(df_users, hide_index=True, use_container_width=True)
else:
    st.info("No users yet.")

col_uid, col_name = st.columns([1,2])
with col_uid:
    user_id_input = st.text_input("User ID", "")
with col_name:
    user_name_input = st.text_input("User Name", "")

st.subheader("Optional Profile Links")
col_web, col_git = st.columns(2)
with col_web:
    website_input = st.text_input("Website (full URL)", "", key="website_input")
with col_git:
    github_input = st.text_input("GitHub (full URL)", "", key="github_input")

col_a, col_b = st.columns(2)
with col_a:
    if st.button("Use Existing User"):
        try:
            uid = int(user_id_input)
            if check_user_exists(uid):
                st.session_state.user_id = uid
                st.session_state.user_name = user_name_input or f"User {uid}"
                rtxt, ltxt = get_user_info(uid)
                st.session_state.resume_text = rtxt or ""
                st.session_state.linkedin_text = ltxt or ""
                st.session_state.website = website_input
                st.session_state.github = github_input
                st.success(f"Loaded user {uid}.")
            else:
                st.warning("User ID does not exist.")
        except:
            st.error("Enter numeric User ID.")

with col_b:
    resume_pdf = st.file_uploader("Resume PDF", type=["pdf"], key="resume_pdf")
    linkedin_pdf = st.file_uploader("LinkedIn PDF", type=["pdf"], key="linkedin_pdf")
    if st.button("Create New User"):
        try:
            uid = int(user_id_input)
            if not user_name_input.strip():
                st.error("Enter a User Name.")
            elif not (resume_pdf and linkedin_pdf):
                st.error("Upload both PDFs.")
            else:
                created = create_user(uid, user_name_input.strip(), resume_pdf, linkedin_pdf, website_input, github_input)
                if created:
                    st.session_state.user_id = uid
                    st.session_state.user_name = user_name_input.strip()
                    st.session_state.resume_text = extract_text_from_pdf(resume_pdf)
                    st.session_state.linkedin_text = extract_text_from_pdf(linkedin_pdf)
                    st.session_state.website = website_input
                    st.session_state.github = github_input
                    st.success(f"User {uid} created.")
        except Exception as e:
            st.error(f"Error creating user: {e}")

st.divider()

# -----------------------
# Step 2: Job selection/creation
# -----------------------
st.header("2) Select or Create a Job Description")
if not st.session_state.user_id:
    st.info("Select or create a user first."); st.stop()

jobs = get_user_jobs(st.session_state.user_id)
if jobs:
    jobs_df = pd.DataFrame(jobs, columns=["Job ID","Description","Generated CV","Created","Updated"])
    st.dataframe(jobs_df[["Job ID","Description","Created","Updated"]], hide_index=True, use_container_width=True)
    chosen = st.selectbox("Pick existing job",[j[0] for j in jobs], format_func=lambda jid: f"Job {jid}")
    if st.button("Load Job"):
        st.session_state.job_id = chosen
        row = next(j for j in jobs if j[0]==chosen)
        st.session_state.selected_job_text = row[1] or ""
        st.success(f"Loaded job {chosen}.")

st.subheader("Or create a new job")
new_jd = st.text_area("Paste job description", height=180, key="jd_text")
if st.button("Save New Job"):
    if not new_jd.strip():
        st.warning("Paste a job description first.")
    else:
        try:
            jid = create_new_job(st.session_state.user_id,new_jd.strip())
            st.session_state.job_id = jid
            st.session_state.selected_job_text = new_jd.strip()
            st.success(f"Created job {jid}.")
        except Exception as e:
            st.error(f"Error saving job: {e}")

st.divider()

# -----------------------
# Step 3: Generate Tailored Resume
# -----------------------
if st.button("Generate with AI"):
    if not st.session_state.selected_job_text.strip():
        st.warning("Select or create a job first.")
        st.stop()

    # Validate API key
    if not pathlib.Path(API_KEY_FILE).exists():
        st.error(f"API key file not found: {API_KEY_FILE}")
        st.stop()

    # Sidebar toggle for location
    header_location = "Open to relocation"
    if specified_location.strip():
        header_location = specified_location.strip()

    # Initialize agent
    try:
        agent = LLMAgent(api_key_path=str(API_KEY_FILE))
    except Exception as e:
        st.error(f"Failed to initialize AI agent: {e}")
        st.stop()

    # Generate structured resume
    with st.spinner("Generating tailored resume..."):
        try:
            # Enhanced prompt for better job matching
            enhanced_prompt = f"""
            Parse the user's resume and LinkedIn content into structured JSON.
            FOCUS ON: Skills, experiences, and projects most relevant to this job description.
            
            Job Requirements Analysis:
            {st.session_state.selected_job_text}
            
            Instructions:
            - Prioritize experience and skills that match the job requirements
            - Include 'projects' and 'volunteering' sections, even if empty
            - Extract ALL certifications mentioned in the source documents
            - Focus on quantifiable achievements and relevant technical skills
            """

            structured = agent.generate_cv(
                resume_text=st.session_state.resume_text,
                linkedin_text=st.session_state.linkedin_text,
                job_description=enhanced_prompt
            )

            if not structured:
                st.error("AI generation returned no result. Please try again.")
                st.stop()

            # Convert to dict if needed
            if not isinstance(structured, dict):
                if hasattr(structured, "dict"):
                    structured_dict = structured.dict()
                else:
                    st.error("AI output could not be converted to dict.")
                    st.stop()
            else:
                structured_dict = structured

            # Clean text fields
            structured_dict = clean_text_fields(structured_dict)
            
            # Apply resume optimization
            if st.checkbox("🎯 Optimize for Job Relevance & Length", value=True, 
                          help="Automatically optimize resume for the job description and one-page format"):
                optimizer = ResumeOptimizer()
                
                original_skills_count = len(structured_dict.get('skills', []))
                original_projects_count = len(structured_dict.get('projects', []))
                
                # Apply optimization
                structured_dict = optimizer.optimize_resume(
                    structured_dict, 
                    st.session_state.selected_job_text
                )
                
                optimized_skills_count = len(structured_dict.get('skills', []))
                optimized_projects_count = len(structured_dict.get('projects', []))
                
                # Show optimization summary
                st.info(f"""
                ✅ **Optimization Applied:**
                - Skills: Focused on {optimized_skills_count} most relevant (from {original_skills_count})
                - Projects: Showing {optimized_projects_count} most relevant (from {original_projects_count})
                - Achievements: Prioritized based on job requirements
                - Format: Optimized for one-page length
                """)
            
            st.session_state.generated_cv = structured_dict

        except Exception as e:
            st.error(f"Error generating CV: {e}")
            st.info("Check your internet connection, API key, and try again.")
            st.stop()

    # Ensure projects and volunteering keys exist
    structured_dict.setdefault("projects", [])
    structured_dict.setdefault("volunteering", [])

    # PDF generation with improved certification handling
    try:
        out_html, out_pdf = render_and_write_pdf(
            structured_result=structured_dict,
            header_location=header_location,
            out_dir=OUTPUT_DIR,
            filename_base=f"Resume_{st.session_state.user_id}_{st.session_state.job_id}",
            include_projects=include_projects,
            include_volunteer=include_volunteer,
            resume_text=st.session_state.get("resume_text", ""),
            linkedin_text=st.session_state.get("linkedin_text", "")
        )
        st.session_state.rendered_html = out_html.read_text(encoding="utf-8")
        
        # Display generated content preview
        st.success("✅ Resume generated successfully!")
        
        # Show key metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Experience", len(structured_dict.get('experience', [])))
        with col2:
            st.metric("Projects", len(structured_dict.get('projects', [])))
        with col3:
            st.metric("Skills", len(structured_dict.get('skills', [])))
        with col4:
            st.metric("Certifications", len([c for c in structured_dict.get('certifications', []) if c]))
        
        # Show download PDF button
        out_pdf_path = OUTPUT_DIR / f"Resume_{st.session_state.user_id}_{st.session_state.job_id}.pdf"
        if out_pdf_path.exists():
            with open(out_pdf_path, "rb") as f:
                st.download_button(
                    "📥 Download PDF Resume",
                    data=f.read(),
                    file_name=out_pdf_path.name,
                    mime="application/pdf",
                    type="primary"
                )
                
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        st.info("Resume content was generated, but PDF creation failed.")

st.divider()

# -----------------------
# Step 4: Edit & Re-make PDF
# -----------------------
st.header("4) Edit Resume Content")

if st.session_state.generated_cv:
    st.caption("📝 Edit your resume content below. Changes will be applied to the final PDF.")
    
    # Convert structured resume to dict if needed
    structured_dict = st.session_state.generated_cv
    if not isinstance(structured_dict, dict):
        structured_dict = structured_dict.dict()
    
    # Create an editable copy
    if 'edited_resume' not in st.session_state:
        st.session_state.edited_resume = structured_dict.copy()
    
    # Create expandable sections for better organization
    with st.expander("👤 Personal Information & Summary", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.edited_resume['name'] = st.text_input(
                "Full Name", 
                value=st.session_state.edited_resume.get('name', ''),
                help="Your name as it should appear on the resume"
            )
            st.session_state.edited_resume['email'] = st.text_input(
                "Email", 
                value=st.session_state.edited_resume.get('email', '')
            )
            st.session_state.edited_resume['phone'] = st.text_input(
                "Phone", 
                value=st.session_state.edited_resume.get('phone', '')
            )
        
        with col2:
            st.session_state.edited_resume['linkedin'] = st.text_input(
                "LinkedIn URL", 
                value=st.session_state.edited_resume.get('linkedin', '')
            )
            st.session_state.edited_resume['website'] = st.text_input(
                "Website URL", 
                value=st.session_state.edited_resume.get('website', '')
            )
            st.session_state.edited_resume['github'] = st.text_input(
                "GitHub URL", 
                value=st.session_state.edited_resume.get('github', '')
            )
        
        st.session_state.edited_resume['summary'] = st.text_area(
            "Professional Summary",
            value=st.session_state.edited_resume.get('summary', ''),
            height=100,
            help="2-3 sentences highlighting your key qualifications for this role"
        )
    
    with st.expander("💼 Professional Experience", expanded=True):
        experiences = st.session_state.edited_resume.get('experience', [])
        
        # Allow adding/removing experience entries
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("➕ Add Experience"):
                experiences.append({
                    'role': '',
                    'company': '',
                    'start_date': '',
                    'end_date': '',
                    'location': '',
                    'achievements': []
                })
        
        # Edit each experience
        updated_experiences = []
        for i, exp in enumerate(experiences):
            st.markdown(f"**Experience {i+1}**")
            
            # Basic info in columns
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                role = st.text_input(f"Job Title", value=exp.get('role', ''), key=f"exp_role_{i}")
                company = st.text_input(f"Company", value=exp.get('company', ''), key=f"exp_company_{i}")
            
            with col2:
                start_date = st.text_input(f"Start Date", value=exp.get('start_date', ''), key=f"exp_start_{i}")
                end_date = st.text_input(f"End Date", value=exp.get('end_date', ''), key=f"exp_end_{i}")
            
            with col3:
                location = st.text_input(f"Location", value=exp.get('location', ''), key=f"exp_location_{i}")
                # Remove experience button
                if st.button(f"🗑️ Remove", key=f"remove_exp_{i}"):
                    continue  # Skip this experience
            
            # Achievements editor with better UX
            st.markdown("**Key Achievements:**")
            achievements = exp.get('achievements', [])
            
            # Edit each achievement with individual text areas
            updated_achievements = []
            for j, achievement in enumerate(achievements):
                col_a, col_b = st.columns([10, 1])
                with col_a:
                    updated_achievement = st.text_area(
                        f"Achievement {j+1}",
                        value=achievement,
                        height=60,
                        key=f"exp_achievement_{i}_{j}",
                        help="Describe specific results and impact"
                    )
                    if updated_achievement.strip():
                        updated_achievements.append(updated_achievement.strip())
                
                with col_b:
                    if st.button("❌", key=f"remove_achievement_{i}_{j}", help="Remove this achievement"):
                        pass  # Achievement will be skipped
            
            # Add new achievement button
            if st.button(f"➕ Add Achievement", key=f"add_achievement_{i}"):
                achievements.append("")
                st.rerun()
            
            updated_experiences.append({
                'role': role,
                'company': company,
                'start_date': start_date,
                'end_date': end_date,
                'location': location,
                'achievements': updated_achievements
            })
            
            st.divider()
        
        st.session_state.edited_resume['experience'] = updated_experiences
    
    with st.expander("🚀 Projects", expanded=False):
        projects = st.session_state.edited_resume.get('projects', [])
        
        # Add/remove project controls
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("➕ Add Project"):
                projects.append({
                    'project_title': '',
                    'role': '',
                    'organization': '',
                    'start_date': '',
                    'end_date': '',
                    'achievements': []
                })
        
        updated_projects = []
        for i, proj in enumerate(projects):
            st.markdown(f"**Project {i+1}**")
            
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                project_title = st.text_input(f"Project Title", value=proj.get('project_title', ''), key=f"proj_title_{i}")
                role = st.text_input(f"Your Role", value=proj.get('role', ''), key=f"proj_role_{i}")
            
            with col2:
                organization = st.text_input(f"Organization", value=proj.get('organization', ''), key=f"proj_org_{i}")
                start_date = st.text_input(f"Start Date", value=proj.get('start_date', ''), key=f"proj_start_{i}")
            
            with col3:
                end_date = st.text_input(f"End Date", value=proj.get('end_date', ''), key=f"proj_end_{i}")
                if st.button(f"🗑️ Remove", key=f"remove_proj_{i}"):
                    continue
            
            # Project achievements
            st.markdown("**Project Details:**")
            achievements = proj.get('achievements', [])
            updated_achievements = []
            
            for j, achievement in enumerate(achievements):
                col_a, col_b = st.columns([10, 1])
                with col_a:
                    updated_achievement = st.text_area(
                        f"Detail {j+1}",
                        value=achievement,
                        height=50,
                        key=f"proj_achievement_{i}_{j}"
                    )
                    if updated_achievement.strip():
                        updated_achievements.append(updated_achievement.strip())
                
                with col_b:
                    if st.button("❌", key=f"remove_proj_achievement_{i}_{j}"):
                        pass
            
            if st.button(f"➕ Add Detail", key=f"add_proj_achievement_{i}"):
                achievements.append("")
                st.rerun()
            
            updated_projects.append({
                'project_title': project_title,
                'role': role,
                'organization': organization,
                'start_date': start_date,
                'end_date': end_date,
                'achievements': updated_achievements
            })
            
            st.divider()
        
        st.session_state.edited_resume['projects'] = updated_projects
    
    with st.expander("🎯 Skills", expanded=True):
        skills = st.session_state.edited_resume.get('skills', [])
        skills_text = ', '.join([str(s) for s in skills if s])
        
        st.session_state.edited_resume['skills'] = st.text_area(
            "Technical & Professional Skills",
            value=skills_text,
            height=100,
            help="List your most relevant skills for this position, separated by commas"
        ).split(',')
        
        # Clean up skills list
        st.session_state.edited_resume['skills'] = [
            skill.strip() for skill in st.session_state.edited_resume['skills'] 
            if skill.strip()
        ]
    
    with st.expander("🎓 Education & Certifications", expanded=False):
        # Education section
        st.subheader("Education")
        education = st.session_state.edited_resume.get('education', [])
        
        updated_education = []
        for i, edu in enumerate(education):
            st.markdown(f"**Education {i+1}**")
            
            col1, col2 = st.columns(2)
            with col1:
                degree = st.text_input(f"Degree", value=edu.get('degree', ''), key=f"edu_degree_{i}")
                major = st.text_input(f"Major/Field", value=edu.get('major', ''), key=f"edu_major_{i}")
            
            with col2:
                institution = st.text_input(f"Institution", value=edu.get('institution', ''), key=f"edu_inst_{i}")
                year = st.text_input(f"Year", value=edu.get('graduation_year', ''), key=f"edu_year_{i}")
            
            updated_education.append({
                'degree': degree,
                'major': major,
                'institution': institution,
                'graduation_year': year,
                'location': edu.get('location', ''),
                'achievements': edu.get('achievements', '')
            })
            
            st.divider()
        
        st.session_state.edited_resume['education'] = updated_education
        
        # Certifications section
        st.subheader("Certifications")
        certifications = st.session_state.edited_resume.get('certifications', [])
        cert_texts = []
        for cert in certifications:
            if isinstance(cert, dict):
                cert_texts.append(cert.get('title', ''))
            else:
                cert_texts.append(str(cert))
        
        cert_input = st.text_area(
            "Professional Certifications",
            value='\n'.join(cert_texts),
            height=80,
            help="List your certifications, one per line"
        )
        
        # Convert back to list format
        cert_list = [cert.strip() for cert in cert_input.split('\n') if cert.strip()]
        st.session_state.edited_resume['certifications'] = cert_list
    
    # Save and regenerate PDF
    st.divider()
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("💾 Save Changes", type="primary"):
            # Update the main generated_cv with edited version
            st.session_state.generated_cv = st.session_state.edited_resume
            st.success("✅ Changes saved!")
    
    with col2:
        if st.button("🔄 Reset to Original"):
            st.session_state.edited_resume = structured_dict.copy()
            st.rerun()
    
    with col3:
        if st.button("📄 Generate PDF"):
            try:
                # Apply the same location logic
                header_location = "Open to relocation"
                if specified_location.strip():
                    header_location = specified_location.strip()
                
                # Generate PDF with edited content
                out_html, out_pdf = render_and_write_pdf(
                    structured_result=st.session_state.edited_resume,
                    header_location=header_location,
                    out_dir=OUTPUT_DIR,
                    filename_base=f"Resume_{st.session_state.user_id}_{st.session_state.job_id}_edited",
                    include_projects=include_projects,
                    include_volunteer=include_volunteer,
                    resume_text=st.session_state.get("resume_text", ""),
                    linkedin_text=st.session_state.get("linkedin_text", "")
                )
                
                # Update session state with new HTML
                st.session_state.rendered_html = out_html.read_text(encoding="utf-8")
                
                # Provide download
                with open(out_pdf, "rb") as f:
                    st.download_button(
                        "⬇️ Download Edited PDF",
                        data=f.read(),
                        file_name=f"Resume_Edited_{st.session_state.user_id}_{st.session_state.job_id}.pdf",
                        mime="application/pdf"
                    )
                
                st.success("✅ PDF generated with your edits!")
                
            except Exception as e:
                st.error(f"❌ Error generating PDF: {e}")

else:
    st.info("Generate a resume first to enable editing.")

st.divider()

# -----------------------
# Step 5: Chat about this resume
# -----------------------
st.header("5) Chat about this resume")
if st.session_state.job_id:
    if not st.session_state.chat_history:
        st.session_state.chat_history = [{"role":"assistant","content":"Hello! Ask me about tailoring your resume or interview prep."}]

    for msg in st.session_state.chat_history:
        if msg.get("role") in ("user","assistant") and msg.get("content"):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_msg = st.chat_input("Ask for improvements, tailoring tips, or interview prep")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)
        try:
            agent_chat = LLM_Chat(api_key_path=str(API_KEY_FILE))
            prompt_messages = [
                {"role": "system", "content": "You are a professional career assistant. Provide suggestions based on the user's CV."},
                {"role": "user", "content": f"{user_msg}\n\nHere is the current CV:\n{st.session_state.generated_cv}"}
            ]
            assistant_reply = agent_chat.get_chat_answer(prompt_messages)[0].get("content","")
        except Exception:
            assistant_reply = "Got it! (LLMAgent chat is not available.)"

        st.session_state.chat_history.append({"role": "assistant", "content": assistant_reply})
        with st.chat_message("assistant"):
            st.markdown(assistant_reply)

        try:
            save_chat_history(st.session_state.user_id, st.session_state.job_id, st.session_state.chat_history)
        except Exception:
            pass
else:
    st.info("Select or create a job to enable chat.")
