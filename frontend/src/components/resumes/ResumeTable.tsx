import { Link } from "react-router-dom";
import { FileText, Mail, Phone, PhoneCall, Trash2, User } from "lucide-react";
import { cn } from "@/lib/utils";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/DataTable";
import type { ColumnDef } from "@/components/ui/DataTable";
import type { CallRecord } from "@/lib/calls";

export interface Resume {
  id: string;
  job_id: string;
  candidate_name: string | null;
  phone_number: string | null;
  email: string | null;
  status: string;
  created_at: string;
  file_path: string;
  file_type: string;
  matching_score: number | null;
  match_explanation: string | null;
  parsed_data?: any;
}

interface ResumeTableProps {
  resumes: Resume[];
  activeCallsByResumeId: Record<string, CallRecord | undefined>;
  onDelete: (id: string) => void;
  onView: (resume: Resume) => void;
  onStartCall: (resume: Resume) => void;
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSortChange: (sortBy: string, sortOrder: "asc" | "desc") => void;
  currentPage: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
}

const statusTone: Record<string, string> = {
  parsed: "bg-green-500/10 text-green-500 border-green-500/20",
  error: "bg-destructive/10 text-destructive border-destructive/20",
  uploaded: "bg-slate-500/10 text-slate-500 border-slate-500/20",
};

function getDisplayName(resume: Resume) {
  if (resume.candidate_name) return resume.candidate_name;
  const filename = resume.file_path.split("/").pop() || "Unknown Candidate";
  return filename.replace(/\.(pdf|docx)$/i, "");
}

export function ResumeTable({
  resumes,
  activeCallsByResumeId,
  onDelete,
  onView,
  onStartCall,
  sortBy,
  sortOrder,
  onSortChange,
  currentPage,
  pageSize,
  totalItems,
  onPageChange,
}: ResumeTableProps) {
  const columns: ColumnDef<Resume>[] = [
    {
      key: "candidate",
      label: "Candidate",
      sortKey: "candidate_name",
      cell: (resume) => (
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2.5 text-primary shadow-sm group-hover:scale-110 transition-transform">
            <User className="h-4 w-4" />
          </div>
          <span className="font-bold text-sm tracking-tight">{getDisplayName(resume)}</span>
        </div>
      ),
    },
    {
      key: "contact",
      label: "Contact",
      cell: (resume) => (
        <div className="space-y-1.5">
          {resume.email && (
            <div className="flex items-center gap-2 text-[11px] font-medium text-muted-foreground hover:text-primary transition-colors cursor-default">
              <Mail className="h-3 w-3 opacity-60" />
              {resume.email}
            </div>
          )}
          {resume.phone_number && (
            <div className="flex items-center gap-2 text-[11px] font-medium text-muted-foreground hover:text-primary transition-colors cursor-default">
              <Phone className="h-3 w-3 opacity-60" />
              {resume.phone_number}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "rank",
      label: "Rank",
      sortKey: "matching_score",
      headerClassName: "text-center",
      className: "text-center",
      cell: (resume) =>
        resume.matching_score !== null ? (
          <div className="flex flex-col items-center gap-1 group/score relative">
            <Badge
              variant="outline"
              className={cn(
                "px-2.5 py-1 rounded-md font-black text-sm tracking-tight border-2 shadow-sm transition-all group-hover/score:scale-110",
                resume.matching_score >= 80
                  ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                  : resume.matching_score >= 50
                  ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                  : "bg-rose-500/10 text-rose-500 border-rose-500/20"
              )}
            >
              {Math.round(resume.matching_score)}%
            </Badge>
            {resume.match_explanation && (
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-popover text-popover-foreground text-[11px] font-medium leading-relaxed rounded-lg border border-border shadow-xl opacity-0 invisible group-hover/score:opacity-100 group-hover/score:visible transition-all z-50 backdrop-blur-md">
                <div className="font-black mb-1 uppercase tracking-widest text-primary/80">AI Insight</div>
                {resume.match_explanation}
                <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-popover" />
              </div>
            )}
          </div>
        ) : (
          <span className="text-[10px] font-black text-muted-foreground uppercase opacity-30 tracking-widest">Pending</span>
        ),
    },
    {
      key: "status",
      label: "Status",
      sortKey: "status",
      cell: (resume) => (
        <Badge
          variant={resume.status === "error" ? "destructive" : "secondary"}
          className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-tighter", statusTone[resume.status])}
        >
          {resume.status.replace("_", " ")}
        </Badge>
      ),
    },
    {
      key: "call_action",
      label: "Call Action",
      cell: (resume) => {
        const activeCall = activeCallsByResumeId[resume.id];
        const canStartCall = resume.status === "parsed" && !!resume.phone_number && !activeCall;
        if (activeCall) {
          return (
            <Button size="sm" variant="outline" className="h-8 rounded-lg text-[11px] font-bold text-primary border-primary/20 bg-primary/5 hover:bg-primary/10" asChild>
              <Link to={`/calls/${activeCall.id}`}>VIEW CALL</Link>
            </Button>
          );
        }
        if (canStartCall) {
          return (
            <Button size="sm" className="h-8 rounded-lg text-[11px] font-bold shadow-md shadow-primary/10" onClick={() => onStartCall(resume)}>
              <PhoneCall className="mr-1.5 h-3.5 w-3.5" />
              START CALL
            </Button>
          );
        }
        return (
          <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest opacity-40">
            {resume.status !== "parsed" ? "Awaiting parse" : "No phone"}
          </span>
        );
      },
    },
    {
      key: "uploaded",
      label: "Uploaded",
      sortKey: "created_at",
      headerClassName: "text-right",
      className: "text-xs font-medium text-muted-foreground opacity-80 text-right",
      cell: (resume) => new Date(resume.created_at).toLocaleDateString(),
    },
    {
      key: "actions",
      label: "Actions",
      headerClassName: "text-right",
      className: "text-right",
      cell: (resume) => (
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 rounded-lg hover:bg-primary/10 hover:text-primary"
            onClick={() => onView(resume)}
          >
            <FileText className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 rounded-lg hover:bg-destructive/10 hover:text-destructive"
            onClick={() => onDelete(resume.id)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      {/* Mobile Card View */}
      <div className="grid grid-cols-1 gap-4 md:hidden">
        {resumes.map((resume) => {
          const activeCall = activeCallsByResumeId[resume.id];
          const canStartCall = resume.status === "parsed" && !!resume.phone_number && !activeCall;
          return (
            <div key={resume.id} className="glass p-4 rounded-lg border border-border/50 shadow-sm space-y-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-primary/10 p-2.5 text-primary shadow-sm">
                    <User className="h-5 w-5" />
                  </div>
                  <div className="flex flex-col">
                    <span className="font-bold text-base leading-none mb-1">{getDisplayName(resume)}</span>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={resume.status === "error" ? "destructive" : "secondary"}
                        className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-tighter", statusTone[resume.status])}
                      >
                        {resume.status.replace("_", " ")}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground font-bold uppercase">
                        {new Date(resume.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={() => onDelete(resume.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <div className="grid grid-cols-1 gap-2 py-2 border-y border-border/30">
                {resume.email && (
                  <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Mail className="h-3.5 w-3.5 text-primary/60" />
                    {resume.email}
                  </div>
                )}
                {resume.phone_number && (
                  <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Phone className="h-3.5 w-3.5 text-primary/60" />
                    {resume.phone_number}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 pt-2">
                <div className="flex-1 flex flex-col gap-1">
                  <span className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">Match Score</span>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-muted/50 overflow-hidden">
                      <div
                        className={cn(
                          "h-full transition-all duration-1000",
                          (resume.matching_score ?? 0) >= 80
                            ? "bg-emerald-500"
                            : (resume.matching_score ?? 0) >= 50
                            ? "bg-amber-500"
                            : "bg-rose-500"
                        )}
                        style={{ width: `${resume.matching_score ?? 0}%` }}
                      />
                    </div>
                    <span className="text-xs font-black tracking-tighter">
                      {resume.matching_score ? `${Math.round(resume.matching_score)}%` : "N/A"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2">
                <Button variant="outline" size="sm" className="flex-1 rounded-lg h-10 font-bold" onClick={() => onView(resume)}>
                  View Details
                </Button>
                {activeCall ? (
                  <Button variant="secondary" size="sm" className="flex-1 rounded-lg h-10 font-bold text-primary" asChild>
                    <Link to={`/calls/${activeCall.id}`}>Active Call</Link>
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    className="flex-1 rounded-lg h-10 font-bold shadow-sm shadow-primary/10"
                    onClick={() => onStartCall(resume)}
                    disabled={!canStartCall}
                  >
                    <PhoneCall className="mr-2 h-4 w-4" />
                    Start Call
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:block">
        <DataTable
          columns={columns}
          data={resumes}
          rowKey={(r) => r.id}
          sortBy={sortBy}
          sortOrder={sortOrder}
          onSortChange={onSortChange}
          currentPage={currentPage}
          pageSize={pageSize}
          totalItems={totalItems}
          onPageChange={onPageChange}
          emptyIcon={<FileText className="h-8 w-8 text-muted-foreground/40" />}
          emptyTitle="No candidates yet"
          emptyDescription="Upload resumes to see candidate information and launch screening calls."
        />
      </div>
    </>
  );
}
