import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowLeft,
  FileText,
  Loader2,
  RefreshCw,
  Save,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useToast } from "@/context/ToastContext";
import { resumeUpdateSchema, migrateToV3, EMPTY_PARSED_DATA, type ResumeUpdate } from "@/lib/resume-schema";

// Section components
import { ContactSection } from "@/components/resumes/sections/ContactSection";
import { SummarySection } from "@/components/resumes/sections/SummarySection";
import { SkillsSection } from "@/components/resumes/sections/SkillsSection";
import { LanguagesSection } from "@/components/resumes/sections/LanguagesSection";
import { ExperienceSection } from "@/components/resumes/sections/ExperienceSection";
import { EducationSection } from "@/components/resumes/sections/EducationSection";
import { ProjectsSection } from "@/components/resumes/sections/ProjectsSection";
import { CertificationsSection } from "@/components/resumes/sections/CertificationsSection";
import { AwardsSection } from "@/components/resumes/sections/AwardsSection";
import { VolunteerSection } from "@/components/resumes/sections/VolunteerSection";
import { PublicationsSection } from "@/components/resumes/sections/PublicationsSection";
import { CoursesSection } from "@/components/resumes/sections/CoursesSection";
import { InterestsSection } from "@/components/resumes/sections/InterestsSection";
import { CustomSectionComponent } from "@/components/resumes/sections/CustomSectionComponent";
import { SectionNav, type NavSection } from "@/components/resumes/editor/SectionNav";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ResumeData {
  id: string;
  job_id: string;
  candidate_name: string | null;
  phone_number: string | null;
  email: string | null;
  file_path: string;
  file_type: string;
  status: string;
  matching_score: number | null;
  match_explanation: string | null;
  parsed_data: Record<string, unknown> | null;
}

const OPTIONAL_SECTIONS = [
  { key: "languages", label: "Languages" },
  { key: "awards", label: "Awards & Achievements" },
  { key: "volunteer", label: "Volunteer Experience" },
  { key: "publications", label: "Publications" },
  { key: "courses", label: "Courses & Training" },
  { key: "interests", label: "Interests" },
];

const DRAFT_KEY = (id: string) => `resume-draft:${id}`;

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export function ResumeEdit() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [resume, setResume] = useState<ResumeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeSection, setActiveSection] = useState("contact");
  const [matchScore, setMatchScore] = useState<number | null>(null);
  const [hasDraft, setHasDraft] = useState(false);
  const [visibleOptional, setVisibleOptional] = useState<string[]>([]);
  const [showAddSection, setShowAddSection] = useState(false);

  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const form = useForm<ResumeUpdate>({
    resolver: zodResolver(resumeUpdateSchema) as any,
    defaultValues: {
      candidate_name: "",
      phone_number: "",
      email: "",
      parsed_data: { ...EMPTY_PARSED_DATA },
      recalculate_match: true,
    },
  });

  const { watch, formState, setValue, handleSubmit, reset } = form;
  const parsedData = watch("parsed_data");

  // ---------------------------------------------------------------------------
  // Load resume
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!resumeId) return;
    (async () => {
      try {
        const { data } = await api.get<ResumeData>(`/resumes/${resumeId}`);
        setResume(data);
        setMatchScore(data.matching_score);

        const migrated = migrateToV3(data.parsed_data);

        // Check for saved draft
        const rawDraft = localStorage.getItem(DRAFT_KEY(resumeId));
        if (rawDraft) {
          setHasDraft(true);
        }

        reset({
          candidate_name: data.candidate_name ?? "",
          phone_number: data.phone_number ?? "",
          email: data.email ?? "",
          parsed_data: migrated,
          recalculate_match: true,
        });

        // Determine which optional sections have data
        const presentOptional = OPTIONAL_SECTIONS
          .filter((s) => {
            const val = (migrated as unknown as Record<string, unknown>)[s.key];
            return Array.isArray(val) ? val.length > 0 : !!val;
          })
          .map((s) => s.key);
        setVisibleOptional(presentOptional);
      } catch {
        toast({ variant: "error", title: "Failed to load resume" });
        navigate(-1);
      } finally {
        setLoading(false);
      }
    })();
  }, [resumeId]); // eslint-disable-line

  // ---------------------------------------------------------------------------
  // Auto-save draft to localStorage (2s debounce)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!formState.isDirty || !resumeId) return;
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT_KEY(resumeId), JSON.stringify(form.getValues()));
      } catch { /* ignore storage quota errors */ }
    }, 2000);
    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    };
  }, [formState.isDirty, resumeId, form]);

  // ---------------------------------------------------------------------------
  // Restore draft
  // ---------------------------------------------------------------------------
  const restoreDraft = () => {
    if (!resumeId) return;
    try {
      const raw = localStorage.getItem(DRAFT_KEY(resumeId));
      if (!raw) return;
      const draft = JSON.parse(raw) as ResumeUpdate;
      reset(draft);
      setHasDraft(false);
      toast({ variant: "success", title: "Draft restored" });
    } catch {
      toast({ variant: "error", title: "Could not restore draft" });
    }
  };

  const discardDraft = () => {
    if (!resumeId) return;
    localStorage.removeItem(DRAFT_KEY(resumeId));
    setHasDraft(false);
  };

  // ---------------------------------------------------------------------------
  // Save
  // ---------------------------------------------------------------------------
  const onSubmit = async (data: ResumeUpdate) => {
    if (!resumeId) return;
    setSaving(true);
    try {
      const { data: updated } = await api.patch<ResumeData>(`/resumes/${resumeId}`, data);
      setMatchScore(updated.matching_score);
      reset(data); // mark form as clean with saved values
      if (resumeId) localStorage.removeItem(DRAFT_KEY(resumeId));
      setHasDraft(false);
      const scoreMsg =
        updated.matching_score !== null
          ? ` · Match score: ${Math.round(updated.matching_score)}%`
          : "";
      toast({ variant: "success", title: `Saved${scoreMsg}` });
    } catch {
      toast({ variant: "error", title: "Save failed", description: "Please try again." });
    } finally {
      setSaving(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Section nav data — orderable via drag-and-drop
  // ---------------------------------------------------------------------------

  // Master lookup: all known sections keyed by their key string.
  // Counts are re-derived each render so badges stay live.
  const SECTION_META: Record<string, Omit<NavSection, "count">> = {
    contact:        { key: "contact",        label: "Contact Info" },
    summary:        { key: "summary",        label: "Summary" },
    experience:     { key: "experience",     label: "Experience" },
    education:      { key: "education",      label: "Education" },
    skills:         { key: "skills",         label: "Skills" },
    projects:       { key: "projects",       label: "Projects" },
    certifications: { key: "certifications", label: "Certifications" },
    languages:      { key: "languages",      label: "Languages" },
    awards:         { key: "awards",         label: "Awards & Achievements" },
    volunteer:      { key: "volunteer",      label: "Volunteer Experience" },
    publications:   { key: "publications",   label: "Publications" },
    courses:        { key: "courses",        label: "Courses & Training" },
    interests:      { key: "interests",      label: "Interests" },
  };

  // `navOrder` is the live display order. Initialized from saved section_order or
  // default; updated instantly on drag so the nav re-renders immediately.
  const [navOrder, setNavOrder] = useState<string[]>(() => {
    const savedOrder = parsedData?.section_order ?? [];
    const defaultKeys = ["contact","summary","experience","education","skills","projects","certifications"];
    return savedOrder.length > 0 ? savedOrder : defaultKeys;
  });

  // Whenever visibleOptional or custom sections change, ensure they appear in navOrder.
  // New sections appended at the end if not already present.
  const allPossibleKeys = [
    ...Object.keys(SECTION_META),
    ...(parsedData?.custom_sections ?? []).map((cs) => `custom:${cs.id}`),
  ];
  const navOrderWithNew = [
    ...navOrder,
    ...allPossibleKeys.filter((k) => !navOrder.includes(k) && (
      visibleOptional.includes(k) ||
      (parsedData?.custom_sections ?? []).some((cs) => `custom:${cs.id}` === k)
    )),
  ].filter((k) => (
    SECTION_META[k] !== undefined ||
    (parsedData?.custom_sections ?? []).some((cs) => `custom:${cs.id}` === k)
  ));

  const getCount = (key: string): number | undefined => {
    if (key.startsWith("custom:")) {
      const cs = (parsedData?.custom_sections ?? []).find((c) => `custom:${c.id}` === key);
      return cs?.items?.length;
    }
    const arr = (parsedData as unknown as Record<string, unknown[]>)?.[key];
    return Array.isArray(arr) ? arr.length : undefined;
  };

  const allSections: NavSection[] = navOrderWithNew
    .filter((k) => {
      // Core sections always shown; optional only if in visibleOptional
      if (OPTIONAL_SECTIONS.some((s) => s.key === k)) return visibleOptional.includes(k);
      return true;
    })
    .map((k) => {
      if (k.startsWith("custom:")) {
        const cs = (parsedData?.custom_sections ?? []).find((c) => `custom:${c.id}` === k);
        const i = (parsedData?.custom_sections ?? []).findIndex((c) => `custom:${c.id}` === k);
        return { key: k, label: cs?.section_title || `Custom ${i + 1}`, count: cs?.items?.length };
      }
      return { ...SECTION_META[k], count: getCount(k) };
    })
    .filter(Boolean) as NavSection[];

  // Hidden optional sections not yet shown in the editor
  const hiddenOptional = OPTIONAL_SECTIONS.filter((s) => !visibleOptional.includes(s.key));

  const showSection = (key: string) => {
    setVisibleOptional((prev) => [...prev, key]);
    setNavOrder((prev) => prev.includes(key) ? prev : [...prev, key]);
    setShowAddSection(false);
    setTimeout(() => sectionRefs.current[key]?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  };

  const addCustomSection = () => {
    const id = crypto.randomUUID();
    const current = parsedData?.custom_sections ?? [];
    setValue("parsed_data.custom_sections", [...current, { id, section_title: "", items: [] }]);
    setNavOrder((prev) => [...prev, `custom:${id}`]);
    setShowAddSection(false);
  };

  const removeCustomSection = (id: string) => {
    const current = parsedData?.custom_sections ?? [];
    setValue("parsed_data.custom_sections", current.filter((cs) => cs.id !== id));
  };

  // ---------------------------------------------------------------------------
  // Open original PDF
  // ---------------------------------------------------------------------------
  const openPdf = async () => {
    try {
      const resp = await api.get(`/resumes/${resumeId}/file`, { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      toast({ variant: "error", title: "Could not load resume file" });
    }
  };

  // ---------------------------------------------------------------------------
  // Scroll-spy: update activeSection based on visible section
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) {
          setActiveSection(visible[0].target.id);
        }
      },
      { rootMargin: "-10% 0px -60% 0px" }
    );
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [visibleOptional, parsedData?.custom_sections?.length]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center gap-3 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading resume…
      </div>
    );
  }

  const candidateName = watch("candidate_name") || resume?.candidate_name || "Resume";
  const jobId = resume?.job_id;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      {/* ── Sticky header ─────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border/40 bg-background/80 backdrop-blur-xl shrink-0 z-20">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" asChild className="gap-2 text-muted-foreground hover:text-foreground">
            <Link to={jobId ? `/jobs/${jobId}` : "/dashboard"}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h1 className="font-black text-xl tracking-tight">{candidateName}</h1>
            <p className="text-xs text-muted-foreground/60">Resume Editor</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {matchScore !== null && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/5 border border-primary/20">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Match</span>
              <span className="text-sm font-black text-primary">{Math.round(matchScore)}%</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={handleSubmit(onSubmit as Parameters<typeof handleSubmit>[0])}
                disabled={saving}
                title="Recalculate match score"
              >
                <RefreshCw className={`h-3 w-3 ${saving ? "animate-spin" : ""}`} />
              </Button>
            </div>
          )}
        </div>
      </header>

      {/* ── Draft restore banner ───────────────────────────────────── */}
      {hasDraft && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-2 flex items-center justify-between text-sm shrink-0">
          <span className="text-amber-600 dark:text-amber-400 font-medium">You have unsaved changes from a previous session.</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={restoreDraft}>Restore</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs text-muted-foreground" onClick={discardDraft}>Discard</Button>
          </div>
        </div>
      )}

      {/* ── Body: nav + editor ────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left nav */}
        <aside className="w-56 shrink-0 border-r border-border/30 overflow-y-auto p-3">
          <SectionNav
            sections={allSections}
            activeKey={activeSection}
            onSelect={(key) => {
              setActiveSection(key);
              sectionRefs.current[key]?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            onReorder={(reordered) => {
              const newOrder = reordered.map((s) => s.key);
              setNavOrder(newOrder);  // immediate visual update
              setValue("parsed_data.section_order", newOrder);  // persist on save
            }}
            onAdd={() => setShowAddSection((v) => !v)}
          />

          {/* Add section popover */}
          {showAddSection && (
            <div className="mt-2 rounded-xl border border-border/40 bg-popover shadow-lg p-2 text-sm space-y-0.5">
              {hiddenOptional.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => showSection(s.key)}
                  className="w-full text-left px-3 py-1.5 rounded-lg hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {s.label}
                </button>
              ))}
              <button
                type="button"
                onClick={addCustomSection}
                className="w-full text-left px-3 py-1.5 rounded-lg hover:bg-primary/10 text-primary transition-colors flex items-center gap-1.5"
              >
                <Plus className="h-3.5 w-3.5" /> Custom section…
              </button>
            </div>
          )}
        </aside>

        {/* Editor area */}
        <main className="flex-1 overflow-y-auto">
          <form onSubmit={handleSubmit(onSubmit as Parameters<typeof handleSubmit>[0])} className="max-w-3xl mx-auto px-8 py-8 space-y-12">

            {/* Contact */}
            <section id="contact" ref={(el) => { sectionRefs.current["contact"] = el; }}>
              <SectionHeading>Contact Information</SectionHeading>
              <ContactSection form={form} />
            </section>

            {/* Summary */}
            <section id="summary" ref={(el) => { sectionRefs.current["summary"] = el; }}>
              <SectionHeading>Professional Summary</SectionHeading>
              <SummarySection form={form} />
            </section>

            {/* Experience */}
            <section id="experience" ref={(el) => { sectionRefs.current["experience"] = el; }}>
              <SectionHeading>Work Experience</SectionHeading>
              <ExperienceSection form={form} />
            </section>

            {/* Education */}
            <section id="education" ref={(el) => { sectionRefs.current["education"] = el; }}>
              <SectionHeading>Education</SectionHeading>
              <EducationSection form={form} />
            </section>

            {/* Skills */}
            <section id="skills" ref={(el) => { sectionRefs.current["skills"] = el; }}>
              <SectionHeading>Skills</SectionHeading>
              <SkillsSection form={form} />
            </section>

            {/* Projects */}
            <section id="projects" ref={(el) => { sectionRefs.current["projects"] = el; }}>
              <SectionHeading>Projects</SectionHeading>
              <ProjectsSection form={form} />
            </section>

            {/* Certifications */}
            <section id="certifications" ref={(el) => { sectionRefs.current["certifications"] = el; }}>
              <SectionHeading>Certifications</SectionHeading>
              <CertificationsSection form={form} />
            </section>

            {/* Optional sections */}
            {visibleOptional.includes("languages") && (
              <section id="languages" ref={(el) => { sectionRefs.current["languages"] = el; }}>
                <SectionHeading>Languages</SectionHeading>
                <LanguagesSection form={form} />
              </section>
            )}

            {visibleOptional.includes("awards") && (
              <section id="awards" ref={(el) => { sectionRefs.current["awards"] = el; }}>
                <SectionHeading>Awards & Achievements</SectionHeading>
                <AwardsSection form={form} />
              </section>
            )}

            {visibleOptional.includes("volunteer") && (
              <section id="volunteer" ref={(el) => { sectionRefs.current["volunteer"] = el; }}>
                <SectionHeading>Volunteer Experience</SectionHeading>
                <VolunteerSection form={form} />
              </section>
            )}

            {visibleOptional.includes("publications") && (
              <section id="publications" ref={(el) => { sectionRefs.current["publications"] = el; }}>
                <SectionHeading>Publications</SectionHeading>
                <PublicationsSection form={form} />
              </section>
            )}

            {visibleOptional.includes("courses") && (
              <section id="courses" ref={(el) => { sectionRefs.current["courses"] = el; }}>
                <SectionHeading>Courses & Training</SectionHeading>
                <CoursesSection form={form} />
              </section>
            )}

            {visibleOptional.includes("interests") && (
              <section id="interests" ref={(el) => { sectionRefs.current["interests"] = el; }}>
                <SectionHeading>Interests & Hobbies</SectionHeading>
                <InterestsSection form={form} />
              </section>
            )}

            {/* Custom sections */}
            {(parsedData?.custom_sections ?? []).map((cs, idx) => (
              <section key={cs.id} id={`custom:${cs.id}`} ref={(el) => { sectionRefs.current[`custom:${cs.id}`] = el; }}>
                <CustomSectionComponent
                  form={form}
                  sectionIndex={idx}
                  onRemoveSection={() => removeCustomSection(cs.id)}
                />
              </section>
            ))}

            {/* Bottom padding */}
            <div className="h-24" />
          </form>
        </main>
      </div>

      {/* ── Sticky footer ─────────────────────────────────────────── */}
      <footer className="flex items-center justify-between px-6 py-3 border-t border-border/40 bg-background/80 backdrop-blur-xl shrink-0 z-20">
        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="sm" onClick={openPdf} className="gap-2 text-muted-foreground hover:text-foreground text-xs">
            <FileText className="h-3.5 w-3.5" />
            View original PDF
          </Button>
          {jobId && (
            <Link to={`/jobs/${jobId}`} className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
              ← Job Strategy & Questions
            </Link>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)} className="text-xs">
            Cancel
          </Button>
          <Button
            onClick={handleSubmit(onSubmit as Parameters<typeof handleSubmit>[0])}
            disabled={saving || !formState.isDirty}
            className="gap-2 font-bold"
          >
            {saving ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</>
            ) : (
              <><Save className="h-4 w-4" /> Save changes</>
            )}
          </Button>
        </div>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section heading component
// ---------------------------------------------------------------------------

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-black uppercase tracking-[0.2em] text-muted-foreground mb-4 pb-2 border-b border-border/30">
      {children}
    </h2>
  );
}
