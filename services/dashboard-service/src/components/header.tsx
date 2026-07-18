"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth-context";
import { NotificationsBell } from "@/components/notifications-bell";
import { UserMenu } from "@/components/user-menu";
import { GithubIcon } from "@/components/icons";

export function Header() {
  const { user, isLoading, login } = useAuth();

  return (
    <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href={user ? "/repositories" : "/"} className="font-semibold tracking-tight">
          CodeReview <span className="text-muted-foreground">AI</span>
        </Link>

        <div className="flex items-center gap-2">
          {isLoading ? (
            <Skeleton className="h-8 w-8 rounded-full" />
          ) : user ? (
            <>
              <NotificationsBell />
              <UserMenu />
            </>
          ) : (
            <Button size="sm" onClick={login}>
              <GithubIcon className="mr-2 h-4 w-4" />
              Sign in with GitHub
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
