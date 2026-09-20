import { cn } from "@/lib/utils";

const TONE = { default: "text-black", positive: "text-[#15803d]", negative: "text-[#e00000]", warning: "text-[#8a5a00]" };

/** Metric window: small title bar, big pixel-font number. */
export default function StatCard({
  label, value, sub, tone = "default", big = false, icon,
}: { label: string; value: string; sub?: React.ReactNode; tone?: "default" | "positive" | "negative" | "warning"; big?: boolean; icon?: React.ReactNode }) {
  return (
    <div className="retro-window">
      <div className="retro-titlebar">
        <span className="font-pixel text-[12px] font-semibold uppercase tracking-wider">{label}</span>
        <span className="retro-winbtn" aria-hidden>–</span>
      </div>
      <div className="p-3">
        <div className="flex items-center gap-3">
          {icon}
          <p className={cn("font-vt leading-none tabular-nums", big ? "text-[40px]" : "text-[36px]", TONE[tone])}>{value}</p>
        </div>
        {sub && <div className="mt-1.5 space-y-0.5 text-xs text-black/70">{sub}</div>}
      </div>
    </div>
  );
}
