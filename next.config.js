/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Lets tests/CI build into a separate folder without disturbing a running `next dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

module.exports = nextConfig;
