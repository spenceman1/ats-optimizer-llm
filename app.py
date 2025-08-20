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
        ]
        for title, keys in known:
            for k in keys:
                if k in txt and title not in [c if isinstance(c,str) else c.get("title") for c in found]:
                    found.append({"title": title, "issuer": ""})
                    break
        lines = [l.strip(" -•*") for l in re.split(r'[\r\n]+', text) if l.strip()]
        for line in lines:
            low = line.lower()
            if ("cert" in low or "certificate" in low) and len(line) < 120:
                if not any((isinstance(c,str) and c==line) or (isinstance(c,dict) and c.get("title")==line) for c in found):
                    found.append(line)
        return found

    auto = extract_certifications(resume_text) + extract_certifications(linkedin_text)
    existing_titles = set()
    cleaned = []
    for c in data.get("certifications", []) or []:
        t = c.get("title") if isinstance(c, dict) else str(c)
        if t and t not in existing_titles:
            existing_titles.add(t)
            cleaned.append(c)
    for ac in auto:
        title = ac.get("title") if isinstance(ac, dict) else ac
        if title and title not in existing_titles:
            cleaned.append(ac)
            existing_titles.add(title)
    data["certifications"] = cleaned

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
st.header("3) Generate Tailored Resume")

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
            prompt_instructions = """
            Parse the user's resume and LinkedIn content into structured JSON with keys:
            name, email, phone, linkedin, github, website, location, summary,
            experience, projects, volunteering, skills, education, certifications.

            Always include 'projects' and 'volunteering', even if empty.
            """
            job_with_instructions = prompt_instructions + "\n\nJob Description:\n" + st.session_state.selected_job_text

            structured = agent.generate_cv(
                resume_text=st.session_state.resume_text,
                linkedin_text=st.session_state.linkedin_text,
                job_description=job_with_instructions
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

            structured_dict = clean_text_fields(structured_dict)
            st.session_state.generated_cv = structured_dict

        except Exception as e:
            st.error(f"Error generating CV: {e}")
            st.info("Check your internet connection, API key, and try again.")
            st.stop()

    # Ensure projects and volunteering keys exist
    structured_dict.setdefault("projects", [])
    structured_dict.setdefault("volunteering", [])

    # PDF generation
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
        # Show download PDF button
        out_pdf_path = OUTPUT_DIR / f"Resume_{st.session_state.user_id}_{st.session_state.job_id}.pdf"
        if out_pdf_path.exists():
            with open(out_pdf_path, "rb") as f:
                st.download_button(
                    "Download PDF",
                    data=f.read(),
                    file_name=out_pdf_path.name,
                    mime="application/pdf"
                )
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        st.info("Resume content was generated, but PDF creation failed.")

st.divider()

# -----------------------
# Step 4: Edit & Re-make PDF
# -----------------------
st.header("4) Edit & Re-make PDF")
if st.session_state.generated_cv:
    st.caption("Edit the HTML below to tweak sections. Then click Rebuild PDF.")
    st.session_state.rendered_html = streamlit_ace.st_ace(
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
                st.download_button("Download Updated PDF", f.read(), file_name=out_pdf.name, mime="application/pdf")
            st.success("Updated PDF generated.")
        except Exception as e:
            st.error(f"Rebuild failed: {e}")
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
