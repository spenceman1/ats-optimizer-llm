from pathlib import Path
from structured_output import StructuredOutput  # Your Pydantic model
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq


class LLMAgent:
    def __init__(self, api_key_path: str, model_name: str = "llama-3.3-70b-versatile"):
        self.API_KEY = Path(api_key_path).read_text()
        self.model_name = model_name
        self.llm = self._initialize_llm()
        self.parser = JsonOutputParser(pydantic_object=StructuredOutput)
        self.chain = self._build_chain()

    def _initialize_llm(self):
        return ChatGroq(
            model=self.model_name,
            temperature=0.25,  # concise, factual output
            api_key=self.API_KEY
        )

    def _build_chain(self):
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            ("user", self._get_user_prompt())
        ])
        return prompt_template.partial(
            format_instructions=self.parser.get_format_instructions()
        ) | self.llm | self.parser

    def _get_system_prompt(self) -> str:
        return """
        You are a professional career assistant.
        Build a factual, concise, structured resume (JSON) based ONLY on the provided documents.
        Use resume_text and linkedin_text as authoritative sources.
        Do NOT invent any information. If a field is missing, leave it empty.
        Include all relevant roles, bullets, education, certifications, and contacts.
        """

    def _get_user_prompt(self) -> str:
        return """
        Here are the verified documents:

        RESUME TEXT:
        {resume_text}

        LINKEDIN TEXT:
        {linkedin_text}

        JOB DESCRIPTION:
        {job_description}

        Generate a structured JSON resume matching this schema: {format_instructions}

        Requirements:
        - Use resume_text and linkedin_text to fill all fields: name, contacts, experience, education, skills, certifications
        - Produce 1-5 concise bullets per role emphasizing accomplishments and outcomes
        - Include all contact links present in the source (LinkedIn, website, GitHub)
        - Keep the resume concise, one-page style
        - Do NOT invent names, dates, companies, or bullets not present in the source
        """

    def generate_cv(
        self,
        resume_text: str,
        linkedin_text: str,
        job_description: str
    ) -> StructuredOutput:
        """
        Returns a structured CV object based on PDF resume and LinkedIn exports.
        """
        llm_input = {
            "resume_text": resume_text,
            "linkedin_text": linkedin_text,
            "job_description": job_description,
            "format_instructions": self.parser.get_format_instructions()
        }

        # The LLM produces all structured fields directly
        final_cv = self.chain.invoke(llm_input)

        return final_cv


# -----------------------
# AGENT CLASS FOR CHATBOT
# -----------------------

class LLM_Chat:
    def __init__(self, api_key_path: str):
        self.API_KEY = Path(api_key_path).read_text()
        self.llm = self._initialize_llm()

    def _initialize_llm(self):
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            api_key=self.API_KEY
        )

    def get_chat_answer(self, final_text_prompt: list) -> list:
        """
        Accepts a list of messages [{role, content}], builds a prompt chain, and returns LLM response.
        """
        prompt = ChatPromptTemplate.from_messages(final_text_prompt)
        chain = prompt | self.llm | StrOutputParser()
        return chain.invoke({})
