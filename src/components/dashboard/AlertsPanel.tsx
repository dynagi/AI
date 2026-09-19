"use client";

import { AlertTriangle, Info, X } from "lucide-react";
import { api } from "@/lib/api";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE = {
  critical: "border-negative/40 bg-negative/10",
  warning: "border-warning/40 bg-warning/10",
  info: "border-primary/30 bg-primary/10",
};

export default function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  const { bump } = useLedger();
  const unread = alerts.filter((a) => !a.is_read).slice(0, 4);
  if (!unread.length) return null;

  async function dismiss(id: string) {
    await api(`/alerts/${id}/read`, { method: "POST" }).catch(() => {});
    bump();
  }

  return (
    <div className="space-y-2" aria-live="polite">
      {unread.map((a) => {
        const Icon = a.severity === "info" ? Info : AlertTriangle;
        return (
          <div key={a.id} className={cn("flex items-start gap-3 rounded-lg border p-3.5", TONE[a.severity])}>
            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", a.severity === "critical" ? "text-negative" : a.severity === "warning" ? "text-warning" : "text-primary")} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{a.title.replace(/^⚠️?\s*/, "")}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{a.message}</p>
            </div>
            <button aria-label="Dismiss" className="text-muted-foreground hover:text-foreground" onClick={() => dismiss(a.id)}>
              <X className="h-4 w-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
