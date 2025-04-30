import psycopg2
import fitz  # pymupdf
import json

# Function to connect to the PostgreSQL
# DOCKER SETUP ON: DB/docker-compose.yml
# DB INITIALIZATION ON: DB/db-init/initsql.sql
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",        # Database host
        port="5432",             # Port (default PostgreSQL port)
        dbname="ats_optimizer",  # Database name (from docker-compose)
        user="ats_user",         # Username (from docker-compose)
        password="good_password" # Password (from docker-compose)
    )
    return conn

# Function to extract text from a Streamlit uploaded file object
def extract_text_from_pdf(uploaded_file):
    uploaded_file.seek(0) # Reset pointer to start
    try:
        # Read the file content into memory
        file_bytes = uploaded_file.getvalue()

        # Use PyMuPDF's stream interface
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text.encode("utf-8", errors="replace").decode("utf-8")
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        raise

# Function to check if the user already exists
def check_user_exists(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE user_id = %s;", (user_name,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0

# Function to initialize the txt input variables from the db in the case of user_selection without cache
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

# Function to get a list of jobs for a determined user
def get_user_jobs(user_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT job_id, job_description,generated_cv, created_at, last_modified
        FROM jobs
        WHERE user_id = %s
        ORDER BY last_modified DESC;
    """, (user_name,))
    jobs = cur.fetchall()
    cur.close()
    conn.close()
    return jobs

# Function to get the list of users
def get_all_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, created_at FROM users ORDER BY created_at DESC;")
        users = cur.fetchall()  # Now getting both user_id and created_at
        cur.close()
        conn.close()
        return users
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

# Function to create a new job
def create_new_job(user_name, job_description_text):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO jobs (user_id, job_description)
        VALUES (%s, %s)
        RETURNING job_id;
    """, (user_name, job_description_text))
    new_id = cur.fetchone()[0] # NEW ID CREATED
    conn.commit()
    cur.close()
    conn.close()

    # Return used for GLOBAL st.session_state.job_id
    # job_id is automatically incremented (SERIAL)
    return new_id

# Function to input the files into the right path
def create_user(user_name, resume_file, linkedin_file):

    user_id = user_name
    resume_text = extract_text_from_pdf(resume_file)
    linkedin_text = extract_text_from_pdf(linkedin_file)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (user_id, resume_txt, linkedin_txt)
        VALUES (%s, %s, %s);
        """, (user_id, resume_text, linkedin_text))

    conn.commit()
    cur.close()
    conn.close()
    return True

# Function to register the JSON used to build the HTML and PDFs
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

# Function to retrieve chat history for a job
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
            # Ensure format is a list of dicts with 'role' and 'content'
            if isinstance(chat_history, list) and all('role' in m and 'content' in m for m in chat_history):
                return chat_history
        except json.JSONDecodeError:
            pass

    return []  # Return empty list if no valid history exists

# Function to append chat data to a specific job
def save_chat_history(user_id, job_id, chat_history):
    """Save complete chat history as JSON to database"""
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