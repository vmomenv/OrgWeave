import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@orgweave/shared-types"],
  poweredByHeader: false,
};

export default nextConfig;
