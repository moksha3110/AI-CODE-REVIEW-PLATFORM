"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Gates a page behind an authenticated session. There's no server-side
 * route protection here (no middleware/proxy check) because the access
 * token only ever lives in browser memory - a server request has no way to
 * see it. This runs client-side, after the initial silent-refresh attempt
 * resolves.
 *
 * Gates on `accessToken`, not `user`. The OAuth callback sets the access
 * token synchronously but fetches the user profile in a separate, slightly
 * later request - gating on `user` would bounce a freshly-logged-in visitor
 * straight back to "/" during that gap, since `isLoading` (the *initial*
 * silent-refresh flag) is already false by the time the callback runs.
 */
export function Protected({ children }: { children: React.ReactNode }) {
  const { accessToken, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !accessToken) {
      router.replace("/");
    }
  }, [isLoading, accessToken, router]);

  if (isLoading || !accessToken) {
    return (
      <div className="container mx-auto max-w-5xl space-y-4 px-4 py-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return <>{children}</>;
}
