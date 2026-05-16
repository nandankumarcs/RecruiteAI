"""Pydantic schemas for resume API responses and update requests."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


# ---------------------------------------------------------------------------
# Update request schemas — mirror the resume.v3 parsed_data shape
# ---------------------------------------------------------------------------

class ResumeLinkUpdate(BaseModel):
    label: str | None = None
    url: str = ""


class ContactUpdate(BaseModel):
    headline: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    other_links: list[ResumeLinkUpdate] = Field(default_factory=list)


class SkillEntryUpdate(BaseModel):
    name: str
    proficiency: str | None = None   # Beginner|Intermediate|Advanced|Expert
    category: str | None = None


class SkillCategoryUpdate(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)


class ExperienceEntryUpdate(BaseModel):
    role_title: str | None = None
    company_name: str | None = None
    company_description: str | None = None
    employment_type: str | None = None
    location: str | None = None
    is_remote: bool = False
    from_date: str | None = None
    to_date: str | None = None
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class EducationEntryUpdate(BaseModel):
    institution: str
    degree_type: str | None = None
    field_of_study: str | None = None
    minor: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    gpa: str | None = None
    honors: str | None = None
    relevant_coursework: list[str] = Field(default_factory=list)
    thesis_title: str | None = None


class ProjectEntryUpdate(BaseModel):
    name: str
    role: str | None = None
    url: str | None = None
    repo_url: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_ongoing: bool = False
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    associated_experience: str | None = None  # reference to experience entry id


class CertificationEntryUpdate(BaseModel):
    name: str
    issuer: str | None = None
    issue_date: str | None = None
    expiration_date: str | None = None
    does_not_expire: bool = False
    credential_id: str | None = None
    credential_url: str | None = None


class LanguageEntryUpdate(BaseModel):
    language: str
    proficiency: str = "Conversational"  # Native|Fluent|Professional|Conversational|Basic
    cefr: str | None = None  # A1|A2|B1|B2|C1|C2


class AwardEntryUpdate(BaseModel):
    title: str
    issuer: str | None = None
    date: str | None = None
    description: str | None = None


class VolunteerEntryUpdate(BaseModel):
    role: str
    organization: str
    cause: str | None = None
    location: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)


class PublicationEntryUpdate(BaseModel):
    title: str
    publisher: str | None = None
    date: str | None = None
    authors: str | None = None
    url: str | None = None
    description: str | None = None


class CourseEntryUpdate(BaseModel):
    name: str
    provider: str | None = None
    completion_date: str | None = None
    credential_url: str | None = None


class CustomSectionItemUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    date: str | None = None
    description: str | None = None
    url: str | None = None


class CustomSectionUpdate(BaseModel):
    id: str  # client-generated uuid for stable keying
    section_title: str
    items: list[CustomSectionItemUpdate] = Field(default_factory=list)


class ParsedDataV3Update(BaseModel):
    """Full replacement of parsed_data on save."""
    contact: ContactUpdate | None = None
    summary: str = ""
    skills: list[SkillEntryUpdate] = Field(default_factory=list)
    skill_categories: list[SkillCategoryUpdate] = Field(default_factory=list)
    experience: list[ExperienceEntryUpdate] = Field(default_factory=list)
    education: list[EducationEntryUpdate] = Field(default_factory=list)
    projects: list[ProjectEntryUpdate] = Field(default_factory=list)
    certifications: list[CertificationEntryUpdate] = Field(default_factory=list)
    languages: list[LanguageEntryUpdate] = Field(default_factory=list)
    awards: list[AwardEntryUpdate] = Field(default_factory=list)
    volunteer: list[VolunteerEntryUpdate] = Field(default_factory=list)
    publications: list[PublicationEntryUpdate] = Field(default_factory=list)
    courses: list[CourseEntryUpdate] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    custom_sections: list[CustomSectionUpdate] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)


class ResumeUpdateRequest(BaseModel):
    """Partial update for a resume — any omitted field is left unchanged."""
    candidate_name: str | None = None
    phone_number: str | None = None
    email: str | None = None
    parsed_data: ParsedDataV3Update | None = None
    recalculate_match: bool = True


class ResumeBaseResponse(BaseModel):
    """Common resume fields returned by the API."""

    id: uuid.UUID
    job_id: uuid.UUID
    candidate_name: str | None
    phone_number: str | None
    email: str | None
    file_path: str
    file_type: str
    status: str
    matching_score: float | None = None
    match_explanation: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResumeResponse(ResumeBaseResponse):
    """List/upload response for resumes."""

    parsed_data: dict | None


class ResumeDetailResponse(ResumeResponse):
    """Detailed resume response including extracted text."""

    raw_text: str | None


class PaginatedResumesResponse(BaseModel):
    items: list[ResumeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
