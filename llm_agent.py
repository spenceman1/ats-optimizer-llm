from pydantic import BaseModel, Field, EmailStr, HttpUrl
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from typing import List, Optional

# -----------------------
# Pydantic Models
# -----------------------

class Summary(BaseModel):
    description: str = Field(description= "A professional summary highlighting the candidate's years of experience, core skills, and unique value proposition. "
                   "Focus on technical expertise. "
                   "Keep it concise (1-2 sentences), use strong action verbs, and align with the job description's keywords.",
    min_length = 50,
    max_length = 200
    )

class ProfessionalExperience(BaseModel):
    role: str = Field(description= "Job title (e.g., 'Senior Data Engineer', 'Analytics Engineer')."
                   "Use standardized industry titles that match the job description when possible.")
    company: str = Field(description= "Company's name")
    achievements: List[str] = Field(description= "2-4 bullet points highlighting quantifiable results and key responsibilities. "
                   "Each should: "
                   "1) Start with a strong action verb (e.g., 'Designed', 'Led', 'Increased') "
                   "2) Include metrics/impact where possible (e.g., 'improved efficiency by 40%')",)
    start_date: str = Field(description="Start date in format: 'MMM. YYYY' (e.g., 'Jan. 2020'). Use consistent formatting throughout the resume.")
    end_date: str = Field(description="End date in format: 'MMM. YYYY' (e.g., 'Dec. 2022') or 'Present' for current roles.")
    sector: Optional[str] = Field(description="Company's niche, industry sector using standardized terms: (eg., Pharma, Retail, E-commerce, Data Platform, Cloud provider, Finance"
                                  "Align with the target job's industry when relevant.")
    location: Optional[str] = Field(None, description="Location country of the company or role (e.g., Brazil, USA, Spain)")

class Education(BaseModel):
    degree: str = Field(description= "The degree obtained (e.g., Bachelor of Science in Computer Engineering)")
    institution: str = Field(description= "Official name of the university or institution that awarded the degree (e.g., Universidade Federal de São Paulo")
    achievements: Optional[str]
    graduation_year: Optional[str] = Field(None, description="Graduation year in the format: Year (e.g., 2022)")
    location: Optional[str] = None

class Courses(BaseModel):
    course: str = Field(description= "The certification obtained or course (e.g., Advanced PySpark for Data Engineers)")
    institution: str = Field(description= "Official name of the organization or company that awarded the(e.g., IBM, Snowflake, Azure")
    graduation_year: Optional[str]

# OBSERVATION > class Projects(BaseModel)
# I don't recommend using it, if you choose to use it, remember to:
# 1. improve your PDF extractions to collect links (actually this doesn't happen)
# 2. test and validate the links until you get solid ones
# 3. adapt your cv_template.html as well (script on doc)
# 4. uncomment StructuredOutput class definition for projects
# -----------------------------------------------------------------------------------
#class Projects(BaseModel):
#    project: str = Field(description= "The project description")
#    link: Optional[HttpUrl] = Field(None, description="Provided URL of the project")

class Skills(BaseModel):
    skill: str = Field(description= "Standardized name of the technical skill or tool. "
                   "Use industry-standard terms that match the job description. "
                   "Examples: "
                   "- 'Python' (not 'Python programming') "
                   "- 'Google Cloud Platform (GCP)' "
                   "- 'Data Visualization'")
    description: str = Field(description= "Detailed description including: "
                   "1) Years of experience (if 1+ years) "
                   "2) Key technologies/libraries within the skill "
                   "3) 2-3 concrete applications or achievements",
        min_length=50,
        max_length=200)

class Volunteering(BaseModel):
    role: str = Field(description= "Relevant Volunteering experience based on the Job Description")
    organization: str = Field(description= "Full name of the organization + cause focus.")
    achievements: List[str] = Field(description= "2-3 bullet points showcasing measurable impact and relevant skills.")
    start_date: str = Field(description="Start date in format: 'MMM. YYYY' (e.g., 'Jan. 2020')")
    end_date: str = Field(description="End date in format: 'MMM. YYYY' (e.g., 'Dec. 2022') or 'Present' for current roles.")
    location: Optional[str] = Field(None, description="Location country of the company or role (e.g., Brazil, USA, Spain)")

# COMPLETE OUTPUT STRUCTURE CLASS
class StructuredOutput(BaseModel):
    name: str = Field(description= "Full name")
    email: EmailStr = Field(description= "Email address")
    phone: str = Field(description="Phone number in the format +XX XXXXX XXXX")
    linkedin: Optional[HttpUrl] = Field(None, description="LinkedIn profile URL")
    github: Optional[HttpUrl] = Field(None, description="GitHub profile URL")

    summary: Summary
    skills: List[Skills]
    experience: List[ProfessionalExperience]
    education: List[Education]
#   projects: List[Projects]
    courses: List[Courses]
    volunteering: List[Volunteering]

# ------------------------------------
# AGENT CLASS FOR RESUME OPTIMIZATION
# ------------------------------------

class LLMAgent:
    def __init__(self, api_key_path: str):
        self.API_KEY = open(api_key_path).read()
        self.llm = self._initialize_llm()
        self.parser = JsonOutputParser(pydantic_object=StructuredOutput)  # Uses your existing StructuredOutput
        self.chain = self._build_chain()

    def _initialize_llm(self):
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.5,
            api_key=self.API_KEY
        )

    # BUILDING CHAIN STRUCTURE [ PROMPT (system+user) | LLM (GROQ OBJECT) | PARSER (STRUCTURED OUTPUT) ]
    def _build_chain(self):
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            ("user", self._get_user_prompt())
        ])
        return prompt_template.partial(
            format_instructions=self.parser.get_format_instructions()
        ) | self.llm | self.parser

    def _get_system_prompt(self):
        return """"
        You are a professional career assistant helping me prepare for job applications.
        I will provide my personal documents (Resume and LinkedIn Export).
        Your task is to build a complete and well-structured Professional Profile Configuration based on the provided documents.

        Write in a neutral, professional tone. Do not invent any information that is not found in the reference documents.
        The user name is: {user}.
        
        --- Resume Export ---
        {resume_text}
        
        --- Linkedin Export ---
        {linkedin_text}
        """

    def _get_user_prompt(self):
        return """"
        Please generate An Updated CV Version based on the information provided previously the following outputs based on the provided job description.
        Follow this schema exactly: {format_instructions}
        Ensure that **all experiences** and courses listed in the input are included in the output. **Preserve the full content**, but adjust the wording to 
        better fit the job description by focusing on keywords, descriptions, and required skills. Ensure nothing is omitted. If necessary, prioritize essential 
        information but retain all experiences. Adjust technical jargon, responsibilities, and achievements to align with the role's requirements and the company’s values.
        
        --- JOB DESCRIPTION ---
        {job_description}
        """

    def generate_cv(self, user_name: str, resume_text: str, linkedin_text: str, job_description: str):
        return self.chain.invoke({
            "user": user_name,
            "resume_text": resume_text,
            "linkedin_text": linkedin_text,
            "job_description": job_description
        })

# -----------------------
# AGENT CLASS FOR CHATBOT
# -----------------------

class LLM_Chat:
    def __init__(self, API_KEY_PATH):
        self.API_KEY = open(API_KEY_PATH).read()
        self.llm = self._initialize_llm()

    def _initialize_llm(self):
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.5,
            api_key=self.API_KEY
        )

    def get_chat_answer(self, final_text_prompt: list) -> list:

        prompt = ChatPromptTemplate.from_messages(final_text_prompt)
        chain = prompt | self.llm | StrOutputParser()

        return chain.invoke({})
