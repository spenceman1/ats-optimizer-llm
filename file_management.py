import os
import pathlib
import json
import PyPDF2

BASE_DIR = pathlib.Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(exist_ok=True)
USERS_FILE = DB_DIR / "users.json"
JOBS_FILE = DB_DIR / "jobs.json"

def _load_json(path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# -----------------------
# User management
# -----------------------
def get_all_users():
    data = _load_json(USERS_FILE, {})
    return [(int(uid), u.get("name", "")) for uid, u in data.items()]

def check_user_exists(user_id):
    data = _load_json(USERS_FILE, {})
    return str(user_id) in data

def get_user_info(user_id):
    data = _load_json(USERS_FILE, {})
    user = data.get(str(user_id), {})
    return user.get("resume_text", ""), user.get("linkedin_text", "")

def create_user(user_id, name, resume_pdf_file, linkedin_pdf_file, website="", github=""):
    users = _load_json(USERS_FILE, {})
    uid_str = str(user_id)
    if uid_str in users:
        return False
    resume_text = extract_text_from_pdf(resume_pdf_file)
    linkedin_text = extract_text_from_pdf(linkedin_pdf_file)
    users[uid_str] = {
        "name": name,
        "resume_text": resume_text,
        "linkedin_text": linkedin_text,
        "website": website,
        "github": github
    }
    _save_json(USERS_FILE, users)
    return True

# -----------------------
# Job management
# -----------------------
def get_user_jobs(user_id):
    jobs = _load_json(JOBS_FILE, {})
    return [(int(jid), j.get("description",""), j.get("generated_cv", None), j.get("created",""), j.get("updated",""))
            for jid, j in jobs.items() if str(user_id) == str(j.get("user_id"))]

def create_new_job(user_id, description):
    jobs = _load_json(JOBS_FILE, {})
    new_id = max([int(j) for j in jobs.keys()] + [0]) + 1
    jobs[str(new_id)] = {
        "user_id": user_id,
        "description": description,
        "generated_cv": None,
        "created": "",
        "updated": ""
    }
    _save_json(JOBS_FILE, jobs)
    return new_id

def save_dict_in_db(file_path, data_dict):
    _save_json(file_path, data_dict)

# -----------------------
# Chat history
# -----------------------
def get_chat_history(user_id, job_id):
    path = DB_DIR / f"chat_{user_id}_{job_id}.json"
    return _load_json(path, [])

def save_chat_history(user_id, job_id, history):
    path = DB_DIR / f"chat_{user_id}_{job_id}.json"
    _save_json(path, history)

# -----------------------
# PDF text extraction
# -----------------------
def extract_text_from_pdf(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text