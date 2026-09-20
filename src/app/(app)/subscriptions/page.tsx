"use client";

import { useLedgerData } from "@/hooks/useLedgerData";
import { dateShort, inr, num, type Money } from "@/lib/format";
import { RetroWindow } from "@/components/retro/Window";

interface Recurring {
  id: string;
  merchant: string;
  category: string;
  average_amount: Money;
  frequency: string;
  last_payment: string;
  next_expected_payment: string;
  confidence: Money;
  occurrences: number;
}

interface Resp {
  payments: Recurring[];
  upcoming: { total: Money; items: { merchant: string; amount: Money; expected_at: string }[] } | null;
}

const PER_MONTH: Record<string, number> = { weekly: 52 / 12, monthly: 1, quarterly: 1 / 3, yearly: 1 / 12 };

export default function SubscriptionsPage() {
  const { data, loading, error } = useLedgerData<Resp>("/recurring");
  if (loading) return <p className="text-sm">Loading recurring payments…</p>;
  if (error && !data) return <p className="text-sm font-bold text-[#e00000]">{error}</p>;
  const rows = data?.payments ?? [];
  const monthly = rows.reduce((s, r) => s + num(r.average_amount) * (PER_MONTH[r.frequency] ?? 1), 0);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <RetroWindow title="Subscriptions.exe" focused closable={false}>
        <p className="text-sm">
          Payments detected from your own ledger (at least 3 evenly spaced payments to the same merchant). About <b>{inr(monthly)}</b> per month across {rows.length} recurring payment{rows.length === 1 ? "" : "s"}.
        </p>
      </RetroWindow>
      <RetroWindow title="Recurring payments" bodyClassName="p-2">
        {rows.length === 0 ? (
          <p className="p-3 text-sm">No recurring payments detected yet.</p>
        ) : (
          <div className="retro-sunken overflow-x-auto">
            <table className="w-full min-w-[560px] text-xs">
              <thead>
                <tr className="bg-[#e8e8e8] text-left">
                  <th className="px-2 py-1">Merchant</th><th className="px-2 py-1">Category</th><th className="px-2 py-1">Every</th>
                  <th className="px-2 py-1">Next expected</th><th className="px-2 py-1 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-black/20">
                    <td className="px-2 py-1.5 font-bold">{r.merchant}</td>
                    <td className="px-2 py-1.5">{r.category}</td>
                    <td className="px-2 py-1.5 capitalize">{r.frequency}</td>
                    <td className="px-2 py-1.5">{dateShort(r.next_expected_payment)}</td>
                    <td className="px-2 py-1.5 text-right font-bold tabular-nums">{inr(r.average_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </RetroWindow>
      {data?.upcoming && data.upcoming.items.length > 0 && (
        <RetroWindow title="Due in the next 30 days" tone="yellow">
          <ul className="space-y-1 text-sm">
            {data.upcoming.items.map((i) => (
              <li key={i.merchant + i.expected_at} className="flex justify-between"><span>{i.merchant} · {dateShort(i.expected_at)}</span><span className="tabular-nums">{inr(i.amount)}</span></li>
            ))}
            <li className="flex justify-between border-t-2 border-black pt-1 font-bold"><span>Total</span><span className="tabular-nums">{inr(data.upcoming.total)}</span></li>
          </ul>
        </RetroWindow>
      )}
    </div>
  );
}
