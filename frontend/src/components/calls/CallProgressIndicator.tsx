import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, PhoneCall } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { CallRecord } from "@/lib/calls";
import { getWebSocketBaseUrl } from "@/lib/api";

import { useCallWebSocket } from "@/hooks/useCallWebSocket";

interface CallProgressIndicatorProps {
  callId: string;
  initialCall?: CallRecord;
  onUpdate?: (call: CallRecord) => void;
}

const steps = ["queued", "ringing", "in_progress", "completed"] as const;

export function CallProgressIndicator({
  callId,
  initialCall,
  onUpdate,
}: CallProgressIndicatorProps) {
  const { connectionState, lastCall } = useCallWebSocket(callId, onUpdate);
  const [internalCall, setInternalCall] = useState<CallRecord | null>(initialCall ?? null);

  const call = lastCall ?? internalCall;


  const currentStepIndex = useMemo(() => {
    if (!call) return 0;
    const index = steps.indexOf((call.status as (typeof steps)[number]) || "queued");
    return index === -1 ? 0 : index;
  }, [call]);

  if (!call) {
    return (
      <Card className="border-border/50 bg-card/70">
        <CardContent className="flex items-center gap-3 p-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Waiting for call updates...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-border/50 bg-card/70">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 font-medium">
            <PhoneCall className="h-4 w-4 text-primary" />
            Live Call Progress
          </div>
          <Badge variant="outline" className="capitalize">
            {call.status.replace("_", " ")}
          </Badge>
        </div>

        <div className="grid grid-cols-4 gap-2">
          {steps.map((step, index) => {
            const isActive = index <= currentStepIndex;
            return (
              <div key={step} className="space-y-2">
                <div className={`h-2 rounded-full ${isActive ? "bg-primary" : "bg-muted"}`} />
                <div className="text-[11px] font-medium capitalize text-muted-foreground">
                  {step.replace("_", " ")}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{call.phone_number}</span>
          <span>{connectionState === "live" ? "Live updates" : "Updates paused"}</span>
        </div>
      </CardContent>
    </Card>
  );
}
