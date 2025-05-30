import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  output: "export",
  basePath: "/jr-freight-map"
};

export default nextConfig;
