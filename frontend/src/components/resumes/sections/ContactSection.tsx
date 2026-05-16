import type { UseFormReturn } from "react-hook-form";
import { Globe, Link as LinkIcon, Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { UrlInput } from "../editor/UrlInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface ContactSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function ContactSection({ form }: ContactSectionProps) {
  const { register, watch, setValue } = form;
  const otherLinks = watch("parsed_data.contact.other_links") ?? [];

  const addLink = () => {
    setValue("parsed_data.contact.other_links", [...otherLinks, { label: "", url: "" }]);
  };
  const removeLink = (i: number) => {
    setValue("parsed_data.contact.other_links", otherLinks.filter((_, idx) => idx !== i));
  };

  return (
    <div className="space-y-5">
      {/* Name + Headline */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Full Name *</Label>
          <Input {...register("candidate_name")} placeholder="Sarthak Bhalla" className="h-10 bg-background/50 border-border/40" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Professional Headline</Label>
          <Input {...register("parsed_data.contact.headline")} placeholder="Senior Backend Engineer" className="h-10 bg-background/50 border-border/40" />
        </div>
      </div>

      {/* Email + Phone */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Email</Label>
          <Input {...register("email")} type="email" placeholder="name@example.com" className="h-10 bg-background/50 border-border/40" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Phone</Label>
          <Input {...register("phone_number")} placeholder="+1 555 000 0000" className="h-10 bg-background/50 border-border/40" />
        </div>
      </div>

      {/* Location */}
      <div className="space-y-1.5">
        <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</Label>
        <Input {...register("parsed_data.contact.location")} placeholder="Mumbai, India" className="h-10 bg-background/50 border-border/40" />
      </div>

      {/* Social links */}
      <div className="space-y-3">
        <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Social & Portfolio Links</Label>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-muted-foreground/40 w-4 shrink-0">in</span>
            <UrlInput
              value={watch("parsed_data.contact.linkedin_url")}
              onChange={(v) => setValue("parsed_data.contact.linkedin_url", v)}
              placeholder="https://linkedin.com/in/yourname"
              className="flex-1"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-muted-foreground/40 w-4 shrink-0">gh</span>
            <UrlInput
              value={watch("parsed_data.contact.github_url")}
              onChange={(v) => setValue("parsed_data.contact.github_url", v)}
              placeholder="https://github.com/yourname"
              className="flex-1"
            />
          </div>
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-muted-foreground/40 shrink-0" />
            <UrlInput
              value={watch("parsed_data.contact.portfolio_url")}
              onChange={(v) => setValue("parsed_data.contact.portfolio_url", v)}
              placeholder="https://yourportfolio.com"
              className="flex-1"
            />
          </div>
        </div>

        {/* Other links */}
        {otherLinks.map((link, i) => (
          <div key={i} className="flex items-center gap-2">
            <LinkIcon className="h-4 w-4 text-muted-foreground/40 shrink-0" />
            <Input
              value={link.label ?? ""}
              onChange={(e) => {
                const next = [...otherLinks];
                next[i] = { ...next[i], label: e.target.value };
                setValue("parsed_data.contact.other_links", next);
              }}
              placeholder="Label (e.g. Twitter)"
              className="h-9 w-28 bg-background/50 border-border/40 text-sm"
            />
            <UrlInput
              value={link.url}
              onChange={(v) => {
                const next = [...otherLinks];
                next[i] = { ...next[i], url: v };
                setValue("parsed_data.contact.other_links", next);
              }}
              placeholder="https://..."
              className="flex-1"
            />
            <button type="button" onClick={() => removeLink(i)} className="text-muted-foreground hover:text-destructive">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}

        <Button type="button" variant="ghost" size="sm" onClick={addLink} className="h-8 text-xs gap-1.5 text-muted-foreground">
          <Plus className="h-3 w-3" /> Add another link
        </Button>
      </div>
    </div>
  );
}
