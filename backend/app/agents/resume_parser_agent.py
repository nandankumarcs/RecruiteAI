"""
Resume Parser Agent.

Handles:
- PDF/DOCX text extraction
- Contact info extraction via regex
- Rich structured parsing with LangChain/OpenAI when available
- Deterministic section-aware fallback parsing for local/test environments
- Normalization so parsed JSON shape remains consistent and robust
"""

from __future__ import annotations

import re
from collections import OrderedDict

from docx import Document
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from app.config import get_settings

settings = get_settings()

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - import guard for constrained envs
    ChatOpenAI = None


PHONE_REGEX = re.compile(
    r"(?:(?:\+?\d{1,3}[\s().-]*)?(?:\d[\s().-]*){10,14})"
)
EMAIL_REGEX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
DATE_RANGE_REGEX = re.compile(
    r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\s*[–-]\s*(?P<end>(?:Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}))",
    re.IGNORECASE,
)

SECTION_ALIASES = OrderedDict(
    {
        "summary": {"summary", "profile", "professional summary"},
        "education": {"education", "academic background"},
        "experience": {
            "experience",
            "work experience",
            "professional experience",
            "internship experience",
        },
        "projects": {"projects", "project experience"},
        "technical_skills": {"technical skills", "skills", "core skills"},
        "certifications": {"certifications", "licenses", "awards"},
    }
)


class ResumeLink(BaseModel):
    model_config = ConfigDict(extra="allow")

    label: str
    value: str


class SkillCategory(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: str
    items: list[str] = Field(default_factory=list)


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    role_title: str = ""
    company_name: str = ""
    title: str = ""
    company: str = ""
    employment_type: str | None = None
    location: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    duration_text: str | None = None
    tasks_performed: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    subtitle: str | None = None
    organization: str | None = None
    technologies: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    institution: str = ""
    degree: str | None = None
    field: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    score: str | None = None


class CertificationEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    issuer: str | None = None
    year: str | None = None


class StructuredResumeData(BaseModel):
    """Structured information extracted from a resume."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "resume.v2"
    candidate_name: str | None = None
    email: str | None = None
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    skill_categories: list[SkillCategory] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    links: list[ResumeLink] = Field(default_factory=list)


class ResumeParserAgent:
    """Parses uploaded resumes into structured candidate data."""

    def __init__(self, enable_llm: bool | None = None):
        self.enable_llm = (
            bool(settings.OPENAI_API_KEY and ChatOpenAI is not None)
            if enable_llm is None
            else enable_llm
        )
        self._structured_llm = None

        if self.enable_llm and ChatOpenAI is not None:
            llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=0,
            )
            self._structured_llm = llm.with_structured_output(StructuredResumeData)

    def extract_text(self, file_path: str, file_type: str) -> str:
        """Extract raw text from a supported resume file."""
        normalized_type = file_type.lower().lstrip(".")
        if normalized_type == "pdf":
            return self.extract_text_from_pdf(file_path)
        if normalized_type == "docx":
            return self.extract_text_from_docx(file_path)
        raise ValueError(f"Unsupported resume file type: {file_type}")

    def extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from a PDF using pypdf."""
        reader = PdfReader(file_path)
        text_parts: list[str] = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            if extracted.strip():
                text_parts.append(extracted.strip())
        return "\n".join(text_parts).strip()

    def extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from a DOCX file using python-docx."""
        document = Document(file_path)
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
        return "\n".join(filter(None, paragraphs)).strip()

    def extract_phone_number(self, raw_text: str) -> str | None:
        """Extract the first reasonable phone number found in resume text."""
        match = PHONE_REGEX.search(raw_text)
        if not match:
            return None

        number = re.sub(r"\s+", " ", match.group(0)).strip(" .-()")
        digits = re.sub(r"\D", "", number)
        if len(digits) < 10:
            return None
        return number

    def extract_email(self, raw_text: str) -> str | None:
        """Extract the first email found in resume text."""
        match = EMAIL_REGEX.search(raw_text)
        return match.group(0) if match else None

    def extract_candidate_name(self, raw_text: str) -> str | None:
        """Best-effort candidate name extraction from the first non-empty line."""
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "@" in stripped or any(char.isdigit() for char in stripped):
                continue
            if len(stripped.split()) <= 5:
                return stripped
        return None

    def extract_links(self, raw_text: str) -> list[ResumeLink]:
        """Best-effort extraction of profile labels/URLs from the resume header."""
        links: list[ResumeLink] = []
        lower_text = raw_text.lower()
        if "linkedin" in lower_text:
            links.append(ResumeLink(label="LinkedIn", value="LinkedIn"))
        if "github" in lower_text:
            links.append(ResumeLink(label="GitHub", value="GitHub"))
        return links

    def _looks_like_project_header(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped or stripped.startswith("•"):
            return False
        if "•" in stripped:
            return False
        if stripped.endswith("."):
            return False
        if ":" in stripped and stripped.lower().split(":", 1)[0] in {
            "languages",
            "ai/ml",
            "generative ai",
            "vector search",
            "backend",
            "tools",
        }:
            return False
        return len(stripped.split()) <= 8

    def _append_project_bullet(
        self, current: ProjectEntry | None, line: str, starts_new_bullet: bool
    ) -> None:
        if current is None:
            return

        cleaned = line.lstrip("•").strip() if starts_new_bullet else line.strip()
        if not cleaned:
            return

        if starts_new_bullet or not current.bullets:
            current.bullets.append(cleaned)
            return

        current.bullets[-1] = f"{current.bullets[-1]} {cleaned}".strip()

    def _clean_lines(self, raw_text: str) -> list[str]:
        cleaned: list[str] = []
        for line in raw_text.splitlines():
            stripped = re.sub(r"\s+", " ", line).strip()
            if stripped:
                cleaned.append(stripped)
        return cleaned

    def _normalize_heading(self, line: str) -> str:
        return line.lower().strip().rstrip(":")

    def _split_sections(self, raw_text: str) -> dict[str, list[str]]:
        lines = self._clean_lines(raw_text)
        sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
        current_section: str | None = None

        for line in lines:
            normalized = self._normalize_heading(line)
            matched_section = next(
                (
                    section_name
                    for section_name, aliases in SECTION_ALIASES.items()
                    if normalized in aliases
                ),
                None,
            )

            if matched_section is not None:
                current_section = matched_section
                continue

            if current_section:
                sections[current_section].append(line)

        return sections

    def _parse_date_range(self, text: str) -> tuple[str | None, str | None, str | None]:
        match = DATE_RANGE_REGEX.search(text)
        if not match:
            return None, None, None
        return match.group("start"), match.group("end"), match.group(0)

    def _parse_summary(self, section_lines: list[str], raw_text: str) -> str:
        if section_lines:
            return " ".join(section_lines).strip()

        for line in self._clean_lines(raw_text):
            if len(line.split()) > 8:
                return line
        return ""

    def _parse_skill_categories(self, section_lines: list[str]) -> list[SkillCategory]:
        categories: list[SkillCategory] = []

        for line in section_lines:
            if ":" not in line:
                continue
            category, items_text = line.split(":", 1)
            items = [
                item.strip()
                for item in re.split(r",|•", items_text)
                if item.strip()
            ]
            if items:
                categories.append(
                    SkillCategory(category=category.strip(), items=items)
                )

        return categories

    def _flatten_skill_categories(
        self, categories: list[SkillCategory], section_lines: list[str]
    ) -> list[str]:
        if categories:
            seen: dict[str, None] = {}
            for category in categories:
                for item in category.items:
                    seen[item] = None
            return list(seen.keys())

        skills: list[str] = []
        for line in section_lines:
            parts = [part.strip() for part in re.split(r",|•", line) if part.strip()]
            skills.extend(parts)
        return skills

    def _parse_education(self, section_lines: list[str]) -> list[EducationEntry]:
        if not section_lines:
            return []

        entries: list[EducationEntry] = []
        index = 0
        while index < len(section_lines):
            line = section_lines[index]
            institution_line = line
            degree_line = section_lines[index + 1] if index + 1 < len(section_lines) else ""

            start_date, end_date, _ = self._parse_date_range(institution_line)
            institution = DATE_RANGE_REGEX.sub("", institution_line).strip(" -–")
            score_match = re.search(
                r"(CGPA:\s*\d+(?:\.\d+)?/\d+(?:\.\d+)?|GPA:\s*\d+(?:\.\d+)?/\d+(?:\.\d+)?)",
                degree_line,
                re.IGNORECASE,
            )
            score = score_match.group(1).strip() if score_match else None

            location = None
            if score_match:
                trailing_after_score = degree_line[score_match.end() :].strip(" -–,")
                if trailing_after_score:
                    location = trailing_after_score
            elif "—" in degree_line:
                trailing_parts = [part.strip() for part in degree_line.split("—") if part.strip()]
                if trailing_parts:
                    location_candidate = trailing_parts[-1]
                    if "CGPA" not in location_candidate.upper() and "GPA" not in location_candidate.upper():
                        location = location_candidate

            degree = degree_line
            if score_match:
                degree = degree_line[: score_match.start()].rstrip(" —–").strip()
            elif "—" in degree_line:
                degree = degree_line.split("—", 1)[0].strip()

            field = None
            field_match = re.search(r"computer science.*", degree_line, re.IGNORECASE)
            if field_match:
                field = field_match.group(0).split("—")[0].strip()

            entries.append(
                EducationEntry(
                    institution=institution or institution_line,
                    degree=degree or None,
                    field=field,
                    location=location,
                    start_date=start_date,
                    end_date=end_date,
                    score=score,
                )
            )
            index += 2

        return entries

    def _parse_experience(self, section_lines: list[str]) -> list[ExperienceEntry]:
        entries: list[ExperienceEntry] = []
        current: ExperienceEntry | None = None

        for line in section_lines:
            if line.lower().startswith("project "):
                if current:
                    entries.append(current)
                    current = None
                continue

            if line.startswith("•"):
                bullet = line.lstrip("•").strip()
                if current:
                    current.bullets.append(bullet)
                continue

            start_date, end_date, duration_text = self._parse_date_range(line)
            if duration_text:
                if current:
                    entries.append(current)

                title_part = DATE_RANGE_REGEX.sub("", line).strip(" -–")
                employment_type = None
                employment_match = re.search(r"\(([^)]+)\)", title_part)
                if employment_match:
                    employment_type = employment_match.group(1).strip()
                    title_part = re.sub(r"\([^)]+\)", "", title_part).strip()

                current = ExperienceEntry(
                    title=title_part,
                    start_date=start_date,
                    end_date=end_date,
                    duration_text=duration_text,
                    employment_type=employment_type,
                )
                continue

            if current and not current.company:
                parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
                if len(parts) >= 2:
                    current.company = parts[0]
                    current.location = parts[-1]
                else:
                    current.company = line.strip()
                continue

            if current:
                if current.bullets:
                    current.bullets[-1] = f"{current.bullets[-1]} {line}".strip()
                else:
                    current.bullets.append(line)

        if current:
            entries.append(current)

        return entries

    def _parse_embedded_projects_from_experience(
        self, section_lines: list[str]
    ) -> list[ProjectEntry]:
        projects: list[ProjectEntry] = []
        current: ProjectEntry | None = None

        for line in section_lines:
            if line.lower().startswith("project "):
                if current:
                    projects.append(current)

                organization = None
                name = line
                if ":" in line:
                    left, right = [part.strip() for part in line.split(":", 1)]
                    organization = left
                    name = right

                current = ProjectEntry(name=name, organization=organization)
                continue

            if line.startswith("•") and current:
                self._append_project_bullet(current, line, starts_new_bullet=True)
                continue

            if current and current.bullets and not self._looks_like_project_header(line):
                self._append_project_bullet(current, line, starts_new_bullet=False)
                continue

            if current and ("•" in line) and not current.technologies:
                current.technologies = [
                    item.strip() for item in line.split("•") if item.strip()
                ]
                continue

        if current:
            projects.append(current)

        return projects

    def _parse_projects(self, section_lines: list[str]) -> list[ProjectEntry]:
        projects: list[ProjectEntry] = []
        current: ProjectEntry | None = None

        for line in section_lines:
            if line.startswith("•"):
                if current:
                    self._append_project_bullet(current, line, starts_new_bullet=True)
                continue

            if "•" in line and current and not current.technologies:
                technologies = [item.strip() for item in line.split("•") if item.strip()]
                current.technologies = technologies
                continue

            if current and current.bullets and not self._looks_like_project_header(line):
                self._append_project_bullet(current, line, starts_new_bullet=False)
                continue

            if current:
                projects.append(current)

            name = line
            subtitle = None
            links: list[str] = []
            if "|" in line:
                name_part, trailing = [part.strip() for part in line.split("|", 1)]
                name = name_part
                links.append(trailing)
            current = ProjectEntry(name=name, subtitle=subtitle, links=links)

        if current:
            projects.append(current)

        return projects

    def _parse_certifications(self, section_lines: list[str]) -> list[CertificationEntry]:
        certifications: list[CertificationEntry] = []
        if not section_lines:
            return certifications

        combined = " ".join(section_lines)
        inline_matches = re.findall(
            r"(?P<name>[^—]+?)\s+[–-]\s+(?P<issuer>[^()—]+?)\s+\((?P<year>\d{4})\)",
            combined,
        )
        if inline_matches:
            return [
                CertificationEntry(
                    name=name.strip(),
                    issuer=issuer.strip(),
                    year=year.strip(),
                )
                for name, issuer, year in inline_matches
            ]

        for line in section_lines:
            match = re.match(
                r"(?P<name>.+?)\s+[–-]\s+(?P<issuer>.+?)(?:\s+\((?P<year>\d{4})\))?$",
                line,
            )
            if match:
                certifications.append(
                    CertificationEntry(
                        name=match.group("name").strip(),
                        issuer=match.group("issuer").strip(),
                        year=match.group("year"),
                    )
                )
            else:
                certifications.append(CertificationEntry(name=line))
        return certifications

    def _normalize_experience_item(self, item: str | dict | ExperienceEntry) -> ExperienceEntry:
        if isinstance(item, ExperienceEntry):
            return self._canonicalize_experience_entry(item)
        if isinstance(item, dict):
            return self._canonicalize_experience_entry(ExperienceEntry(**item))
        return self._canonicalize_experience_entry(
            ExperienceEntry(title=item, bullets=[item], tasks_performed=[item])
        )

    def _canonicalize_experience_entry(self, item: ExperienceEntry) -> ExperienceEntry:
        role_title = item.role_title or item.title
        company_name = item.company_name or item.company
        from_date = item.from_date or item.start_date
        to_date = item.to_date or item.end_date
        tasks_performed = item.tasks_performed or item.bullets

        is_current = item.is_current
        if is_current is None and to_date:
            is_current = to_date.strip().lower() in {"present", "current"}

        duration_text = item.duration_text
        if not duration_text and from_date and to_date:
            duration_text = f"{from_date} – {to_date}"

        return item.model_copy(
            update={
                "role_title": role_title,
                "title": role_title,
                "company_name": company_name,
                "company": company_name,
                "from_date": from_date,
                "start_date": from_date,
                "to_date": to_date,
                "end_date": to_date,
                "is_current": is_current,
                "duration_text": duration_text,
                "tasks_performed": list(tasks_performed),
                "bullets": list(tasks_performed),
            }
        )

    def _normalize_project_item(self, item: str | dict | ProjectEntry) -> ProjectEntry:
        if isinstance(item, ProjectEntry):
            return item
        if isinstance(item, dict):
            return ProjectEntry(**item)
        return ProjectEntry(name=item)

    def _normalize_education_item(self, item: str | dict | EducationEntry) -> EducationEntry:
        if isinstance(item, EducationEntry):
            return item
        if isinstance(item, dict):
            return EducationEntry(**item)
        return EducationEntry(institution=item)

    def _normalize_certification_item(
        self, item: str | dict | CertificationEntry
    ) -> CertificationEntry:
        if isinstance(item, CertificationEntry):
            return item
        if isinstance(item, dict):
            return CertificationEntry(**item)
        return CertificationEntry(name=item)

    def normalize_structured_data(
        self, structured: StructuredResumeData, raw_text: str
    ) -> StructuredResumeData:
        """Normalize LLM or fallback output into one stable JSON contract."""
        skill_categories = [
            category if isinstance(category, SkillCategory) else SkillCategory(**category)
            for category in structured.skill_categories
        ]

        if not skill_categories and structured.skills:
            skill_categories = [SkillCategory(category="General", items=structured.skills)]

        flattened_skills = self._flatten_skill_categories(
            skill_categories,
            [],
        )
        if not flattened_skills:
            flattened_skills = list(OrderedDict.fromkeys(structured.skills))

        return StructuredResumeData(
            schema_version=structured.schema_version or "resume.v2",
            candidate_name=structured.candidate_name or self.extract_candidate_name(raw_text),
            email=structured.email or self.extract_email(raw_text),
            summary=structured.summary.strip(),
            skills=flattened_skills,
            skill_categories=skill_categories,
            experience=[
                self._normalize_experience_item(item) for item in structured.experience
            ],
            projects=[self._normalize_project_item(item) for item in structured.projects],
            education=[
                self._normalize_education_item(item) for item in structured.education
            ],
            certifications=[
                self._normalize_certification_item(item)
                for item in structured.certifications
            ],
            links=[
                ResumeLink(
                    label=(link.label if isinstance(link, ResumeLink) else link["label"]).strip(),
                    value=(
                        (link.value if isinstance(link, ResumeLink) else link["value"]).strip()
                    ),
                )
                for link in structured.links
            ],
        )

    def merge_structured_data(
        self, primary: StructuredResumeData, fallback: StructuredResumeData
    ) -> StructuredResumeData:
        """Use the richer of primary/fallback data while preserving stable structure."""

        def dedupe_strings(items: list[str]) -> list[str]:
            seen: OrderedDict[str, None] = OrderedDict()
            for item in items:
                cleaned = item.strip()
                if cleaned:
                    seen[cleaned] = None
            return list(seen.keys())

        merged_skill_categories = list(primary.skill_categories)
        existing_categories = {category.category for category in merged_skill_categories}
        for category in fallback.skill_categories:
            if category.category not in existing_categories:
                merged_skill_categories.append(category)

        merged_experience = list(primary.experience)
        existing_experience_keys = {
            (
                item.title.strip().lower(),
                (item.start_date or "").strip().lower(),
                (item.end_date or "").strip().lower(),
            )
            for item in merged_experience
        }
        for item in fallback.experience:
            key = (
                item.title.strip().lower(),
                (item.start_date or "").strip().lower(),
                (item.end_date or "").strip().lower(),
            )
            if key not in existing_experience_keys:
                merged_experience.append(item)

        merged_projects = list(primary.projects)
        existing_project_names = {item.name.strip().lower() for item in merged_projects}
        for item in fallback.projects:
            key = item.name.strip().lower()
            if key not in existing_project_names:
                merged_projects.append(item)

        merged_education = list(primary.education)
        existing_education = {item.institution.strip().lower() for item in merged_education}
        for item in fallback.education:
            key = item.institution.strip().lower()
            if key not in existing_education:
                merged_education.append(item)

        merged_certifications = list(primary.certifications)
        existing_certs = {item.name.strip().lower() for item in merged_certifications}
        for item in fallback.certifications:
            key = item.name.strip().lower()
            if key not in existing_certs and not any(
                key in existing or existing in key for existing in existing_certs
            ):
                merged_certifications.append(item)

        merged_links: list[ResumeLink] = []
        links_by_label: dict[str, ResumeLink] = {}
        for item in primary.links + fallback.links:
            label_key = item.label.strip().lower()
            sanitized_value = item.value.strip()
            if (
                sanitized_value.startswith("/")
                or sanitized_value.lower() in {"linkedin", "github"}
                or "github" in sanitized_value.lower()
                or "linkedin" in sanitized_value.lower()
            ):
                sanitized_value = item.label

            if label_key not in links_by_label:
                links_by_label[label_key] = ResumeLink(label=item.label, value=sanitized_value)
        merged_links = list(links_by_label.values())

        for item in merged_experience:
            if not item.duration_text and item.start_date and item.end_date:
                item.duration_text = f"{item.start_date} – {item.end_date}"

        return StructuredResumeData(
            schema_version=primary.schema_version or fallback.schema_version or "resume.v2",
            candidate_name=primary.candidate_name or fallback.candidate_name,
            email=primary.email or fallback.email,
            summary=primary.summary or fallback.summary,
            skills=dedupe_strings(primary.skills + fallback.skills),
            skill_categories=merged_skill_categories,
            experience=merged_experience,
            projects=merged_projects,
            education=merged_education,
            certifications=merged_certifications,
            links=merged_links,
        )

    def fallback_structured_parse(self, raw_text: str) -> StructuredResumeData:
        """Deterministic structured parse used in tests and as a resilience fallback."""
        sections = self._split_sections(raw_text)
        skill_categories = self._parse_skill_categories(sections["technical_skills"])

        structured = StructuredResumeData(
            candidate_name=self.extract_candidate_name(raw_text),
            email=self.extract_email(raw_text),
            summary=self._parse_summary(sections["summary"], raw_text),
            skills=self._flatten_skill_categories(
                skill_categories, sections["technical_skills"]
            ),
            skill_categories=skill_categories,
            experience=self._parse_experience(sections["experience"]),
            projects=self._parse_projects(sections["projects"])
            + self._parse_embedded_projects_from_experience(sections["experience"]),
            education=self._parse_education(sections["education"]),
            certifications=self._parse_certifications(sections["certifications"]),
            links=self.extract_links(raw_text),
        )

        return self.normalize_structured_data(structured, raw_text)

    async def extract_structured_data(self, raw_text: str) -> StructuredResumeData:
        """Use the LLM when available, otherwise fall back to deterministic parsing."""
        fallback = self.fallback_structured_parse(raw_text)
        if self._structured_llm is None:
            return fallback

        prompt = (
            "Extract structured candidate information from the resume text below. "
            "Preserve structure rigorously. "
            "Return: summary, flat skills, categorized skills, structured experience "
            "(role_title/company_name/location/from_date/to_date/employment_type/tasks_performed, "
            "while keeping equivalent title/company/start_date/end_date/bullets fields aligned), structured projects "
            "(name/technologies/bullets/links), education, certifications, and visible links. "
            "Do not omit sections that are present in the resume. "
            "If a field is unknown, leave it empty instead of inventing data.\n\n"
            f"Resume text:\n{raw_text[:16000]}"
        )

        try:
            structured = await self._structured_llm.ainvoke(prompt)
            normalized_primary = self.normalize_structured_data(structured, raw_text)
            return self.merge_structured_data(normalized_primary, fallback)
        except Exception:
            return fallback

    async def parse_resume(self, file_path: str, file_type: str) -> dict:
        """Parse a saved resume file into API-ready fields."""
        raw_text = self.extract_text(file_path, file_type)
        structured = self.normalize_structured_data(
            await self.extract_structured_data(raw_text),
            raw_text,
        )
        phone_number = self.extract_phone_number(raw_text)
        email = structured.email or self.extract_email(raw_text)
        candidate_name = structured.candidate_name or self.extract_candidate_name(raw_text)

        return {
            "candidate_name": candidate_name,
            "phone_number": phone_number,
            "email": email,
            "raw_text": raw_text,
            "parsed_data": {
                "schema_version": structured.schema_version,
                "summary": structured.summary,
                "skills": structured.skills,
                "skill_categories": [category.model_dump() for category in structured.skill_categories],
                "experience": [item.model_dump() for item in structured.experience],
                "projects": [item.model_dump() for item in structured.projects],
                "education": [item.model_dump() for item in structured.education],
                "certifications": [
                    item.model_dump() for item in structured.certifications
                ],
                "links": [item.model_dump() for item in structured.links],
            },
        }


def get_resume_parser_agent() -> ResumeParserAgent:
    """Dependency factory for the resume parser agent."""
    return ResumeParserAgent()
