import type { NextConfig } from "next";

// STATIC_DEMO=1 builds ONLY the /demo console as static files for the public link (Cloudflare
// Pages): no Clerk, no backend, no keys. Routes come from *.static.tsx files and @clerk/nextjs
// is aliased to a stub. Normal builds are unaffected.
const staticDemo = process.env.STATIC_DEMO === "1";

const nextConfig: NextConfig = staticDemo
  ? {
      output: "export",
      distDir: ".next-static",
      trailingSlash: true,
      pageExtensions: ["static.tsx"],
      images: { unoptimized: true },
      env: { NEXT_PUBLIC_STATIC_DEMO: "1" },
      turbopack: { resolveAlias: { "@clerk/nextjs": "./lib/clerk-stub.tsx" } },
    }
  : {
      turbopack: { resolveAlias: { "@clerk/nextjs": "./lib/clerk-stub.tsx" } },
      webpack(config) {
        config.resolve.alias = {
          ...config.resolve.alias,
          "@clerk/nextjs": require("path").resolve(__dirname, "lib/clerk-stub.tsx"),
        };
        return config;
      },
      async rewrites() {
        // The marketing site (app/public/landing/index.html) is the only landing page. Serve it at
        // "/" before the app router so the URL stays clean; the console lives at /app.
        return {
          beforeFiles: [
            { source: "/", destination: "/landing/index.html" },
            { source: "/landing", destination: "/landing/index.html" },
          ],
          afterFiles: [],
          fallback: [],
        };
      },
    };

export default nextConfig;
