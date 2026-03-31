import withPWAInit from "next-pwa";

const withPWA = withPWAInit({
  dest: "public",
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === "development",
});

const localTurbopackConfig =
  process.env.VERCEL === "1"
    ? {}
    : {
        turbopack: {
          root: process.cwd(),
        },
      };

/** @type {import("next").NextConfig} */
const nextConfig = {
  ...localTurbopackConfig,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
        pathname: "/storage/v1/object/public/**",
      },
    ],
  },
};

export default withPWA(nextConfig);
