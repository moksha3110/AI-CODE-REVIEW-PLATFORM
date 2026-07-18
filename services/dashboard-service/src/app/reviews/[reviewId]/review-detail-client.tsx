"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bug, FileText, Gauge, Lightbulb, ShieldAlert } from "lucide-react";
import { Protected } from "@/components/protected";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError, reviewApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { complexityColor, relativeTime, severityVariant, shortSha } from "@/lib/format";
import type { FileReview, Issue, ReviewDetail as ReviewDetailType } from "@/lib/types";

function IssueList({ title, icon: Icon, issues }: { title: string; icon: typeof Bug; issues: Issue[] }) {
  if (issues.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <Icon className="h-4 w-4" />
        {title}
      </p>
      <ul className="space-y-1.5 pl-1">
        {issues.map((issue, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Badge variant={severityVariant(issue.severity)} className="mt-0.5 shrink-0">
              {issue.severity}
            </Badge>
            <span>
              {issue.description}
              {issue.line !== null && (
                <span className="ml-1 text-muted-foreground">(line {issue.line})</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FileReviewCard({ file }: { file: FileReview }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <CardTitle className="break-all font-mono text-sm font-medium">{file.file_path}</CardTitle>
          <span className={`flex shrink-0 items-center gap-1 text-sm font-medium ${complexityColor(file.complexity_score)}`}>
            <Gauge className="h-4 w-4" />
            {file.complexity_score.toFixed(1)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{file.summary}</p>

        {file.bugs.length === 0 &&
          file.security_issues.length === 0 &&
          file.optimizations.length === 0 &&
          file.documentation_suggestions.length === 0 && (
            <p className="text-sm text-muted-foreground">No issues found in this file.</p>
          )}

        <IssueList title="Bugs" icon={Bug} issues={file.bugs} />
        <IssueList title="Security issues" icon={ShieldAlert} issues={file.security_issues} />

        {file.optimizations.length > 0 && (
          <div className="space-y-2">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Lightbulb className="h-4 w-4" />
              Optimizations
            </p>
            <ul className="space-y-1.5 pl-1">
              {file.optimizations.map((opt, i) => (
                <li key={i} className="text-sm">
                  {opt.description}
                  {opt.line !== null && <span className="ml-1 text-muted-foreground">(line {opt.line})</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {file.documentation_suggestions.length > 0 && (
          <div className="space-y-2">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <FileText className="h-4 w-4" />
              Documentation
            </p>
            <ul className="list-disc space-y-1 pl-6 text-sm">
              {file.documentation_suggestions.map((doc, i) => (
                <li key={i}>{doc}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReviewDetailView({ reviewId }: { reviewId: string }) {
  const { accessToken, refreshAccessToken } = useAuth();
  const [review, setReview] = useState<ReviewDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    reviewApi
      .get(reviewId, accessToken, refreshAccessToken)
      .then(setReview)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load this review.");
      });
  }, [reviewId, accessToken, refreshAccessToken]);

  if (error) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-8">
        <Alert variant="destructive">
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="container mx-auto max-w-4xl space-y-4 px-4 py-8">
        <Skeleton className="h-8 w-96" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <div>
        <Link
          href={`/repositories/${review.repository_id}`}
          className="text-sm text-muted-foreground hover:underline"
        >
          &larr; {review.repository_full_name}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-xl font-semibold">{shortSha(review.after_sha)}</h1>
          <Badge variant="outline">{review.ref.replace("refs/heads/", "")}</Badge>
          <span className="text-sm text-muted-foreground">{relativeTime(review.analyzed_at)}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="py-4 text-center">
            <p className={`text-2xl font-semibold ${complexityColor(review.overall_complexity_score)}`}>
              {review.overall_complexity_score.toFixed(1)}
            </p>
            <p className="text-xs text-muted-foreground">Complexity</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 text-center">
            <p className="text-2xl font-semibold">{review.total_bug_count}</p>
            <p className="text-xs text-muted-foreground">Bugs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 text-center">
            <p className="text-2xl font-semibold">{review.total_security_issue_count}</p>
            <p className="text-xs text-muted-foreground">Security issues</p>
          </CardContent>
        </Card>
      </div>

      <Separator />

      <div className="space-y-4">
        <h2 className="text-lg font-medium">
          Files reviewed ({review.file_reviews.length})
        </h2>
        {review.file_reviews.map((file) => (
          <FileReviewCard key={file.file_path} file={file} />
        ))}
      </div>
    </div>
  );
}

export function ReviewDetailClient({ reviewId }: { reviewId: string }) {
  return (
    <Protected>
      <ReviewDetailView reviewId={reviewId} />
    </Protected>
  );
}
