import { Link } from "react-router-dom";
import { ExternalLink, PhoneCall } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CallRecord } from "@/lib/calls";

interface CallsTableProps {
  calls: CallRecord[];
}

export function CallsTable({ calls }: CallsTableProps) {
  if (calls.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/50 bg-muted/20 py-12 text-center">
        <PhoneCall className="mx-auto mb-4 h-12 w-12 text-muted-foreground/50" />
        <h3 className="text-lg font-semibold">No calls yet</h3>
        <p className="text-muted-foreground">Start an interview call from a parsed candidate to see history here.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border/50 bg-card/30 shadow-sm backdrop-blur-sm">
      <Table>
        <TableHeader className="bg-muted/50">
          <TableRow>
            <TableHead className="font-semibold">Phone</TableHead>
            <TableHead className="font-semibold">Status</TableHead>
            <TableHead className="font-semibold">Score</TableHead>
            <TableHead className="font-semibold">Created</TableHead>
            <TableHead className="text-right font-semibold">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {calls.map((call) => (
            <TableRow key={call.id} className="transition-colors hover:bg-muted/30">
              <TableCell className="font-medium">{call.phone_number}</TableCell>
              <TableCell>
                <Badge variant="outline" className="capitalize">
                  {call.status.replace("_", " ")}
                </Badge>
              </TableCell>
              <TableCell>
                {typeof call.ai_evaluation?.overall_score === "number"
                  ? `${call.ai_evaluation.overall_score}/10`
                  : "—"}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {new Date(call.created_at).toLocaleString()}
              </TableCell>
              <TableCell className="text-right">
                <Link
                  to={`/calls/${call.id}`}
                  className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                >
                  View
                  <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
