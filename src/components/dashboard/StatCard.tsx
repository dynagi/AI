import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function StatCard({
  label, value, sub, tone = "default", big = false,
}: { label: string; value: string; sub?: React.ReactNode; tone?: "default" | "positive" | "negative" | "warning"; big?: boolean }) {
  const color = { default: "text-foreground", positive: "text-positive", negative: "text-negative", warning: "text-warning" }[tone];
  return (
    <Card className="p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-2 font-semibold tabular-nums tracking-tight", big ? "text-3xl" : "text-2xl", color)}>{value}</p>
      {sub && <div className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
}
