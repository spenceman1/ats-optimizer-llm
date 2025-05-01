# LLM-Powered Resume Optimizer to Beat ATS Filters

Automates resume generation and optimization by analyzing job descriptions, user resumes, and LinkedIn exports. The system uses a modular architecture with Python, PostgreSQL (via Docker), and LangChain with Groq's power and Pydantic's accuracy to produce high-quality, ATS-compliant resume PDFs.

-----------------------------------------
Medium Article with the complete guide and walkthrough:[Link]
-----------------------------------------

-----------------------------------------
Key Sections Covered in the Medium Guide:
-----------------------------------------
Local Setup & UI Flow: Simple, privacy-first Streamlit interface with support for multiple job versions and chat-based interaction.

LLM Integration: Structured resume output via LLaMA 3.3 and LangChain’s Pydantic parsing system.

PDF Rendering: Dynamic Jinja2 HTML template rendered with WeasyPrint.

Database Design: Dockerized PostgreSQL storing users, job inputs, LLM outputs, and chat history.

Future Improvements: Rate limiting, project sections, Ollama summarization for job titles, and ATS scoring features.

-----------------------------------------
TL;DR
-----------------------------------------

An open-source resume tailoring tool that helps candidates pass automated filters and better match job expectations using local workflows, LLMs, and clean design.

For a detailed walkthrough, check out the Medium article linked above.
