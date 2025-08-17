import streamlit as st
import os, time, pathlib, json
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import weasyprint

# INTERNAL LIBRARIES
from file_management import *
from state_machine import ResumeOptimizerStateMachine
from llm_agent import *

# Add the path to the GTK3 bin folder -> required to run weasyprint
os.add_dll_directory(r"C:\Program Files\GTK3-Runtime Win64\bin")

# Initializing the state machine
if "machine" not in st.session_state:
    st.session_state.machine = ResumeOptimizerStateMachine()

st.title("ATS TAILORING SYSTEM (LLM)")

machine = st.session_state.machine

# Create output directory if not exists
output_path = pathlib.Path("output")
output_path.mkdir(exist_ok=True)
(output_path/".gitkeep").touch(exist_ok=True)

# --- GLOBAL VARIABLES USED FOR PDF GENERATION ----------
output_dir = pathlib.Path("output")   # relative path
template_dir = pathlib.Path("templates")   # relative path

# SETTING UP JINJA2 ENVIRONMENT
env = Environment(loader=FileSystemLoader(template_dir))
template = env.get_template('cv_template.html')  # Custom-made HTML template

# --- CONTROL STATE INITIALIZATIONS ---
session_vars = [
    "user_checked", "user_exists", "user_confirmed",
    "user_name", "job_id", "resume_text", "linkedin_text",
    "generated_cv", "chat_history"
]

for var in session_vars:
    if var not in st.session_state:
        if var == "chat_history":
            st.session_state[var] = []
        elif "text" in var or "name" in var:
            st.session_state[var] = None
        else:
            st.session_state[var] = False

starting_chat_prompt_model = """You are a helpful assistant specialized in career assistance.Your goal is to provide clear,
actionable, and practical advice to help users present themselves at their best,
land interviews, and succeed in their career transitions.
Take the following information as reference for the candidate and opportunity.

--- Candidate Resume ---
{resume_text}

--- Linkedin Export ---
{linkedin_text}

--- Job Description ---
{job_description}
"""

API_KEY_PATH = pathlib.Path("API_KEY.txt")  # relative path

# ------------------------------------
# APP FUNCTIONS
# ------------------------------------
def display_jobs_with_selection(user_jobs):
    if not user_jobs:
        st.info("No existing jobs found for this user")
        return None

    jobs_df = pd.DataFrame(user_jobs,
                           columns=["ID", "Description", "Generated CV", "Created", "Last Modified"])

    st.dataframe(
        jobs_df,
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "Description": st.column_config.TextColumn(width="large"),
            "Generated CV": st.column_config.JsonColumn(),
            "Created": st.column_config.DatetimeColumn(),
            "Last Modified": st.column_config.DatetimeColumn()
        },
        hide_index=True,
        use_container_width=True
    )

    selected_id = st.selectbox(
        "Select job:",
        options=jobs_df["ID"].tolist(),
        format_func=lambda x: f"Job {x} - {jobs_df[jobs_df['ID'] == x]['Description'].iloc[0][:50]}..."
    )

    if st.button("Confirm Job Selection"):
        return selected_id
    return None

def show_loading_state():
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i in range(100):
        progress_bar.progress(i + 1)
        status_text.text(f"Generating optimized CV... {i + 1}%")
        time.sleep(0.03)

    progress_bar.empty()
    status_text.empty()

# --- STEP 1: USER SELECTION ---
if machine.state == "start":

    user_name = st.text_input("Enter an user name for this configuration:")

    st.subheader("Existing Users")
    all_users = get_all_users()

    if all_users:
        users_df = pd.DataFrame(all_users, columns=["User ID", "Last Modified"])
        users_df["Last Modified"] = pd.to_datetime(users_df["Last Modified"]).dt.strftime('%Y-%m-%d %H:%M')

        st.dataframe(
            users_df,
            column_config={
                "User ID": st.column_config.TextColumn(width="medium"),
                "Last Modified": st.column_config.DatetimeColumn(width="medium")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No existing users found in the database")

    if user_name and not st.session_state.user_checked:
        user_exists = check_user_exists(user_name)
        st.session_state.user_exists = user_exists
        st.session_state.user_checked = True

    if user_name:
        user_exists_count = check_user_exists(user_name) or 0
        if user_exists_count > 0:
            st.warning(f"⚠️ User '{user_name}' already exists. Continuing with existing data?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Yes, continue"):
                    st.session_state.user_name = user_name
                    st.session_state.resume_text, st.session_state.linkedin_text = get_user_info(st.session_state.user_name)
                    st.session_state.user_confirmed = True
                    message = machine.next("select_user")
                    st.success(message)
                    st.rerun()

            with col2:
                if st.button("❌ No, input a new user"):
                    st.session_state.user_checked = False
                    st.session_state.user_exists = False
                    st.rerun()

        else:
            st.info(f"User '{user_name}' selected. Please, input your updated Resume PDF and Linkedin Export PDF to create your profile.")

            resume_pdf = st.file_uploader("Resume PDF", type=["pdf"])
            linkedin_pdf = st.file_uploader("Linkedin Default PDF Export", type=["pdf"])

            if resume_pdf and linkedin_pdf and user_name is not None:
                if st.button("📤 Upload & Continue", type="primary"):
                    try:
                        st.session_state.resume_text = extract_text_from_pdf(resume_pdf)
                        st.session_state.linkedin_text = extract_text_from_pdf(linkedin_pdf)
                        create_user(user_name, resume_pdf, linkedin_pdf)
                        st.session_state.user_name = user_name
                        message = machine.next("select_user")
                        st.success(message)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error creating user: {e}")

# --- STEP 2: JOB SELECTION ---
elif machine.state == "waiting_job_description":

    st.subheader("Select a Job Description for optimization:")
    user_jobs = get_user_jobs(st.session_state.user_name)

    with st.expander("➕ Create New Job", expanded=True):
        new_job_text = st.text_area("Paste job description here:", height=200)
        if st.button("Save New Job"):
            if new_job_text.strip():
                try:
                    job_id = create_new_job(st.session_state.user_name, new_job_text)
                    st.session_state.selected_job_text = new_job_text
                    st.session_state.job_id = job_id
                    message = machine.next("job_description_uploaded")
                    st.success(message)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving job: {e}")
            else:
                st.warning("Please enter a job description")

    st.subheader("Or select a previous Job configuration:")
    selected_id = display_jobs_with_selection(user_jobs)

    if selected_id:
        selected_job = next(job for job in user_jobs if job[0] == selected_id)
        st.session_state.job_id = selected_id
        st.session_state.selected_job_text = selected_job[1]
        message = machine.next("job_description_uploaded")
        st.success(f"Selected Job {selected_id}. {message}")
        st.rerun()

# --- STEP 3: PROCESSING LLM ---
elif machine.state == "processing_llm":
    st.subheader("Processing your data")
    with st.spinner("Initializing AI engine..."):
        time.sleep(1)
        show_loading_state()
        try:
            llm_agent = LLMAgent(API_KEY_PATH)
            result = llm_agent.generate_cv(
                st.session_state.user_name,
                st.session_state.resume_text,
                st.session_state.linkedin_text,
                st.session_state.selected_job_text
            )

            st.session_state.generated_cv = result
            save_dict_in_db(st.session_state.user_name, st.session_state.job_id, json.dumps(result))

            rendered_html = template.render(st.session_state.generated_cv)
            output_html_path = output_dir / 'output_cv.html'
            with open(output_html_path, 'w', encoding="utf-8") as f:
                f.write(rendered_html)

            output_pdf_path = output_dir / f'Resume_{st.session_state.user_name}_{st.session_state.job_id}.PDF'
            weasyprint.HTML(string=rendered_html).write_pdf(output_pdf_path)

            message = machine.next("finished")
            st.success(message)
            st.rerun()

        except Exception as e:
            st.error(f"Generation failed: {str(e)}")
            machine.state = "waiting_job_description"

# --- STEP 4: CHAT & DOWNLOAD ---
elif machine.state == "job_exploration":

    empty_col, button_col = st.columns([0.95, 0.05])
    with button_col:
        if st.button("↩️", help="Return to main menu"):
            st.session_state.clear()
            machine.next("menu")
            st.rerun()

    st.subheader("Download your Tailored Resume & Chat")

    output_pdf_path = output_dir / f'Resume_{st.session_state.user_name}_{st.session_state.job_id}.PDF'
    with open(output_pdf_path, "rb") as pdf_file:
        pdf_data = pdf_file.read()
    st.download_button(
        label="📄 Download Your Tailored Resume (PDF)",
        data=pdf_data,
        file_name=f"Tailored_Resume_{st.session_state.user_name}.pdf",
        mime="application/pdf"
    )

    st.divider()

    st.subheader("💬 Chat with llama-3.3-70b-versatile")

    if not st.session_state.chat_history:
        db_chat_history = get_chat_history(st.session_state.user_name, st.session_state.job_id)
        st.session_state.chat_history = db_chat_history if db_chat_history else [
            {"role": "system", "content": starting_chat_prompt_model.format(
                resume_text=st.session_state.resume_text,
                linkedin_text=st.session_state.linkedin_text,
                job_description=st.session_state.selected_job_text
            )}
        ]

    llm_chat_agent = LLM_Chat(API_KEY_PATH)

    for message in st.session_state.chat_history:
        if message["role"] != "system":
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("How can I help you today?"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        assistant_response = llm_chat_agent.get_chat_answer(final_text_prompt=st.session_state.chat_history)
        st.session_state.chat_history.append({"role": "assistant", "content": assistant_response})

        save_chat_history(
            user_id=st.session_state.user_name,
            job_id=st.session_state.job_id,
            chat_history=json.dumps(st.session_state.chat_history)
        )

        st.rerun()
