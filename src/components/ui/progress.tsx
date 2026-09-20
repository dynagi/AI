import { cn } from "@/lib/utils";

const FILL = { primary: "bg-[#9B72E8]", positive: "bg-[#16A34A]", warning: "bg-[#F5C400]", negative: "bg-[#FF3333]" };
const SEGMENTS = 20;

/** Classic segmented progress bar: 20 blocks in a sunken trough. */
export function Progress({ value, tone = "primary", className }: { value: number; tone?: "primary" | "positive" | "warning" | "negative"; className?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  const filled = Math.round((clamped / 100) * SEGMENTS);
  return (
    <div
      className={cn("retro-sunken flex h-6 w-full gap-[2px] p-[3px]", className)}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {Array.from({ length: SEGMENTS }, (_, i) => (
        <span key={i} className={cn("h-full flex-1", i < filled ? FILL[tone] : "bg-transparent")} />
      ))}
    </div>
  );
}
