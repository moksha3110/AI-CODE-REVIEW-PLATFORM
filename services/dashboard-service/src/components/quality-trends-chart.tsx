"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format } from "date-fns";
import type { QualityTrendPoint } from "@/lib/types";

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: QualityTrendPoint }[];
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-md border bg-popover p-3 text-sm shadow-md">
      <p className="font-medium">{format(new Date(point.analyzed_at), "MMM d, yyyy p")}</p>
      <p>Complexity: {point.overall_complexity_score.toFixed(1)}</p>
      <p>Bugs: {point.total_bug_count}</p>
      <p>Security issues: {point.total_security_issue_count}</p>
    </div>
  );
}

export function QualityTrendsChart({ points }: { points: QualityTrendPoint[] }) {
  if (points.length === 0) {
    return (
      <p className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        Not enough reviews yet to chart a trend.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={256}>
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="analyzed_at"
          tickFormatter={(value: string) => format(new Date(value), "MMM d")}
          className="text-xs"
          tick={{ fill: "currentColor" }}
        />
        <YAxis
          domain={[0, 10]}
          allowDecimals={false}
          className="text-xs"
          tick={{ fill: "currentColor" }}
        />
        <Tooltip content={<ChartTooltip />} />
        <Line
          type="monotone"
          dataKey="overall_complexity_score"
          stroke="var(--color-chart-2)"
          strokeWidth={2}
          dot={{ r: 3 }}
          name="Complexity"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
