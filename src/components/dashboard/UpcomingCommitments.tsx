"use client";

import { useState } from "react";
import type { CashflowRisk, RiskLevel } from "@/lib/types";
import { inr, num, signedInr } from "@/lib/format";
import { RetroWindow } from "@/components/retro/Window";
import { cn } from "@/lib/utils";

// Display only: the risk level, amounts, dates and wording all come from the backend (/dashboard -> cashflow_risk).
const LEVEL: Record<RiskLevel, { icon: string; label: string; bg: string }> = {
  SAFE: { icon: "🟢", label: "Safe", bg: "bg-[#d9f2d9]" },
  WATCH: { icon: "🟡", label: "Watch", bg: "bg-[#FFF29A]" },
  AT_RISK: { icon: "🟠", label: "At risk", bg: "bg-[#ffdcb3]" },
  SHORTFALL: { icon: "🔴", label: "Shortfall", bg: "bg-[#ffd0d0]" },
};

function dueText(days: number) {
  return days <= 0 ? "Due today" : days === 1 ? "Due tomorrow" : `Due in ${days} days`;
}

export default function UpcomingCommitments({ risk }: { risk: CashflowRisk }) {
  const [open, setOpen] = useState(false);
  const lv = LEVEL[risk.risk_level];
  const payments = risk.upcoming_payments;

  if (payments.length === 0) {
    return (
      <RetroWindow title="Upcoming Money Commitments">
        <p className="text-sm">{risk.warning_message}</p>
      </RetroWindow>
    );
  }

  return (
    <RetroWindow title="🔔 Upcoming Money Commitments" bodyClassName="space-y-3 p-3">
      <p className="text-sm">
        <span className="text-xl font-bold tabular-nums">{inr(risk.upcoming_amount)}</span> upcoming in the next {risk.horizon_days} days
      </p>

      <ul className="divide-y divide-black/20 text-sm">
        {payments.slice(0, 5).map((p, i) => (
          <li key={`${p.merchant}-${p.due_at}-${i}`} className="flex items-center justify-between gap-3 py-1.5">
            <div className="min-w-0">
              <p className="truncate font-bold">{p.merchant}</p>
              <p className="text-xs">Due {p.due_label} · {dueText(p.days_remaining).replace("Due ", "")}{p.priority === "high" ? " · essential" : ""}</p>
            </div>
            <span className="tabular-nums font-bold">{inr(p.amount)}</span>
          </li>
        ))}
        {payments.length > 5 && <li className="py-1.5 text-xs">+ {payments.length - 5} more</li>}
      </ul>

      <div className={cn("space-y-1.5 border-2 border-black p-3", lv.bg)} role="status">
        <p className="text-sm font-bold">{lv.icon} {lv.label.toUpperCase()} — {risk.headline}</p>
        <p className="text-sm">{risk.warning_message}</p>
        {risk.suggested_action && <p className="text-xs italic">{risk.suggested_action}</p>}
        <button className="retro-bevel px-3 py-1 text-xs font-bold" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Hide Details" : "View Details"}
        </button>
      </div>

      {open && (
        <div className="space-y-3">
          <ol className="text-sm">
            {risk.timeline.map((t, i) => (
              <li key={i}>
                {i > 0 && <p className="pl-3 text-muted-foreground" aria-hidden>↓</p>}
                <div className={cn("flex items-baseline justify-between gap-3 border-2 border-black px-2 py-1", t.shortfall ? "bg-[#ffd0d0]" : t.kind === "income" ? "bg-[#d9f2d9]" : "bg-white")}>
                  <span>
                    <b>{t.date_label}</b>{" "}
                    {t.kind === "start" ? "Balance now" : `${signedInr(t.amount)} ${t.label}`}
                  </span>
                  <span className="text-xs tabular-nums">{t.kind === "start" ? inr(t.balance_after) : `→ ${inr(t.balance_after)}`}</span>
                </div>
              </li>
            ))}
            <li>
              <p className="pl-3 text-muted-foreground" aria-hidden>↓</p>
              <div className={cn("border-2 border-black px-2 py-1 font-bold", num(risk.projected_balance) < 0 ? "bg-[#ffd0d0]" : "bg-white")}>
                Projected: {inr(risk.projected_balance)}
              </div>
            </li>
          </ol>

          <div className="space-y-1 text-xs">
            <p>Safety buffer: {inr(risk.safety_buffer)}</p>
            <p>{risk.savings_impact.at_risk ? "⚠️ " : ""}{risk.savings_impact.message}</p>
            <p>{risk.budget_impact.at_risk ? "⚠️ " : ""}{risk.budget_impact.message}</p>
            <p className="text-muted-foreground">FinPilot only warns you. It never makes payments, cancels subscriptions or moves money.</p>
          </div>
        </div>
      )}
    </RetroWindow>
  );
}
