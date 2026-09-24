/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export so the whole UI can be bundled into the Tauri app and served
  // from the native webview. The app is a single client-rendered page that talks
  // to the backend over HTTP/WS, so it needs no Node server at runtime.
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
