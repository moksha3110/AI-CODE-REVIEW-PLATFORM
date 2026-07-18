"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Lock, Plus } from "lucide-react";
import { Protected } from "@/components/protected";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError, repositoryApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { relativeTime } from "@/lib/format";
import type { Repository } from "@/lib/types";
import { GithubIcon } from "@/components/icons";

function RepositoriesList() {
  const { accessToken, refreshAccessToken } = useAuth();
  const [repositories, setRepositories] = useState<Repository[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    repositoryApi
      .list(accessToken, refreshAccessToken)
      .then(setRepositories)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load repositories.");
      });
  }, [accessToken, refreshAccessToken]);

  const handleConnect = useCallback(async () => {
    setConnecting(true);
    try {
      const { install_url } = await repositoryApi.getInstallUrl(accessToken, refreshAccessToken);
      window.location.href = install_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start installation.");
      setConnecting(false);
    }
  }, [accessToken, refreshAccessToken]);

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Repositories</h1>
        <Button onClick={handleConnect} disabled={connecting}>
          <Plus className="mr-2 h-4 w-4" />
          Connect a repository
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {repositories === null && !error && (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}

      {repositories?.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
            <GithubIcon className="h-8 w-8" />
            <p>No repositories connected yet.</p>
            <Button variant="outline" onClick={handleConnect} disabled={connecting}>
              Connect your first repository
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {repositories?.map((repo) => (
          <Link key={repo.id} href={`/repositories/${repo.id}`}>
            <Card className="transition-colors hover:bg-accent/50">
              <CardContent className="flex items-center justify-between py-4">
                <div className="flex items-center gap-3">
                  <GithubIcon className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">{repo.full_name}</p>
                    <p className="text-sm text-muted-foreground">
                      Default branch: {repo.default_branch} &middot; Updated{" "}
                      {relativeTime(repo.updated_at)}
                    </p>
                  </div>
                </div>
                {repo.is_private && (
                  <Lock className="h-4 w-4 text-muted-foreground" aria-label="Private repository" />
                )}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function RepositoriesPage() {
  return (
    <Protected>
      <RepositoriesList />
    </Protected>
  );
}
