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
    name: str = "Unknown Name"
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None

    summary: Optional[str] = None
    experience: List[Experience] = Field(default_factory=list)
    volunteering: List[Project] = Field(default_factory=list)  # Always a list
    projects: List[Project] = Field(default_factory=list)      # Always a list
    skills: List = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    courses: List[Course] = Field(default_factory=list)
    certifications: List = Field(default_factory=list)


def map_input_to_structured_output(parsed_data: dict) -> StructuredOutput:
    """
    Map a generic parsed dict into StructuredOutput.
    Ensures that experience, projects, volunteering, education, skills, etc. always return lists.
    """

    def safe_list(x):
        if x is None:
            return []
        if isinstance(x, list):
            return x
        return [x]

    # Map experiences
    experience = [
        Experience(
            role=exp.get("role",""),
            company=exp.get("company",""),
            start_date=exp.get("start_date"),
            end_date=exp.get("end_date"),
            location=exp.get("location"),
            achievements=safe_list(exp.get("achievements"))
        )
        for exp in safe_list(parsed_data.get("experience"))
        if isinstance(exp, dict)
    ]

    # Map volunteering
    volunteering = [
        Project(
            role=vol.get("role",""),
            organization=vol.get("organization",""),
            start_date=vol.get("start_date"),
            end_date=vol.get("end_date"),
            location=vol.get("location"),
            achievements=safe_list(vol.get("achievements"))
        )
        for vol in safe_list(parsed_data.get("volunteering"))
        if isinstance(vol, dict)
    ]

    # Map projects
    projects = [
        Project(
            role=proj.get("role",""),
            organization=proj.get("organization",""),
            start_date=proj.get("start_date"),
            end_date=proj.get("end_date"),
            location=proj.get("location"),
            achievements=safe_list(proj.get("achievements"))
        )
        for proj in safe_list(parsed_data.get("projects"))
        if isinstance(proj, dict)
    ]

    # Map education
    education = [
        Education(
            degree=edu.get("degree"),
            major=edu.get("major"),
            institution=edu.get("institution"),
            graduation_year=edu.get("graduation_year"),
            location=edu.get("location"),
            achievements=edu.get("achievements"),
        )
        for edu in safe_list(parsed_data.get("education"))
        if isinstance(edu, dict)
    ]

    # Build StructuredOutput
    structured = StructuredOutput(
        name=parsed_data.get("name") or parsed_data.get("full_name") or "Unknown Name",
        email=parsed_data.get("email"),
        phone=parsed_data.get("phone"),
        linkedin=parsed_data.get("linkedin"),
        website=parsed_data.get("website"),
        github=parsed_data.get("github"),
        summary=parsed_data.get("summary"),
        experience=experience,
        volunteering=volunteering,  # Guaranteed list
        projects=projects,          # Guaranteed list
        skills=safe_list(parsed_data.get("skills")),
        education=education,
        courses=safe_list(parsed_data.get("courses")),
        certifications=safe_list(parsed_data.get("certifications")),
    )
    return structured
