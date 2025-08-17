import psycopg2
import fitz  # PyMuPDF
import json
import os
import pathlib
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# --- BASE PATHS ---
BASE_DIR = pathlib.Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "templates"
API_KEY_PATH = BASE_DIR / "API_KEY.txt"

OUTPUT_DIR.mkdir(exist_ok=True)

# --- DATABASE CONNECTION ---
DB_PASSWORD = os.getenv("ATS_DB_PASSWORD")
DB_HOST = "localhost"
DB_PORT = "5433"
DB_NAME = "ats_optimizer"
DB_USER = "ats_user"

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

# --- PDF TEXT EXTRACTION ---
def extract_text_from_pdf(uploaded_file):
    uploaded_file.seek(0)
    try:
        file_bytes = uploaded_file.getvalue()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text.encode("utf-8", errors="replace").decode("utf-8")
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        raise

# --- USER FUNCTIONS ---
def check_user_exists(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE user_id = %s;", (user_name,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0

def get_user_info(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT resume_txt, linkedin_txt
        FROM users
        WHERE user_id = %s;
    """, (user_name,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    resume_txt, linkedin_txt = result
    return resume_txt, linkedin_txt

def get_user_jobs(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT job_id, job_description, generated_cv, created_at, last_modified
        FROM jobs
        WHERE user_id = %s
        ORDER BY last_modified DESC;
    """, (user_name,))
    jobs = cur.fetchall()
    cur.close()
    conn.close()
    return jobs

def get_all_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, created_at FROM users ORDER BY created_at DESC;")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return users
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

def create_new_job(user_name, job_description_text):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO jobs (user_id, job_description)
        VALUES (%s, %s)
        RETURNING job_id;
    """, (user_name, job_description_text))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return new_id

def create_user(user_name, resume_file, linkedin_file):
    resume_text = extract_text_from_pdf(resume_file)
    linkedin_text = extract_text_from_pdf(linkedin_file)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, resume_txt, linkedin_txt)
        VALUES (%s, %s, %s);
    """, (user_name, resume_text, linkedin_text))
    conn.commit()
    cur.close()
    conn.close()
    return True

def save_dict_in_db(user_id, job_id, generated_dict_resume):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE jobs
        SET generated_cv = %s, last_modified = NOW()
        WHERE user_id = %s AND job_id = %s;
    """, (generated_dict_resume, user_id, job_id))
    conn.commit()
    cur.close()
    conn.close()
    return True

# --- CHAT HISTORY FUNCTIONS ---
def get_chat_history(user_id, job_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT chat_history
        FROM jobs
        WHERE user_id = %s AND job_id = %s;
    """, (user_id, job_id))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if result and result[0]:
        try:
            chat_history = json.loads(result[0])
            if isinstance(chat_history, list) and all('role' in m and 'content' in m for m in chat_history):
                return chat_history
        except json.JSONDecodeError:
            pass
    return []

def save_chat_history(user_id, job_id, chat_history):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE jobs
            SET chat_history = %s::jsonb, last_modified = NOW()
            WHERE user_id = %s AND job_id = %s;
        """, (json.dumps(chat_history), user_id, job_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
