import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Capacitor builds a static copy into `out`; the normal web deployment
  // remains a Next server with its existing rewrite proxy.
  ...(process.env.CAPACITOR_BUILD === "1" ? { output: "export" as const } : {}),
  // Let devices on private LANs load dev-only assets and the HMR WebSocket.
  // These are host patterns, so moving the computer to another private network
  // does not require editing this file.
  allowedDevOrigins: ["localhost", "127.0.0.1", "10.*.*.*", "172.*.*.*", "192.168.*.*"],
  // A single public origin lets Cloudflare route the app without exposing the
  // backend port. API_INTERNAL_URL is server-only and defaults to deployment.
  async rewrites() {
    const apiOrigin = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8010";
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }, { source: "/health", destination: `${apiOrigin}/health` }, { source: "/webhooks/:path*", destination: `${apiOrigin}/webhooks/:path*` }];
  },
};

export default nextConfig;
