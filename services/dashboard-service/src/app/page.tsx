"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { GitPullRequest, ShieldAlert, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { GithubIcon } from "@/components/icons";

const FEATURES = [
  {
    icon: GitPullRequest,
    title: "Review on every push",
    body: "Connect a repository once - every push after that gets a Claude-generated review automatically, no CI config to write.",
  },
  {
    icon: ShieldAlert,
    title: "Bugs and security issues",
    body: "Per-file findings with severity and line numbers, not a vague pass/fail.",
  },
  {
    icon: TrendingUp,
    title: "Quality trends over time",
    body: "Complexity and issue counts charted per repository, so drift is visible before it's a problem.",
  },
];

export default function LandingPage() {
  const { user, isLoading, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/repositories");
    }
  }, [isLoading, user, router]);

  return (
    <div className="container mx-auto flex max-w-3xl flex-col items-center gap-10 px-4 py-20 text-center">
      <div className="space-y-4">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          AI code review, on every push.
        </h1>
        <p className="text-lg text-muted-foreground">
          Connect a GitHub repository and get a structured Claude review -
          bugs, security issues, optimizations, and complexity trends -
          automatically, no CI setup required.
        </p>
      </div>

      <Button size="lg" onClick={login} disabled={isLoading}>
        <GithubIcon className="mr-2 h-5 w-5" />
        Sign in with GitHub
      </Button>

      <div className="grid gap-4 pt-8 text-left sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <Card key={title}>
            <CardHeader>
              <Icon className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">{title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{body}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
