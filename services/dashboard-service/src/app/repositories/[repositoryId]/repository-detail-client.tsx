"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bug, ShieldAlert } from "lucide-react";
import { Protected } from "@/components/protected";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { QualityTrendsChart } from "@/components/quality-trends-chart";
import { ApiError, reviewApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { complexityColor, relativeTime, shortSha } from "@/lib/format";
import type { QualityTrendPoint, ReviewSummary } from "@/lib/types";

function RepositoryDetail({ repositoryId }: { repositoryId: string }) {
  const { accessToken, refreshAccessToken } = useAuth();
  const [reviews, setReviews] = useState<ReviewSummary[] | null>(null);
  const [trends, setTrends] = useState<QualityTrendPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    Promise.all([
      reviewApi.list(repositoryId, { limit: 50 }, accessToken, refreshAccessToken),
      reviewApi.qualityTrends(repositoryId, accessToken, refreshAccessToken),
    ])
      .then(([reviewPage, trendPoints]) => {
        setReviews(reviewPage.items);
        setTrends(trendPoints);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load this repository's reviews.");
      });
  }, [repositoryId, accessToken, refreshAccessToken]);

  const title = reviews?.[0]?.repository_full_name ?? "Repository";

  return (
    <div className="container mx-auto max-w-5xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">Review history and quality trends</p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Quality trend</CardTitle>
        </CardHeader>
        <CardContent>
          {trends === null && !error ? <Skeleton className="h-64 w-full" /> : <QualityTrendsChart points={trends ?? []} />}
        </CardContent>
      </Card>

      <div className="space-y-3">
        <h2 className="text-lg font-medium">Review history</h2>

        {reviews === null && !error && (
          <div className="space-y-3">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}

        {reviews?.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              No reviews yet - push a commit to this repository to trigger one.
            </CardContent>
          </Card>
        )}

        {reviews?.map((review) => (
          <Link key={review.id} href={`/reviews/${review.id}`}>
            <Card className="transition-colors hover:bg-accent/50">
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-mono text-sm">{shortSha(review.after_sha)}</p>
                  <p className="text-sm text-muted-foreground">
                    {review.ref.replace("refs/heads/", "")} &middot; {relativeTime(review.analyzed_at)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant="outline" className="gap-1">
                    <Bug className="h-3 w-3" />
                    {review.total_bug_count}
                  </Badge>
                  <Badge variant="outline" className="gap-1">
                    <ShieldAlert className="h-3 w-3" />
                    {review.total_security_issue_count}
                  </Badge>
                  <span className={`font-medium ${complexityColor(review.overall_complexity_score)}`}>
                    {review.overall_complexity_score.toFixed(1)}
                  </span>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function RepositoryDetailClient({ repositoryId }: { repositoryId: string }) {
  return (
    <Protected>
      <RepositoryDetail repositoryId={repositoryId} />
    </Protected>
  );
}
