import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // An unrelated lockfile in the user's home directory otherwise makes
  // Turbopack guess the workspace root incorrectly.
  turbopack: {
    root: path.join(__dirname),
  },
  // Lean, self-contained production image - see Dockerfile.
  output: "standalone",
};

export default nextConfig;
