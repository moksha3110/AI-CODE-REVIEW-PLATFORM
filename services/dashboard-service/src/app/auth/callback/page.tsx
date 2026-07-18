"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from "next/link";

/**
 * auth-service redirects here after a successful GitHub OAuth exchange,
 * with the access token as a URL fragment
 * (`#access_token=...`) rather than a query param - fragments never reach
 * the server (not sent in the request, never logged), so this has to run
 * client-side. The refresh token was already set as an httpOnly cookie by
 * that same redirect response.
 */
export default function AuthCallbackPage() {
  const { setAccessTokenFromCallback } = useAuth();
  const router = useRouter();
  const [error, setError] = useState(false);

  useEffect(() => {
    const hash = window.location.hash;
    const token = new URLSearchParams(hash.replace(/^#/, "")).get("access_token");

    if (!token) {
      // window.location.hash is a browser-only API with no render-time
      // equivalent (nothing to read on the server) - this has to be an
      // effect, and the error state genuinely can't be known any earlier.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(true);
      return;
    }

    setAccessTokenFromCallback(token);
    // Strip the token from the URL immediately - it shouldn't linger in
    // browser history or be re-readable via the back button.
    window.history.replaceState(null, "", window.location.pathname);
    router.replace("/repositories");
  }, [setAccessTokenFromCallback, router]);

  if (error) {
    return (
      <div className="container mx-auto max-w-md px-4 py-20">
        <Alert variant="destructive">
          <AlertTitle>Sign-in failed</AlertTitle>
          <AlertDescription>
            No access token was returned. Try signing in again.
          </AlertDescription>
        </Alert>
        <Link href="/" className={cn(buttonVariants(), "mt-4")}>
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-md space-y-4 px-4 py-20">
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}
