import { Link } from "react-router-dom";
import { ExternalLink, PhoneCall } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/ui/DataTable";
import type { ColumnDef } from "@/components/ui/DataTable";
import { cn } from "@/lib/utils";
import type { CallRecord } from "@/lib/calls";

interface CallsTableProps {
  calls: CallRecord[];
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSortChange: (sortBy: string, sortOrder: "asc" | "desc") => void;
  currentPage: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
}

const statusTone: Record<string, string> = {
  completed: "bg-green-500/10 text-green-500 border-green-500/20",
  failed: "bg-destructive/10 text-destructive border-destructive/20",
  in_progress: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  ringing: "bg-amber-500/10 text-amber-500 border-amber-500/20",
};

const columns: ColumnDef<CallRecord>[] = [
  {
    key: "phone",
    label: "Phone",
    sortKey: "phone_number",
    cell: (call) => <span className="font-medium">{call.phone_number}</span>,
  },
  {
    key: "provider",
    label: "Provider",
    className: "text-xs font-bold tracking-tight text-muted-foreground uppercase",
    cell: (call) => call.provider,
  },
  {
    key: "status",
    label: "Status",
    sortKey: "status",
    cell: (call) => (
      <Badge
        variant="outline"
        className={cn("capitalize text-[10px] font-bold px-2 py-0.5", statusTone[call.status] ?? "")}
      >
        {call.status.replace(/_/g, " ")}
      </Badge>
    ),
  },
  {
    key: "runtime",
    label: "Runtime",
    className: "text-xs text-muted-foreground",
    cell: (call) => call.voice_runtime.replace(/_/g, " "),
  },
  {
    key: "score",
    label: "Score",
    className: "text-sm",
    cell: (call) =>
      typeof call.ai_evaluation?.overall_score === "number"
        ? `${call.ai_evaluation.overall_score}/10`
        : "—",
  },
  {
    key: "cost",
    label: "Cost",
    className: "text-sm",
    cell: (call) =>
      typeof call.cost_breakdown?.estimated_total_usd === "number"
        ? `$${call.cost_breakdown.estimated_total_usd.toFixed(4)}`
        : "—",
  },
  {
    key: "created",
    label: "Created",
    sortKey: "created_at",
    headerClassName: "text-right",
    className: "text-xs text-muted-foreground text-right",
    cell: (call) => new Date(call.created_at).toLocaleString(),
  },
  {
    key: "action",
    label: "Action",
    headerClassName: "text-right",
    className: "text-right",
    cell: (call) => (
      <Link
        to={`/calls/${call.id}`}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline"
      >
        View
        <ExternalLink className="h-3.5 w-3.5" />
      </Link>
    ),
  },
];

export function CallsTable({
  calls,
  sortBy,
  sortOrder,
  onSortChange,
  currentPage,
  pageSize,
  totalItems,
  onPageChange,
}: CallsTableProps) {
  return (
    <DataTable
      columns={columns}
      data={calls}
      rowKey={(c) => c.id}
      sortBy={sortBy}
      sortOrder={sortOrder}
      onSortChange={onSortChange}
      currentPage={currentPage}
      pageSize={pageSize}
      totalItems={totalItems}
      onPageChange={onPageChange}
      emptyIcon={<PhoneCall className="h-8 w-8 text-muted-foreground/50" />}
      emptyTitle="No calls yet"
      emptyDescription="Start an interview call from a parsed candidate to see history here."
    />
  );
}
