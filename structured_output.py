from pydantic import BaseModel, Field
from typing import List, Optional


class Experience(BaseModel):
    role: str
    company: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    achievements: List[str] = Field(default_factory=list)


class Project(BaseModel):
    role: str
    organization: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    achievements: List[str] = Field(default_factory=list)


class Education(BaseModel):
    degree: Optional[str] = None
    major: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[str] = None
    location: Optional[str] = None
    achievements: Optional[str] = None


class Course(BaseModel):
    course: str
    institution: Optional[str] = None
    graduation_year: Optional[str] = None


class StructuredOutput(BaseModel):
    # Required: name is required because we want at least a placeholder name
    name: str = "Unknown Name"

    # Optional contact fields must have defaults (None) to avoid Pydantic "required" errors
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None

    summary: Optional[str] = None
    experience: List[Experience] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    skills: List = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    courses: List[Course] = Field(default_factory=list)
    certifications: List = Field(default_factory=list)


def map_input_to_structured_output(parsed_data: dict) -> StructuredOutput:
    """
    Map a generic parsed dict (from the LLM or extraction) into StructuredOutput.
    Accepts dicts where lists may already be present or missing.
    """

    def safe_list(x):
        if x is None:
            return []
        if isinstance(x, list):
            return x
        # try to coerce a single item into list
        return [x]

    experience = []
    for exp in safe_list(parsed_data.get("experience", [])):
        if isinstance(exp, dict):
            experience.append(
                Experience(
                    role=exp.get("role", "") or "",
                    company=exp.get("company", "") or "",
                    start_date=exp.get("start_date"),
                    end_date=exp.get("end_date"),
                    location=exp.get("location"),
                    achievements=exp.get("achievements") or [],
                )
            )

    projects = []
    for proj in safe_list(parsed_data.get("projects", [])):
        if isinstance(proj, dict):
            projects.append(
                Project(
                    role=proj.get("role", "") or "",
                    organization=proj.get("organization", "") or "",
                    start_date=proj.get("start_date"),
                    end_date=proj.get("end_date"),
                    location=proj.get("location"),
                    achievements=proj.get("achievements") or [],
                )
            )

    education = []
    for edu in safe_list(parsed_data.get("education", [])):
        if isinstance(edu, dict):
            education.append(
                Education(
                    degree=edu.get("degree"),
                    major=edu.get("major"),
                    institution=edu.get("institution"),
                    graduation_year=edu.get("graduation_year"),
                    location=edu.get("location"),
                    achievements=edu.get("achievements"),
                )
            )

    structured = StructuredOutput(
        name=parsed_data.get("name") or parsed_data.get("full_name") or "Unknown Name",
        email=parsed_data.get("email"),
        phone=parsed_data.get("phone"),
        linkedin=parsed_data.get("linkedin"),
        website=parsed_data.get("website"),
        github=parsed_data.get("github"),
        summary=parsed_data.get("summary"),
        experience=experience,
        projects=projects,
        skills=parsed_data.get("skills") or [],
        education=education,
        courses=parsed_data.get("courses") or [],
        certifications=parsed_data.get("certifications") or [],
    )
    return structured
