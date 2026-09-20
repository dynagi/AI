"use client";

import { useLedgerData } from "@/hooks/useLedgerData";
import { RetroWindow } from "@/components/retro/Window";
import { TONES, useTone } from "@/lib/tone";
import { cn } from "@/lib/utils";
import { num } from "@/lib/format";

interface Briefing {
  greeting: string;
  streak: { available: boolean; current_streak: number; best_streak: number; badge: string | null; no_spend_days_30: number };
  items: { kind: string; level: string; icon: string; text: string }[];
}

const BG: Record<string, string> = { SAFE: "bg-white", WATCH: "bg-[#FFF29A]", AT_RISK: "bg-[#ffdcb3]", SHORTFALL: "bg-[#ffd0d0]" };

/** Today's briefing: every line and number comes from GET /briefing (the same data as the agent's tools). */
export default function BriefingCard() {
  const { tone, setTone } = useTone();
  const { data, error } = useLedgerData<Briefing>(`/briefing?tone=${tone}`);

  const toggle = (
    <span className="flex gap-1" role="group" aria-label="Assistant tone">
      {TONES.map((t) => (
        <button
          key={t.id}
          onClick={() => setTone(t.id)}
          aria-pressed={tone === t.id}
          className={cn("retro-bevel px-1.5 py-0.5 text-[11px] font-bold", tone === t.id && "bg-[#e3d8fa]")}
        >
          {t.label}
        </button>
      ))}
    </span>
  );

  return (
    <RetroWindow title="Today's Briefing" right={toggle} bodyClassName="space-y-2 p-3">
      {error && !data && <p className="text-xs">{error}</p>}
      {data && (
        <>
          <p className="text-sm font-bold">{data.greeting}</p>
          {data.streak.available && (
            <p className="text-xs">
              🔥 Streak <b>{data.streak.current_streak}</b> · best <b>{data.streak.best_streak}</b> · no-spend days (30d){" "}
              <b>{num(data.streak.no_spend_days_30)}</b>
              {data.streak.badge && <> · 🏅 {data.streak.badge}</>}
            </p>
          )}
          <ul className="space-y-1.5">
            {data.items.map((i, idx) => (
              <li key={idx} className={cn("flex gap-2 border-2 border-black px-2 py-1.5 text-sm", BG[i.level] ?? "bg-white")}>
                <span aria-hidden>{i.icon}</span>
                <span>{i.text}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </RetroWindow>
  );
}
