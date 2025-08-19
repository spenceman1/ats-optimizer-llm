import os
import pathlib
import json
import re
import streamlit as st
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import weasyprint

# For richer text editor
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

from llm_agent import LLMAgent  # LLM wrapper; must accept model_name and api_key_path

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
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
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
    """Return master resume style skills"""
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

def normalize_url(url):
    return url if url else None

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
    """
    Render the structured CV to HTML and PDF using Jinja2 + WeasyPrint.
    Handles toggles for projects and volunteer sections and auto-fills certifications.
    """
    # shallow copy so we do not mutate the original
    data = dict(structured_result)

    # apply toggles
    if not include_volunteer:
        data["volunteering"] = []
    if not include_projects:
        data["projects"] = []

    # normalize header fields
    data["linkedin"] = data.get("linkedin") or None
    data["github"] = data.get("github") or None
    data["website"] = data.get("website") or None
    data["location"] = header_location or data.get("location")

    # ensure certifications key exists
    if "certifications" not in data or data["certifications"] is None:
        data["certifications"] = []

    # ---- Auto detect common certifications in raw text ----
    def extract_certifications(text):
        found = []
        if not text:
            return found
        txt = text.lower()
        # simple exact/substring checks for common certs
        known = [
            ("Project Management Professional (PMP)", ["pmp", "project management professional"]),
            ("Export Compliance Certification", ["export compliance", "citi program", "citi"]),
            ("Certified Scrum Master (CSM)", ["scrum master", "csm"]),
            ("Lean Six Sigma", ["six sigma", "lean six sigma"]),
        ]
        for title, keys in known:
            for k in keys:
                if k in txt and title not in [c if isinstance(c, str) else c.get("title") for c in found]:
                    found.append({"title": title, "issuer": ""})
                    break

        # fallback: pull short lines that contain "cert" or "certificate"
        lines = [l.strip(" -•*") for l in re.split(r'[\r\n]+', text) if l.strip()]
        for line in lines:
            low = line.lower()
            if ("cert" in low or "certificate" in low) and len(line) < 120:
                # avoid adding duplicates
                if not any((isinstance(c, str) and c == line) or (isinstance(c, dict) and c.get("title") == line) for c in found):
                    found.append(line)
        return found

    # merge any auto-detected certs from resume and linkedin text
    auto = []
    auto += extract_certifications(resume_text)
    auto += extract_certifications(linkedin_text)

    # merge into data['certifications'] without duplicates
    existing_titles = set()
    cleaned = []
    for c in data.get("certifications", []) or []:
        if isinstance(c, dict):
            t = c.get("title") or ""
        else:
            t = str(c)
        if t and t not in existing_titles:
            existing_titles.add(t)
            cleaned.append(c)
    # add autodetected if missing
    for ac in auto:
        title = ac.get("title") if isinstance(ac, dict) else ac
        if title and title not in existing_titles:
            cleaned.append(ac)
            existing_titles.add(title)
    data["certifications"] = cleaned

    # Render HTML
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

# Streamlit session state
for key in ["user_id","user_name","resume_text","linkedin_text","job_id","selected_job_text","generated_cv","rendered_html","chat_history"]:
    if key not in st.session_state:
        st.session_state[key] = None if key=="generated_cv" else "" if key=="rendered_html" else []

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
                
                # Store the profile links in session state
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
                created = create_user(uid, user_name_input.strip(), resume_pdf, linkedin_pdf, 
                                   website_input, github_input)  # Pass the URLs
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
st.header("3) Generate Tailored Resume")

if st.button("Generate with AI"):
    if not st.session_state.selected_job_text.strip():
        st.warning("Select or create a job first.")
        st.stop()

    # Validate API key
    try:
        if not pathlib.Path(API_KEY_FILE).exists():
            st.error(f"API key file not found: {API_KEY_FILE}")
            st.stop()
    except Exception as e:
        st.error(f"Error checking API key: {e}")
        st.stop()

    # Sidebar toggle for location
    header_location = "Open to relocation"
    if specified_location.strip():
        header_location = specified_location.strip()

    # Initialize agent with error handling
    try:
        agent = LLMAgent(api_key_path=str(API_KEY_FILE))
    except Exception as e:
        st.error(f"Failed to initialize AI agent: {e}")
        st.stop()

    # Generate structured resume with progress indicator
    with st.spinner("Generating tailored resume..."):
        try:
            structured = agent.generate_cv(
                resume_text=st.session_state.resume_text,
                linkedin_text=st.session_state.linkedin_text,
                job_description=st.session_state.selected_job_text
            )
            st.session_state.generated_cv = structured
            
            # Check if we got an error structure
            if hasattr(structured, 'name') and structured.name.startswith("Error"):
                st.error("AI generation failed. Please try again or check your inputs.")
                st.stop()
                
        except Exception as e:
            st.error(f"Error generating CV: {e}")
            st.info("Please check your internet connection, API key, and try again.")
            st.stop()

    # PDF generation with error handling
    try:
        # Convert to dict if it's a StructuredOutput object
        if not isinstance(structured, dict):
            structured_dict = structured.dict()
        else:
            structured_dict = structured
    except Exception as e:
        st.error(f"Error creating PDF: {e}")
        st.info("The resume was generated but PDF creation failed. You can still view the content below.")
        # Continue to show the resume content even if PDF fails


    # ---- Normalize project & volunteering keys ----
    for proj in structured_dict.get("projects", []):
        if "title" in proj and "role" not in proj:
            proj["role"] = proj.pop("title")
        if "company" in proj and "organization" not in proj:
            proj["organization"] = proj.pop("company")
        if "achievements" not in proj:
            proj["achievements"] = []

    for vol in structured_dict.get("volunteering", []):
        if "title" in vol and "role" not in vol:
            vol["role"] = vol.pop("title")
        if "company" in vol and "organization" not in vol:
            vol["organization"] = vol.pop("company")
        if "achievements" not in vol:
            vol["achievements"] = []

    # ---- Existing clean-up for achievements ----
    for section in ["experience", "projects", "volunteering"]:
        for item in structured_dict.get(section, []) or []:
            item["achievements"] = [a.replace("\n", " ").strip() for a in item.get("achievements", [])]

    # Render HTML for PDF
    out_html, out_pdf = render_and_write_pdf(
        structured_result=structured_dict,
        header_location=header_location,
        out_dir=OUTPUT_DIR,
        filename_base=f"Resume_{st.session_state.user_id}_{st.session_state.job_id}",
        include_projects=include_projects,
        include_volunteer=include_volunteer,
        resume_text=st.session_state.get("resume_text",""),
        linkedin_text=st.session_state.get("linkedin_text","")
    )

    # Save rendered HTML into session state for Step 4 editor
    st.session_state.rendered_html = out_html.read_text(encoding="utf-8")

    # -----------------------
    # Header
    # -----------------------
    links = pick_profile_links(st.session_state.resume_text, st.session_state.linkedin_text)
    linkedin_link = links.get("linkedin")
    github_link = links.get("github")
    website_link = links.get("website")

    st.markdown(f"**{structured_dict.get('name','Unknown Name')}**  ")
    st.markdown(f"Email: {structured_dict.get('email','unknown@example.com')}  ")
    st.markdown(f"Phone: {structured_dict.get('phone','000-000-0000')}  ")
    if linkedin_link:
        st.markdown(f"[LinkedIn]({linkedin_link})  ")
    if github_link:
        st.markdown(f"[GitHub]({github_link})  ")
    elif website_link:
        st.markdown(f"[Website]({website_link})  ")
    st.markdown(f"Location: {header_location}  ")

    # -----------------------
    # Summary
    # -----------------------
    st.markdown("**Summary**")
    summary_text = ensure_summary_text(structured_dict)
    st.markdown(summary_text or "Professional with relevant experience and skills aligned to the target job description.")

    # -----------------------
    # Professional Experience
    # -----------------------
    st.markdown("**Professional Experience**")
    for exp in structured_dict.get("experience", []) or []:
        role = exp.get("role","N/A")
        company = exp.get("company","N/A")
        start_date = exp.get("start_date","")
        end_date = exp.get("end_date","")
        location = exp.get("location","N/A")
        st.markdown(f"**{role}** | {company} | {start_date} - {end_date} | {location}")
        for bullet in exp.get("achievements",[]) or []:
            st.markdown(f"- {bullet}")

    # -----------------------
    # Project Experience
    # -----------------------
    st.markdown("**Project Experience**")
    for proj in structured_dict.get("projects",[]) or []:
        role = proj.get("role","N/A")
        org = proj.get("organization","N/A")
        start_date = proj.get("start_date","")
        end_date = proj.get("end_date","")
        location = proj.get("location","N/A")
        st.markdown(f"**{role}** | {org} | {start_date} - {end_date} | {location}")
        for bullet in proj.get("achievements",[]) or []:
            st.markdown(f"- {bullet}")

    # -----------------------
    # Skills
    # -----------------------
    st.markdown("**Skills**")
    skills_list = slim_skills(structured_dict)

    # Tailor skills to job description
    def tailor_skills_to_job(skills_list, job_description):
        jd_lower = job_description.lower()
        filtered = [s for s in skills_list if s.lower() in jd_lower or True]  # keep all if no match
        return filtered

    skills_list = tailor_skills_to_job(skills_list, st.session_state.selected_job_text)

    if isinstance(skills_list, list):
        st.markdown(", ".join(skills_list))
    elif isinstance(skills_list, dict):
        for category, items in skills_list.items():
            st.markdown(f"**{category}:** {', '.join(items)}")

    # -----------------------
    # Education & Certifications
    # -----------------------
    st.markdown("**Education & Certifications**")
    for edu in structured_dict.get("education",[]) or []:
        degree = edu.get("degree","N/A")
        institution = edu.get("institution","N/A")
        year = edu.get("graduation_year","N/A")
        loc = edu.get("location","N/A")
        st.markdown(f"**{degree}** | {institution} | {year} | {loc}")
        achievements = edu.get("achievements","")
        if achievements:
            st.markdown(f"- {achievements}")
    for course in structured_dict.get("courses",[]) or []:
        cname = course.get("course","N/A")
        inst = course.get("institution","N/A")
        year = course.get("graduation_year","N/A")
        st.markdown(f"{cname} | {inst} | {year}")

    # Show download PDF button
    out_pdf = OUTPUT_DIR / f"Resume_{st.session_state.user_id}_{st.session_state.job_id}.pdf"
    if out_pdf.exists():
        with open(out_pdf,"rb") as f:
            st.download_button(
                "Download PDF",
                data=f.read(),
                file_name=out_pdf.name,
                mime="application/pdf"
            )

# -----------------------
# Step 4: Edit & Re-make PDF
# -----------------------
st.header("4) Edit & Re-make PDF")

if st.session_state.generated_cv:
    st.caption(
        "Edit the HTML below to make small tweaks or remove sections (e.g., certifications). "
        "Then click Rebuild PDF."
    )

    # Use ACE editor for a richer editing experience
    import streamlit_ace as st_ace

    # Load the latest rendered HTML if available
    html_to_edit = st.session_state.rendered_html
    if not html_to_edit and st.session_state.generated_cv:
        # Use latest HTML from PDF render
        filename_base = f"Resume_{st.session_state.user_id}_{st.session_state.job_id}"
        out_html = OUTPUT_DIR / f"{filename_base}.html"
        if out_html.exists():
            html_to_edit = out_html.read_text(encoding="utf-8")
        st.session_state.rendered_html = html_to_edit

    # ACE editor
    st.session_state.rendered_html = st_ace.st_ace(
        value=st.session_state.rendered_html,
        language="html",
        theme="chrome",
        height=400,
        key="html_editor"
    )

    if st.button("Rebuild PDF"):
        try:
            filename_base = f"Resume_{st.session_state.user_id}_{st.session_state.job_id}"
            out_pdf = OUTPUT_DIR / f"{filename_base}.pdf"
            weasyprint.HTML(string=st.session_state.rendered_html).write_pdf(str(out_pdf))

            with open(out_pdf, "rb") as f:
                st.download_button(
                    "Download Updated PDF",
                    data=f.read(),
                    file_name=out_pdf.name,
                    mime="application/pdf"
                )
            st.success("Updated PDF generated.")
        except Exception as e:
            st.error(f"Rebuild failed: {e}")
else:
    st.info("Generate a resume first to enable editing.")

# -----------------------
# Step 5: Chat about this resume
# -----------------------
st.header("5) Chat about this resume")

if st.session_state.job_id:
    # Load chat history from DB if empty
    if not st.session_state.chat_history:
        st.session_state.chat_history = [{"role":"assistant","content":"Hello! Ask me about tailoring your resume or interview prep."}]

    # Display chat messages
    for msg in st.session_state.chat_history:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Chat input
    user_msg = st.chat_input("Ask for improvements, tailoring tips, or interview prep")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        # Generate assistant response using LLMAgent chat if available
        try:
            agent_chat = LLM_Chat(api_key_path=str(API_KEY_FILE))
            # Example prompt: include user's message and current CV content
            prompt_messages = [
                {"role": "system", "content": "You are a professional career assistant. Provide suggestions based on the user's CV."},
                {"role": "user", "content": f"{user_msg}\n\nHere is the current CV:\n{st.session_state.generated_cv}"}
            ]
            assistant_reply = agent_chat.get_chat_answer(prompt_messages)[0].get("content", "")
        except Exception:
            # Fallback if chat agent fails
            assistant_reply = "Got it! (LLMAgent chat is not available.)"

        st.session_state.chat_history.append({"role": "assistant", "content": assistant_reply})
        with st.chat_message("assistant"):
            st.markdown(assistant_reply)

        # Save chat history to DB
        try:
            save_chat_history(st.session_state.user_id, st.session_state.job_id, st.session_state.chat_history)
        except Exception:
            pass
else:
    st.info("Select or create a job to enable chat.")
