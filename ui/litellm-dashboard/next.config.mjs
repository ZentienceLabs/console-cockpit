import path from "path";
import { fileURLToPath } from "url";

/** @type {import('next').NextConfig} */
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = process.env.NODE_ENV === "development";

const nextConfig = {
  output: "export",
  basePath: "",
  assetPrefix: "/litellm-asset-prefix",
  async rewrites() {
    if (!isDev) {
      return [];
    }
    return [
      {
        source: "/v1/:path*",
        destination: "http://localhost:4000/v1/:path*",
      },
    ];
  },
  turbopack: {
    // Must be absolute; "." is no longer allowed
    root: __dirname,
  },
};

export default nextConfig;
