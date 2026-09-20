"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inr, num, type Money } from "@/lib/format";

const COLORS = ["#9B72E8", "#7FE3B5", "#FFE04D", "#FF8FA3", "#7FB8FF", "#FFB066", "#C3A6F5", "#5CC98F"];

export default function CategoryBars({ data }: { data: { category: string; total: Money }[] }) {
  if (!data.length) return <p className="py-10 text-center text-sm">No spending recorded in this cycle yet.</p>;
  const rows = data.slice(0, 8).map((d) => ({ category: d.category, total: num(d.total) }));
  return (
    <div className="retro-chart retro-sunken p-2">
      <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 34)}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid horizontal={false} stroke="#cfcfcf" strokeDasharray="2 2" />
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="category" width={96} tick={{ fill: "#000", fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "#f0f0f0" }}
            contentStyle={{ background: "#FFF29A", border: "2px solid #000", borderRadius: 0, fontSize: 12, color: "#000" }}
            formatter={(v: number) => [inr(v), "Spent"]}
          />
          <Bar dataKey="total" radius={0} stroke="#000" strokeWidth={2} isAnimationActive={false}>
            {rows.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
