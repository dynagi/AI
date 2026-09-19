"use client";

import { useMemo, useRef, useState } from "react";
import { Plus, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { Txn } from "@/lib/types";
import { dayKey, dayLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import TxnRow from "@/components/transactions/TxnRow";

const TYPES = [
  { v: "EXPENSE", l: "Expense" },
  { v: "SALARY", l: "Salary" },
  { v: "TRANSFER_IN", l: "Money received (from a person)" },
  { v: "REFUND", l: "Refund" },
  { v: "OTHER_INCOME", l: "Other income" },
  { v: "TRANSFER_OUT", l: "Transfer out" },
];

export default function TransactionsPage() {
  const { bump } = useLedger();
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const path = `/transactions?limit=500${category ? `&category=${encodeURIComponent(category)}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const { data, error, loading } = useLedgerData<{ transactions: Txn[]; categories: string[] }>(path);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ transaction_type: "EXPENSE", amount: "", merchant: "", description: "", category: "", timestamp: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const groups = useMemo(() => {
    const out: { key: string; label: string; items: Txn[] }[] = [];
    for (const t of data?.transactions ?? []) {
      const k = dayKey(t.timestamp);
      const last = out[out.length - 1];
      if (last && last.key === k) last.items.push(t);
      else out.push({ key: k, label: dayLabel(t.timestamp), items: [t] });
    }
    return out;
  }, [data]);

  async function addTxn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ balance: number | string; alerts: { title: string }[] }>("/transactions", {
        json: {
          transaction_type: form.transaction_type,
          amount: Number(form.amount),
          merchant: form.merchant || undefined,
          description: form.description || undefined,
          category: form.category || undefined,
          timestamp: form.timestamp ? `${form.timestamp}:00` : undefined,
        },
      });
      setMsg({ ok: true, text: `Saved. The balance and this cycle's totals were updated${r.alerts.length ? ` · ${r.alerts.map((a) => a.title).join(", ")}` : ""}.` });
      setForm({ ...form, amount: "", merchant: "", description: "" });
      bump();
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function importCsv(file: File) {
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api<{ inserted: number; duplicates: number; malformed: number; errors: string[] }>("/transactions/csv", { form: fd });
      setMsg({
        ok: r.inserted > 0 || r.duplicates > 0,
        text: `Imported ${r.inserted} transaction(s)` + (r.duplicates ? `, skipped ${r.duplicates} duplicate(s)` : "") + (r.malformed ? `, ${r.malformed} row(s) could not be read${r.errors[0] ? ` (${r.errors[0]})` : ""}` : "") + ".",
      });
      bump();
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function recategorize(id: string, cat: string) {
    await api(`/transactions/${id}/category`, { method: "PATCH", json: { category: cat } }).catch(() => {});
    bump();
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Transactions</h1>
          <p className="text-sm text-muted-foreground">Bank and manual data in one live timeline, with the balance after each entry.</p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
          <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={busy}><Upload className="h-4 w-4" /> Import CSV</Button>
          <Button onClick={() => setShowForm((v) => !v)}><Plus className="h-4 w-4" /> Add transaction</Button>
        </div>
      </div>

      {msg && <p className={`text-sm ${msg.ok ? "text-positive" : "text-negative"}`}>{msg.text}</p>}

      {showForm && (
        <Card>
          <CardContent className="pt-5">
            <form onSubmit={addTxn} className="grid gap-3 sm:grid-cols-6">
              <div className="space-y-1.5 sm:col-span-2">
                <Label>Type</Label>
                <Select value={form.transaction_type} onChange={(e) => setForm({ ...form, transaction_type: e.target.value })}>
                  {TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Amount (₹)</Label>
                <Input type="number" min="0.01" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div className="space-y-1.5 sm:col-span-3">
                <Label>Merchant / person</Label>
                <Input value={form.merchant} onChange={(e) => setForm({ ...form, merchant: e.target.value })} placeholder="Swiggy, Rahul…" />
              </div>
              <div className="space-y-1.5 sm:col-span-3">
                <Label>Description (optional)</Label>
                <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label>Category (optional)</Label>
                <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  <option value="">Auto-detect</option>
                  {(data?.categories ?? []).map((c) => <option key={c}>{c}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Date &amp; time (IST)</Label>
                <Input type="datetime-local" value={form.timestamp} onChange={(e) => setForm({ ...form, timestamp: e.target.value })} />
              </div>
              <div className="sm:col-span-6"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save transaction"}</Button></div>
            </form>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Input className="max-w-xs" placeholder="Search merchant or description" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select className="w-48" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {(data?.categories ?? []).map((c) => <option key={c}>{c}</option>)}
        </Select>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && !data && <p className="text-sm text-negative">{error}</p>}
      {!loading && groups.length === 0 && <p className="text-sm text-muted-foreground">No transactions yet. Add one, import a CSV, or connect the Demo Bank.</p>}

      <div className="space-y-5">
        {groups.map((g) => (
          <section key={g.key}>
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{g.label}</h2>
            <Card>
              <CardContent className="divide-y divide-border py-1">
                {g.items.map((t) => (
                  <div key={t.id} className="flex items-center gap-2">
                    <div className="min-w-0 flex-1"><TxnRow t={t} /></div>
                    {(t.transaction_type === "EXPENSE" || t.transaction_type === "REFUND") && (
                      <select
                        aria-label="Change category"
                        className="hidden w-28 rounded border border-input bg-background px-1.5 py-1 text-xs text-muted-foreground sm:block"
                        value={t.category}
                        onChange={(e) => recategorize(t.id, e.target.value)}
                      >
                        {(data?.categories ?? []).map((c) => <option key={c}>{c}</option>)}
                      </select>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          </section>
        ))}
      </div>
    </div>
  );
}
