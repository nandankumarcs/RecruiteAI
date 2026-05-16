/**
 * Zod schemas mirroring the backend's resume.v3 ParsedDataV3Update types.
 * Used by ResumeEdit for react-hook-form validation and TypeScript inference.
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Atoms
// ---------------------------------------------------------------------------

export const urlField = z
  .string()
  .refine((v) => !v || v.startsWith("http") || v.startsWith("mailto:"), {
    message: "Must be a valid URL starting with http(s)",
  })
  .optional()
  .or(z.literal(""));

export const linkSchema = z.object({
  label: z.string().optional(),
  url: urlField ?? z.string(),
});

// ---------------------------------------------------------------------------
// Contact
// ---------------------------------------------------------------------------

export const contactSchema = z.object({
  headline: z.string().optional(),
  location: z.string().optional(),
  linkedin_url: urlField,
  github_url: urlField,
  portfolio_url: urlField,
  other_links: z.array(linkSchema).default([]),
});

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------

export const PROFICIENCY_LEVELS = ["Beginner", "Intermediate", "Advanced", "Expert"] as const;
export type ProficiencyLevel = typeof PROFICIENCY_LEVELS[number];

export const skillEntrySchema = z.object({
  name: z.string().min(1, "Skill name required"),
  proficiency: z.enum(PROFICIENCY_LEVELS).optional(),
  category: z.string().optional(),
});

export const skillCategorySchema = z.object({
  category: z.string().min(1, "Category name required"),
  items: z.array(z.string().min(1)).default([]),
});

// ---------------------------------------------------------------------------
// Languages
// ---------------------------------------------------------------------------

export const LANGUAGE_PROFICIENCY = ["Native", "Fluent", "Professional", "Conversational", "Basic"] as const;
export type LanguageProficiency = typeof LANGUAGE_PROFICIENCY[number];

export const CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;

export const languageSchema = z.object({
  language: z.string().min(1, "Language name required"),
  proficiency: z.enum(LANGUAGE_PROFICIENCY).default("Conversational"),
  cefr: z.enum(CEFR_LEVELS).optional(),
});

// ---------------------------------------------------------------------------
// Experience
// ---------------------------------------------------------------------------

export const EMPLOYMENT_TYPES = [
  "Full-time",
  "Part-time",
  "Contract",
  "Freelance",
  "Internship",
  "Apprenticeship",
  "Seasonal",
] as const;

export const experienceSchema = z.object({
  role_title: z.string().optional(),
  company_name: z.string().optional(),
  company_description: z.string().optional(),
  employment_type: z.enum(EMPLOYMENT_TYPES).optional(),
  location: z.string().optional(),
  is_remote: z.boolean().default(false),
  from_date: z.string().optional(),
  to_date: z.string().optional(),
  is_current: z.boolean().default(false),
  bullets: z.array(z.string()).default([]),
  technologies: z.array(z.string()).default([]),
});

// ---------------------------------------------------------------------------
// Education
// ---------------------------------------------------------------------------

export const DEGREE_TYPES = [
  "High School Diploma",
  "Associate's",
  "Bachelor's",
  "Master's",
  "Ph.D.",
  "MBA",
  "Certificate",
  "Bootcamp",
  "Other",
] as const;

export const educationSchema = z.object({
  institution: z.string().min(1, "Institution required"),
  degree_type: z.enum(DEGREE_TYPES).optional(),
  field_of_study: z.string().optional(),
  minor: z.string().optional(),
  location: z.string().optional(),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  is_current: z.boolean().default(false),
  gpa: z.string().optional(),
  honors: z.string().optional(),
  relevant_coursework: z.array(z.string()).default([]),
  thesis_title: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export const projectSchema = z.object({
  name: z.string().min(1, "Project name required"),
  role: z.string().optional(),
  url: urlField,
  repo_url: urlField,
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  is_ongoing: z.boolean().default(false),
  bullets: z.array(z.string()).default([]),
  technologies: z.array(z.string()).default([]),
  associated_experience: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Certifications
// ---------------------------------------------------------------------------

export const certificationSchema = z.object({
  name: z.string().min(1, "Certification name required"),
  issuer: z.string().optional(),
  issue_date: z.string().optional(),
  expiration_date: z.string().optional(),
  does_not_expire: z.boolean().default(false),
  credential_id: z.string().optional(),
  credential_url: urlField,
});

// ---------------------------------------------------------------------------
// Awards
// ---------------------------------------------------------------------------

export const awardSchema = z.object({
  title: z.string().min(1, "Award title required"),
  issuer: z.string().optional(),
  date: z.string().optional(),
  description: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Volunteer
// ---------------------------------------------------------------------------

export const volunteerSchema = z.object({
  role: z.string().min(1, "Role required"),
  organization: z.string().min(1, "Organization required"),
  cause: z.string().optional(),
  location: z.string().optional(),
  from_date: z.string().optional(),
  to_date: z.string().optional(),
  is_current: z.boolean().default(false),
  bullets: z.array(z.string()).default([]),
});

// ---------------------------------------------------------------------------
// Publications
// ---------------------------------------------------------------------------

export const publicationSchema = z.object({
  title: z.string().min(1, "Publication title required"),
  publisher: z.string().optional(),
  date: z.string().optional(),
  authors: z.string().optional(),
  url: urlField,
  description: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Courses
// ---------------------------------------------------------------------------

export const courseSchema = z.object({
  name: z.string().min(1, "Course name required"),
  provider: z.string().optional(),
  completion_date: z.string().optional(),
  credential_url: urlField,
});

// ---------------------------------------------------------------------------
// Custom sections
// ---------------------------------------------------------------------------

export const customSectionItemSchema = z.object({
  title: z.string().optional(),
  subtitle: z.string().optional(),
  date: z.string().optional(),
  description: z.string().optional(),
  url: urlField,
});

export const customSectionSchema = z.object({
  id: z.string(),
  section_title: z.string().min(1, "Section title required"),
  items: z.array(customSectionItemSchema).default([]),
});

// ---------------------------------------------------------------------------
// Root parsed_data schema
// ---------------------------------------------------------------------------

export const parsedDataSchema = z.object({
  contact: contactSchema.optional(),
  summary: z.string().default(""),
  skills: z.array(skillEntrySchema).default([]),
  skill_categories: z.array(skillCategorySchema).default([]),
  experience: z.array(experienceSchema).default([]),
  education: z.array(educationSchema).default([]),
  projects: z.array(projectSchema).default([]),
  certifications: z.array(certificationSchema).default([]),
  languages: z.array(languageSchema).default([]),
  awards: z.array(awardSchema).default([]),
  volunteer: z.array(volunteerSchema).default([]),
  publications: z.array(publicationSchema).default([]),
  courses: z.array(courseSchema).default([]),
  interests: z.array(z.string()).default([]),
  custom_sections: z.array(customSectionSchema).default([]),
  section_order: z.array(z.string()).default([]),
});

export const resumeUpdateSchema = z.object({
  candidate_name: z.string().optional(),
  phone_number: z.string().optional(),
  email: z.string().email("Invalid email").or(z.literal("")).optional(),
  parsed_data: parsedDataSchema,
  recalculate_match: z.boolean().default(true),
});

// ---------------------------------------------------------------------------
// Inferred types
// ---------------------------------------------------------------------------

export type ResumeUpdate = z.infer<typeof resumeUpdateSchema>;
export type ParsedData = z.infer<typeof parsedDataSchema>;
export type ContactData = z.infer<typeof contactSchema>;
export type SkillEntry = z.infer<typeof skillEntrySchema>;
export type ExperienceEntry = z.infer<typeof experienceSchema>;
export type EducationEntry = z.infer<typeof educationSchema>;
export type ProjectEntry = z.infer<typeof projectSchema>;
export type CertificationEntry = z.infer<typeof certificationSchema>;
export type LanguageEntry = z.infer<typeof languageSchema>;
export type AwardEntry = z.infer<typeof awardSchema>;
export type VolunteerEntry = z.infer<typeof volunteerSchema>;
export type PublicationEntry = z.infer<typeof publicationSchema>;
export type CourseEntry = z.infer<typeof courseSchema>;
export type CustomSection = z.infer<typeof customSectionSchema>;
export type CustomSectionItem = z.infer<typeof customSectionItemSchema>;

// ---------------------------------------------------------------------------
// Default empty parsed_data — used when resume has no/null parsed_data
// ---------------------------------------------------------------------------

export const EMPTY_PARSED_DATA: ParsedData = {
  contact: {
    headline: "",
    location: "",
    linkedin_url: "",
    github_url: "",
    portfolio_url: "",
    other_links: [],
  },
  summary: "",
  skills: [],
  skill_categories: [],
  experience: [],
  education: [],
  projects: [],
  certifications: [],
  languages: [],
  awards: [],
  volunteer: [],
  publications: [],
  courses: [],
  interests: [],
  custom_sections: [],
  section_order: [
    "contact",
    "summary",
    "experience",
    "education",
    "skills",
    "languages",
    "projects",
    "certifications",
    "awards",
    "volunteer",
    "publications",
    "courses",
    "interests",
  ],
};

// ---------------------------------------------------------------------------
// Migrate v2 parsed_data to the v3 shape expected by the editor
// ---------------------------------------------------------------------------

export function migrateToV3(raw: Record<string, unknown> | null | undefined): ParsedData {
  if (!raw) return { ...EMPTY_PARSED_DATA };

  // Skills: v2 stored as string[]; v3 stores as {name, proficiency, category}[]
  const rawSkills = (raw.skills as (string | Record<string, unknown>)[] | undefined) ?? [];
  const skills: SkillEntry[] = rawSkills.map((s) =>
    typeof s === "string"
      ? { name: s }
      : { name: String(s.name ?? ""), proficiency: s.proficiency as ProficiencyLevel | undefined, category: s.category as string | undefined }
  );

  // Experience: map legacy aliases to v3 field names
  const rawExp = (raw.experience as Record<string, unknown>[] | undefined) ?? [];
  const experience: ExperienceEntry[] = rawExp.map((e) => ({
    role_title: String(e.role_title ?? e.title ?? ""),
    company_name: String(e.company_name ?? e.company ?? ""),
    company_description: e.company_description as string | undefined,
    employment_type: e.employment_type as ExperienceEntry["employment_type"],
    location: e.location as string | undefined,
    is_remote: Boolean(e.is_remote),
    from_date: (e.from_date ?? e.start_date) as string | undefined,
    to_date: e.is_current ? "Present" : ((e.to_date ?? e.end_date) as string | undefined),
    is_current: Boolean(e.is_current),
    bullets: (e.bullets ?? e.tasks_performed ?? []) as string[],
    technologies: (e.technologies ?? []) as string[],
  }));

  // Education
  const rawEdu = (raw.education as Record<string, unknown>[] | undefined) ?? [];
  const education: EducationEntry[] = rawEdu.map((e) => ({
    institution: String(e.institution ?? ""),
    degree_type: (e.degree_type ?? e.degree) as EducationEntry["degree_type"],
    field_of_study: (e.field_of_study ?? e.field) as string | undefined,
    minor: e.minor as string | undefined,
    location: e.location as string | undefined,
    start_date: e.start_date as string | undefined,
    end_date: e.end_date as string | undefined,
    is_current: Boolean(e.is_current),
    gpa: (e.gpa ?? e.score) as string | undefined,
    honors: e.honors as string | undefined,
    relevant_coursework: (e.relevant_coursework ?? []) as string[],
    thesis_title: e.thesis_title as string | undefined,
  }));

  // Projects
  const rawProj = (raw.projects as Record<string, unknown>[] | undefined) ?? [];
  const projects: ProjectEntry[] = rawProj.map((p) => ({
    name: String(p.name ?? ""),
    role: p.role as string | undefined,
    url: p.url as string | undefined,
    repo_url: p.repo_url as string | undefined,
    start_date: p.start_date as string | undefined,
    end_date: p.end_date as string | undefined,
    is_ongoing: Boolean(p.is_ongoing),
    bullets: (p.bullets ?? []) as string[],
    technologies: (p.technologies ?? []) as string[],
    associated_experience: p.associated_experience as string | undefined,
  }));

  // Certifications
  const rawCert = (raw.certifications as Record<string, unknown>[] | undefined) ?? [];
  const certifications: CertificationEntry[] = rawCert.map((c) => ({
    name: String(c.name ?? ""),
    issuer: c.issuer as string | undefined,
    issue_date: (c.issue_date ?? c.year) as string | undefined,
    expiration_date: c.expiration_date as string | undefined,
    does_not_expire: Boolean(c.does_not_expire),
    credential_id: c.credential_id as string | undefined,
    credential_url: c.credential_url as string | undefined,
  }));

  const existingOrder: string[] = (raw.section_order as string[] | undefined) ?? [];
  const defaultOrder = EMPTY_PARSED_DATA.section_order!;
  const section_order = existingOrder.length > 0 ? existingOrder : defaultOrder;

  return {
    contact: {
      headline: (raw as Record<string, Record<string, unknown>>).contact?.headline as string ?? "",
      location: (raw as Record<string, Record<string, unknown>>).contact?.location as string ?? "",
      linkedin_url: (raw as Record<string, Record<string, unknown>>).contact?.linkedin_url as string ?? "",
      github_url: (raw as Record<string, Record<string, unknown>>).contact?.github_url as string ?? "",
      portfolio_url: (raw as Record<string, Record<string, unknown>>).contact?.portfolio_url as string ?? "",
      other_links: ((raw as Record<string, Record<string, unknown>>).contact?.other_links as { label?: string; url: string }[]) ?? [],
    },
    summary: String(raw.summary ?? ""),
    skills,
    skill_categories: (raw.skill_categories as { category: string; items: string[] }[] | undefined) ?? [],
    experience,
    education,
    projects,
    certifications,
    languages: (raw.languages as LanguageEntry[] | undefined) ?? [],
    awards: (raw.awards as AwardEntry[] | undefined) ?? [],
    volunteer: (raw.volunteer as VolunteerEntry[] | undefined) ?? [],
    publications: (raw.publications as PublicationEntry[] | undefined) ?? [],
    courses: (raw.courses as CourseEntry[] | undefined) ?? [],
    interests: (raw.interests as string[] | undefined) ?? [],
    custom_sections: (raw.custom_sections as CustomSection[] | undefined) ?? [],
    section_order,
  };
}
