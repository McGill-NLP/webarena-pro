import "./globals.css";
import type { Metadata } from "next";
import ThemeSync from "./_components/ThemeSync";

export const metadata: Metadata = {
  title: "Notion Sandbox",
  description: "Multi-user Notion-like sandbox for task evaluation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <ThemeSync />
        {children}
      </body>
    </html>
  );
}
