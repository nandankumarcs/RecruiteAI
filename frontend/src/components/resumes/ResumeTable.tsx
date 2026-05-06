import { Link } from "react-router-dom";
import { FileText, Mail, Phone, PhoneCall, Trash2, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CallRecord } from "@/lib/calls";

export interface Resume {
  id: string;
  candidate_name: string | null;
  phone_number: string | null;
  email: string | null;
  status: string;
  created_at: string;
  file_path: string;
  file_type: string;
  parsed_data?: any;
}

interface ResumeTableProps {
  resumes: Resume[];
  activeCallsByResumeId: Record<string, CallRecord | undefined>;
  onDelete: (id: string) => void;
  onView: (resume: Resume) => void;
  onStartCall: (resume: Resume) => void;
}

const statusTone: Record<string, string> = {
  parsed: "bg-green-500/10 text-green-500 border-green-500/20",
  error: "bg-destructive/10 text-destructive border-destructive/20",
  uploaded: "bg-slate-500/10 text-slate-500 border-slate-500/20",
};

export function ResumeTable({
  resumes,
  activeCallsByResumeId,
  onDelete,
  onView,
  onStartCall,
}: ResumeTableProps) {
  const getStatusBadge = (status: string) => (
    <Badge variant={status === "error" ? "destructive" : "secondary"} className={statusTone[status] || ""}>
      {status.replace("_", " ")}
    </Badge>
  );

  if (resumes.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/50 bg-muted/20 py-12 text-center">
        <FileText className="mx-auto mb-4 h-12 w-12 text-muted-foreground/50" />
        <h3 className="text-lg font-semibold">No candidates yet</h3>
        <p className="text-muted-foreground">Upload resumes to see candidate information here.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border/50 bg-card/30 shadow-sm backdrop-blur-sm">
      <Table>
        <TableHeader className="bg-muted/50">
          <TableRow>
            <TableHead className="font-semibold">Candidate</TableHead>
            <TableHead className="font-semibold">Contact</TableHead>
            <TableHead className="font-semibold">Status</TableHead>
            <TableHead className="font-semibold">Call</TableHead>
            <TableHead className="font-semibold">Uploaded</TableHead>
            <TableHead className="text-right font-semibold">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {resumes.map((resume) => {
            const activeCall = activeCallsByResumeId[resume.id];
            const canStartCall = resume.status === "parsed" && !!resume.phone_number && !activeCall;

            return (
              <TableRow key={resume.id} className="transition-colors hover:bg-muted/30">
                <TableCell>
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-primary/10 p-2 text-primary">
                      <User className="h-4 w-4" />
                    </div>
                    <span className="font-medium">{resume.candidate_name || "Unknown"}</span>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="space-y-1">
                    {resume.email && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Mail className="h-3 w-3" />
                        {resume.email}
                      </div>
                    )}
                    {resume.phone_number && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Phone className="h-3 w-3" />
                        {resume.phone_number}
                      </div>
                    )}
                  </div>
                </TableCell>
                <TableCell>{getStatusBadge(resume.status)}</TableCell>
                <TableCell>
                  {activeCall ? (
                    <Link to={`/calls/${activeCall.id}`} className="text-sm font-medium text-primary hover:underline">
                      {activeCall.status.replace("_", " ")}
                    </Link>
                  ) : canStartCall ? (
                    <Button size="sm" onClick={() => onStartCall(resume)}>
                      <PhoneCall className="mr-2 h-4 w-4" />
                      Call
                    </Button>
                  ) : (
                    <span className="text-sm text-muted-foreground">
                      {resume.status !== "parsed" ? "Awaiting parse" : "No phone"}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(resume.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="hover:bg-primary/10 hover:text-primary"
                      onClick={() => onView(resume)}
                    >
                      View
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="hover:bg-destructive/10 hover:text-destructive"
                      onClick={() => onDelete(resume.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
