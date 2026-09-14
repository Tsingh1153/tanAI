import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "tanAI",
  description: "A fully local AI assistant.",
};

// Set the theme class before first paint to avoid a light/dark flash. Reads the
// saved preference, falling back to the OS setting.
const themeScript = `
(function () {
  try {
    var stored = localStorage.getItem("localmind-theme");
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var dark = stored ? stored === "dark" : prefersDark;
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
