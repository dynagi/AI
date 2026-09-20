"use client";

import { useState } from "react";

const DOW = ["S", "M", "T", "W", "T", "F", "S"];

/** Month calendar; days that have a transaction get a red dot. `marks` are YYYY-MM-DD strings. */
export function RetroCalendar({ marks = [] }: { marks?: string[] }) {
  const today = new Date();
  const [cursor, setCursor] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const y = cursor.getFullYear();
  const m = cursor.getMonth();
  const first = new Date(y, m, 1).getDay();
  const days = new Date(y, m + 1, 0).getDate();
  const key = (d: number) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const markSet = new Set(marks);
  const cells: (number | null)[] = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span aria-hidden className="text-2xl">🗓️</span>
        <div className="retro-sunken flex flex-1 items-center justify-between px-1 py-0.5">
          <button className="retro-bevel h-6 w-6 text-sm" aria-label="Previous month" onClick={() => setCursor(new Date(y, m - 1, 1))}>◀</button>
          <span className="font-pixel text-sm font-bold">{cursor.toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</span>
          <button className="retro-bevel h-6 w-6 text-sm" aria-label="Next month" onClick={() => setCursor(new Date(y, m + 1, 1))}>▶</button>
        </div>
      </div>
      <div className="grid grid-cols-7 gap-px text-center text-[11px]">
        {DOW.map((d, i) => <span key={i} className="font-bold">{d}</span>)}
        {cells.map((d, i) => {
          const isToday = d === today.getDate() && m === today.getMonth() && y === today.getFullYear();
          return (
            <span key={i} className={`relative py-0.5 ${isToday ? "border-2 border-black bg-[#B79AEF] font-bold" : ""}`}>
              {d ?? ""}
              {d && markSet.has(key(d)) && <span className="absolute bottom-0 left-1/2 h-1 w-1 -translate-x-1/2 bg-[#e00000]" />}
            </span>
          );
        })}
      </div>
    </div>
  );
}
