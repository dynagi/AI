"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inr, num, type Money } from "@/lib/format";

const COLORS = ["#6d86ff", "#8ea2ff", "#4ade80", "#facc15", "#f472b6", "#a78bfa", "#38bdf8", "#fb923c"];

export default function CategoryBars({ data }: { data: { category: string; total: Money }[] }) {
  if (!data.length) return <p className="py-10 text-center text-sm text-muted-foreground">No spending recorded in this cycle yet.</p>;
  const rows = data.slice(0, 8).map((d) => ({ category: d.category, total: num(d.total) }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 34)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 24 }}>
        <CartesianGrid horizontal={false} stroke="hsl(222 16% 18%)" />
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="category" width={96} tick={{ fill: "hsl(220 10% 70%)", fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip
          cursor={{ fill: "hsl(222 18% 14%)" }}
          contentStyle={{ background: "hsl(222 22% 10%)", border: "1px solid hsl(222 16% 22%)", borderRadius: 8, fontSize: 12 }}
          formatter={(v: number) => [inr(v), "Spent"]}
        />
        <Bar dataKey="total" radius={[0, 6, 6, 0]} isAnimationActive={false}>
          {rows.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
