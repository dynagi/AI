import { cn } from "@/lib/utils";

export function Progress({ value, tone = "primary", className }: { value: number; tone?: "primary" | "positive" | "warning" | "negative"; className?: string }) {
  const color = { primary: "bg-primary", positive: "bg-positive", warning: "bg-warning", negative: "bg-negative" }[tone];
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-secondary", className)} role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn("h-full rounded-full transition-all duration-500", color)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
