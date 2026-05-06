import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { User, Mail, Phone, FileText, Code, Briefcase, GraduationCap, Award, FolderKanban } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Resume } from "./ResumeTable";

interface ResumeDetailModalProps {
  resume: Resume | null;
  isOpen: boolean;
  onClose: () => void;
}

export function ResumeDetailModal({ resume, isOpen, onClose }: ResumeDetailModalProps) {
  if (!resume) return null;

  const parsedData = resume.parsed_data || {};
  const skills = parsedData.skills || [];
  const experience = parsedData.experience || [];
  const projects = parsedData.projects || [];
  const education = parsedData.education || [];
  const certifications = parsedData.certifications || [];
  const skillCategories = parsedData.skill_categories || [];

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl bg-card/95 backdrop-blur-xl border-border/50">
        <DialogHeader>
          <div className="flex items-center gap-4 mb-2">
            <div className="p-3 bg-primary/10 rounded-xl text-primary">
              <User className="h-6 w-6" />
            </div>
            <div>
              <DialogTitle className="text-2xl font-bold">{resume.candidate_name || "Unknown Candidate"}</DialogTitle>
              <DialogDescription>
                Uploaded on {new Date(resume.created_at).toLocaleDateString()}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="grid gap-6 py-4 overflow-y-auto max-h-[60vh] pr-2">
          {/* Contact Info */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg border border-border/50">
              <Mail className="h-4 w-4 text-primary" />
              {resume.email || "No email"}
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg border border-border/50">
              <Phone className="h-4 w-4 text-primary" />
              {resume.phone_number || "No phone"}
            </div>
          </div>

          {/* Skills */}
          {skills.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <Code className="h-4 w-4 text-primary" />
                Skills
              </div>
              <div className="flex flex-wrap gap-2">
                {skills.map((skill: string, i: number) => (
                  <Badge key={i} variant="secondary" className="bg-primary/5 text-primary border-primary/10">
                    {skill}
                  </Badge>
                ))}
              </div>
              {skillCategories.length > 0 && (
                <div className="space-y-2">
                  {skillCategories.map((category: any, i: number) => (
                    <div key={i} className="text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">{category.category}:</span>{" "}
                      {(category.items || []).join(", ")}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Experience */}
          {experience.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <Briefcase className="h-4 w-4 text-primary" />
                Experience
              </div>
              <div className="space-y-3">
                {experience.map((exp: any, i: number) => (
                  <div key={i} className="p-3 bg-muted/20 rounded-lg border border-border/50 space-y-1">
                    <div className="font-medium">{exp.role_title || exp.title || exp.role || exp}</div>
                    <div className="text-sm text-muted-foreground flex items-center justify-between">
                      <span>{exp.company_name || exp.company || ""}</span>
                      <span>{exp.duration_text || [exp.from_date || exp.start_date, exp.to_date || exp.end_date].filter(Boolean).join(" - ") || exp.duration || ""}</span>
                    </div>
                    {exp.location && (
                      <div className="text-sm text-muted-foreground">{exp.location}</div>
                    )}
                    {Array.isArray(exp.tasks_performed || exp.bullets) && (exp.tasks_performed || exp.bullets).length > 0 && (
                      <ul className="list-disc pl-5 text-sm text-muted-foreground space-y-1">
                        {(exp.tasks_performed || exp.bullets).map((bullet: string, bulletIndex: number) => (
                          <li key={bulletIndex}>{bullet}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Projects */}
          {projects.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <FolderKanban className="h-4 w-4 text-primary" />
                Projects
              </div>
              <div className="space-y-3">
                {projects.map((project: any, i: number) => (
                  <div key={i} className="p-3 bg-muted/20 rounded-lg border border-border/50 space-y-2">
                    <div className="font-medium">{project.name || "Project"}</div>
                    {Array.isArray(project.technologies) && project.technologies.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {project.technologies.map((tech: string, techIndex: number) => (
                          <Badge key={techIndex} variant="outline">{tech}</Badge>
                        ))}
                      </div>
                    )}
                    {Array.isArray(project.bullets) && project.bullets.length > 0 && (
                      <ul className="list-disc pl-5 text-sm text-muted-foreground space-y-1">
                        {project.bullets.map((bullet: string, bulletIndex: number) => (
                          <li key={bulletIndex}>{bullet}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Education */}
          {education.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <GraduationCap className="h-4 w-4 text-primary" />
                Education
              </div>
              <div className="space-y-3">
                {education.map((item: any, i: number) => (
                  <div key={i} className="p-3 bg-muted/20 rounded-lg border border-border/50 space-y-1">
                    <div className="font-medium">{item.institution || "Institution"}</div>
                    <div className="text-sm text-muted-foreground">
                      {[item.degree, item.field].filter(Boolean).join(" - ")}
                    </div>
                    <div className="text-sm text-muted-foreground flex items-center justify-between">
                      <span>{item.location || ""}</span>
                      <span>{[item.start_date, item.end_date].filter(Boolean).join(" - ")}</span>
                    </div>
                    {item.score && <div className="text-sm text-muted-foreground">{item.score}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Certifications */}
          {certifications.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <Award className="h-4 w-4 text-primary" />
                Certifications
              </div>
              <div className="space-y-2">
                {certifications.map((cert: any, i: number) => (
                  <div key={i} className="text-sm text-muted-foreground bg-muted/20 p-3 rounded-lg border border-border/50">
                    <span className="font-medium text-foreground">{cert.name}</span>
                    {cert.issuer ? ` - ${cert.issuer}` : ""}
                    {cert.year ? ` (${cert.year})` : ""}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Raw Text / Summary Placeholder */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 font-semibold">
              <FileText className="h-4 w-4 text-primary" />
              Resume Content
            </div>
            <div className="p-4 bg-muted/30 rounded-lg border border-border/50 text-sm text-muted-foreground leading-relaxed italic">
              {parsedData.summary || "No summary extracted. Full resume text is available in the storage layer."}
            </div>
          </div>
        </div>

        <DialogFooter className="border-t border-border/50 pt-4">
          <Button onClick={onClose} className="w-full sm:w-auto">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
