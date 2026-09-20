import { Badge } from "@/components/ui/badge";
import type { GoalStatus } from "@/lib/types";

export function GoalStatusBadge({ status, reason }: { status: GoalStatus; reason?: string | null }) {
  switch (status) {
    case "ON_TRACK":
      return <Badge variant="positive">On track</Badge>;
    case "AT_RISK":
      return <Badge variant="warning">At risk</Badge>;
    case "BEHIND":
      return <Badge variant="negative">Behind</Badge>;
    case "COMPLETED":
      return <Badge variant="positive">Completed</Badge>;
    case "PAUSED":
      return <Badge variant="outline">Paused</Badge>;
    default:
      return <Badge variant="outline">{reason === "insufficient_history" ? "Not enough history" : "No status"}</Badge>;
  }
}

export const GOAL_TYPE_LABEL: Record<string, string> = {
  PURCHASE: "Purchase",
  EMERGENCY_FUND: "Emergency fund",
  TRAVEL: "Travel",
  EDUCATION: "Education",
  CUSTOM: "Custom",
};

export function goalTone(status: GoalStatus): "primary" | "positive" | "warning" | "negative" {
  if (status === "AT_RISK") return "warning";
  if (status === "BEHIND") return "negative";
  if (status === "COMPLETED" || status === "ON_TRACK") return "positive";
  return "primary";
}
