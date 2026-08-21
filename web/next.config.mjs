import path from "node:path";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Exported as plain files so the Python service can serve the whole app on
  // one port, with no Node at runtime.
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,

  // Pin the workspace root, otherwise Next looks upwards and picks up stray
  // lockfiles from the home directory.
  turbopack: {
    root: path.dirname(new URL(import.meta.url).pathname.slice(1)),
  },
};

export default nextConfig;
