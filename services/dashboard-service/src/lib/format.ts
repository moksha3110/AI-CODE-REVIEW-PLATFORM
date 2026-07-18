import { formatDistanceToNow } from "date-fns";
import type { IssueSeverity } from "./types";

export function relativeTime(iso: string): string {
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}

export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

/** Badge variant per severity - matches shadcn's Badge `variant` prop. */
export function severityVariant(
  severity: IssueSeverity,
): "secondary" | "outline" | "destructive" {
  switch (severity) {
    case "critical":
    case "high":
      return "destructive";
    case "medium":
      return "outline";
    default:
      return "secondary";
  }
}

/** Text color class for a 1-10 complexity score - low is fine, high needs attention. */
export function complexityColor(score: number): string {
  if (score >= 7) return "text-red-600 dark:text-red-400";
  if (score >= 4) return "text-amber-600 dark:text-amber-400";
  return "text-emerald-600 dark:text-emerald-400";
}
