"use client";

import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * repository-service redirects here after the user approves the GitHub App
 * installation. There's nothing to fetch on this page - the installation
 * callback already ran server-side before this redirect fired.
 */
export default function RepositoriesConnectedPage() {
  return (
    <div className="container mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
      <CheckCircle2 className="h-12 w-12 text-emerald-500" />
      <h1 className="text-2xl font-semibold">Repository connected</h1>
      <p className="text-muted-foreground">
        Pushes to this repository will now be reviewed automatically.
      </p>
      <Link href="/repositories" className={cn(buttonVariants())}>
        Go to repositories
      </Link>
    </div>
  );
}
