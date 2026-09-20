"use client";

import { api } from "@/lib/api";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE = { critical: "bg-[#ffd0d0]", warning: "bg-[#FFF29A]", info: "bg-[#e3d8fa]" };
const ICON = { critical: "⛔", warning: "⚠️", info: "ℹ️" };

export default function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  const { bump } = useLedger();
  const unread = alerts.filter((a) => !a.is_read).slice(0, 4);
  if (!unread.length) return null;

  async function dismiss(id: string) {
    await api(`/alerts/${id}/read`, { method: "POST" }).catch(() => {});
    bump();
  }

  return (
    <div className="retro-window" aria-live="polite">
      <div className="retro-titlebar">
        <span className="font-pixel text-[13px] font-semibold uppercase">⚠ Alerts ({unread.length})</span>
      </div>
      <div className="space-y-1.5 p-2">
        {unread.map((a) => (
          <div key={a.id} className={cn("flex items-start gap-2 border-2 border-black px-2 py-1.5", TONE[a.severity])}>
            <span aria-hidden>{ICON[a.severity]}</span>
            <div className="min-w-0 flex-1">
              <p className="text-xs"><b>{a.title.replace(/^⚠️?\s*/, "")}.</b> {a.message}</p>
            </div>
            <button aria-label="Dismiss" className="retro-winbtn shrink-0" onClick={() => dismiss(a.id)}>×</button>
          </div>
        ))}
      </div>
    </div>
  );
}
