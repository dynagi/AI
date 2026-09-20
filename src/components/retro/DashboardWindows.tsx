"use client";

import { useState } from "react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLedgerData } from "@/hooks/useLedgerData";
import type { Txn } from "@/lib/types";
import { dateShort, inr, num, signedInr, type Money } from "@/lib/format";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { RetroWindow } from "./Window";
import { Robot } from "./Sprite";
import { useFinPilotChat } from "./useFinPilotChat";

const PALETTE = ["#B79AEF", "#FFE04D", "#7FE3B5", "#FF9EC4", "#7FB8FF", "#FFB066", "#FFFFFF", "#C3A6F5"];

export function SpendingOverview({ categories }: { categories: { category: string; total: Money }[] }) {
  const rows = categories.filter((c) => num(c.total) > 0).slice(0, 7).map((c) => ({ name: c.category, value: num(c.total) }));
  const total = rows.reduce((s, r) => s + r.value, 0);
  return (
    <RetroWindow title="Spending Overview" bodyClassName="p-3">
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm">No spending recorded in this cycle yet.</p>
      ) : (
        <div className="flex flex-col items-center gap-4 sm:flex-row">
          <div className="retro-chart h-[190px] w-[190px] shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={rows} dataKey="value" nameKey="name" outerRadius={90} stroke="#000" strokeWidth={2} isAnimationActive={false}>
                  {rows.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#FFF29A", border: "2px solid #000", borderRadius: 0, fontSize: 12, color: "#000" }} formatter={(v: number) => inr(v)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="w-full min-w-0 flex-1 space-y-1 text-xs">
            {rows.map((r, i) => (
              <li key={r.name} className="flex items-center gap-2">
                <span className="h-3 w-3 shrink-0 border-2 border-black" style={{ background: PALETTE[i % PALETTE.length] }} />
                <span className="min-w-0 flex-1 truncate">{r.name}</span>
                <span className="w-9 text-right">{Math.round((r.value / total) * 100)}%</span>
                <span className="w-20 text-right tabular-nums">{inr(r.value)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </RetroWindow>
  );
}

interface TrendRow { label: string; expenses: Money }

export function SpendingTrend() {
  const { data } = useLedgerData<{ cycles: TrendRow[] }>("/trends?limit=6");
  const rows = (data?.cycles ?? []).map((c) => ({ label: c.label.split(/\s*[–-]\s*/)[0].replace(/\s*\d{4}$/, ""), full: c.label, expenses: num(c.expenses) }));
  const last = rows[rows.length - 1];
  const prev = rows[rows.length - 2];
  const diff = last && prev && prev.expenses > 0 ? ((last.expenses - prev.expenses) / prev.expenses) * 100 : null;
  return (
    <RetroWindow title="Spending Trend">
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm">Trend appears after your first cycle.</p>
      ) : (
        <div className="retro-chart">
          <ResponsiveContainer width="100%" height={170}>
            <BarChart data={rows} margin={{ left: -10, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="#cfcfcf" strokeDasharray="2 2" />
              <XAxis dataKey="label" tick={{ fill: "#000", fontSize: 11 }} axisLine={{ stroke: "#000" }} tickLine={false} interval={0} />
              <YAxis tick={{ fill: "#000", fontSize: 11 }} axisLine={{ stroke: "#000" }} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}K` : `${v}`)} />
              <Tooltip cursor={{ fill: "#f0f0f0" }} contentStyle={{ background: "#FFF29A", border: "2px solid #000", borderRadius: 0, fontSize: 12, color: "#000" }} labelFormatter={(_, p) => p?.[0]?.payload?.full ?? ""} formatter={(v: number) => [inr(v), "Spent"]} />
              <Bar dataKey="expenses" fill="#9B72E8" stroke="#000" strokeWidth={2} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {diff !== null && (
        <div className="retro-note mt-2 flex items-center gap-2 p-2 text-xs">
          <span aria-hidden className="text-lg">{diff <= 0 ? "⬇️" : "⬆️"}</span>
          <div>
            <p className="font-bold">{Math.abs(diff).toFixed(0)}% {diff <= 0 ? "lower" : "higher"} than the previous cycle</p>
            <p>{diff <= 0 ? "Great job! " : ""}You spent {inr(Math.abs(last.expenses - prev.expenses))} {diff <= 0 ? "less" : "more"} than {prev.full}.</p>
          </div>
        </div>
      )}
    </RetroWindow>
  );
}

export function RecentTransactions({ txns }: { txns: Txn[] }) {
  return (
    <RetroWindow title="Recent Transactions" right={<Link href="/transactions" className="mr-1 text-[11px] font-bold underline">View all</Link>} bodyClassName="p-2">
      {txns.length === 0 ? (
        <p className="p-3 text-sm">No transactions yet.</p>
      ) : (
        <div className="retro-sunken max-h-[220px] overflow-auto">
          <table className="w-full min-w-[520px] text-xs">
            <thead>
              <tr className="sticky top-0 bg-[#e8e8e8] text-left">
                <th className="px-2 py-1">Date</th><th className="px-2 py-1">Merchant</th><th className="px-2 py-1">Category</th><th className="px-2 py-1 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {txns.slice(0, 8).map((t) => {
                const credit = num(t.signed_amount) > 0;
                return (
                  <tr key={t.id} className="border-t border-black/20 hover:bg-[#f2ecfd]">
                    <td className="whitespace-nowrap px-2 py-1.5">{dateShort(t.timestamp)}</td>
                    <td className="max-w-[200px] truncate px-2 py-1.5"><Link href={`/transactions`} className="hover:underline">{t.merchant || t.description}</Link></td>
                    <td className="px-2 py-1.5">{t.category}</td>
                    <td className={cn("whitespace-nowrap px-2 py-1.5 text-right font-bold tabular-nums", credit ? "text-[#15803d]" : "text-[#e00000]")}>{signedInr(t.signed_amount)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </RetroWindow>
  );
}

const CHAT_SUGGESTIONS = [
  "Where did I spend the most this month?",
  "Which subscriptions am I paying for?",
  "What expenses increased compared with last month?",
  "How much of my income am I saving?",
  "Help me create a budget for next month.",
];

export function AskWindow() {
  const { msgs, busy, error, send } = useFinPilotChat();
  const [input, setInput] = useState("");
  const submit = (t: string) => { send(t); setInput(""); };
  return (
    <RetroWindow title="Ask Penny.exe" bodyClassName="p-3">
      <div className="mb-2 flex items-end gap-2">
        <Robot />
        <div className="retro-note p-2 text-xs">Hi, I&apos;m Penny!<br />Ask me anything about your money.</div>
      </div>
      {msgs.length > 0 && (
        <div className="retro-sunken mb-2 max-h-56 space-y-2 overflow-y-auto p-2 text-xs" aria-live="polite">
          {msgs.map((m, i) => (
            <div key={i} className={cn("whitespace-pre-wrap border-2 border-black p-1.5", m.role === "user" ? "ml-6 bg-[#e3d8fa]" : "mr-6 bg-white")}>{m.content}</div>
          ))}
          {busy && <p className="blink">Penny is thinking…</p>}
        </div>
      )}
      {error && <p className="mb-2 border-2 border-black bg-[#ffd0d0] p-1.5 text-xs">{error}</p>}
      {msgs.length === 0 && (
        <div className="mb-2 space-y-1.5">
          {CHAT_SUGGESTIONS.map((s) => (
            <button key={s} className="retro-bevel flex w-full items-center justify-between gap-2 bg-cream px-2 py-1.5 text-left text-xs hover:bg-[#fff7b8]" onClick={() => submit(s)} disabled={busy}>
              <span>{s}</span><span aria-hidden>›</span>
            </button>
          ))}
        </div>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(input); }}>
        <input className="retro-sunken h-9 min-w-0 flex-1 px-2 text-xs" placeholder="Type your question..." value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <button className="retro-bevel h-9 px-3 text-xs font-bold" disabled={busy || !input.trim()}>Send</button>
      </form>
    </RetroWindow>
  );
}

export function QuickActions() {
  const items = [
    { icon: "🎯", label: "Set a Goal", href: "/goals?new=1" },
    { icon: "📄", label: "Create Budget", href: "/budgets" },
    { icon: "➕", label: "Add Transaction", href: "/transactions?add=1" },
    { icon: "📑", label: "Generate Report", href: "/summaries" },
  ];
  return (
    <RetroWindow title="Quick Actions" bodyClassName="p-0">
      <div className="grid grid-cols-4">
        {items.map((it, i) => (
          <Link key={it.label} href={it.href} className={cn("flex flex-col items-center gap-1 px-1 py-3 text-center text-[11px] leading-tight hover:bg-white", i > 0 && "border-l-2 border-black")}>
            <span aria-hidden className="text-2xl">{it.icon}</span>
            {it.label}
          </Link>
        ))}
      </div>
    </RetroWindow>
  );
}

export function ProgressWindow({ percent, message }: { percent: number | null; message: string }) {
  const p = percent ?? 0;
  return (
    <div className="relative">
      <RetroWindow title="Progress.exe">
        <p className="mb-2 text-xs">{message}</p>
        <div className="flex items-center gap-2">
          <Progress className="flex-1" value={p} tone={p > 100 ? "negative" : p > 80 ? "warning" : "primary"} />
          <span className="font-bold text-[#5b3bb5] text-xs">{Math.round(p)}%</span>
        </div>
        <Link href="/comparisons" className="retro-bevel mt-3 inline-block px-3 py-1 text-xs font-bold">View Details</Link>
      </RetroWindow>
    </div>
  );
}
