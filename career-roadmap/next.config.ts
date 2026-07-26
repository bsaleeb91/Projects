import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // pdf-parse (via pdfjs-dist) resolves a worker file path at runtime that
  // Next's Server Components bundler mangles — opt it out of bundling so it
  // runs under native Node `require` instead.
  serverExternalPackages: ["pdf-parse"],
};

export default nextConfig;
