import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { DateTextInput } from "../editor/DateTextInput";
import { UrlInput } from "../editor/UrlInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface CertificationsSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function CertificationsSection({ form }: CertificationsSectionProps) {
  const { watch, setValue } = form;
  const certifications = watch("parsed_data.certifications") ?? [];

  const add = () => {
    setValue("parsed_data.certifications", [
      ...certifications,
      { name: "", does_not_expire: false },
    ]);
  };

  const remove = (i: number) => {
    setValue("parsed_data.certifications", certifications.filter((_, idx) => idx !== i));
  };

  const update = (i: number, field: string, value: unknown) => {
    const next = [...certifications];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.certifications", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={certifications}
        getKey={(_, i) => `cert-${i}`}
        onReorder={(reordered) => setValue("parsed_data.certifications", reordered)}
        renderItem={(cert, i) => (
        <SectionCard
          title={cert.name || "New Certification"}
          subtitle={cert.issuer}
          defaultExpanded={!cert.name}
          onRemove={() => remove(i)}
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Certification Name *</Label>
              <Input value={cert.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="AWS Solutions Architect" className="h-9 bg-background/50 border-border/40" />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Issuing Organisation</Label>
              <Input value={cert.issuer ?? ""} onChange={(e) => update(i, "issuer", e.target.value)} placeholder="Amazon Web Services" className="h-9 bg-background/50 border-border/40" />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Issue Date</Label>
                <DateTextInput value={cert.issue_date} onChange={(v) => update(i, "issue_date", v)} placeholder="Mar 2024" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Expiry Date</Label>
                <DateTextInput value={cert.does_not_expire ? "No expiry" : (cert.expiration_date ?? "")} onChange={(v) => update(i, "expiration_date", v)} placeholder="Mar 2027" disabled={cert.does_not_expire} />
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={cert.does_not_expire} onChange={(e) => update(i, "does_not_expire", e.target.checked)} className="rounded" />
              This certification does not expire
            </label>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Credential ID</Label>
                <Input value={cert.credential_id ?? ""} onChange={(e) => update(i, "credential_id", e.target.value)} placeholder="ABC-123456" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Credential URL</Label>
                <UrlInput value={cert.credential_url} onChange={(v) => update(i, "credential_url", v)} placeholder="https://verify.example.com/..." />
              </div>
            </div>
          </div>
        </SectionCard>
      )}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Certification
      </Button>
    </div>
  );
}
