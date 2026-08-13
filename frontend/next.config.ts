import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Let devices on the shop LAN receive Next.js dev updates.
  allowedDevOrigins: ["192.168.1.36"],
};

export default nextConfig;
