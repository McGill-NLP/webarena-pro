import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "serif"],
      },
      colors: {
        ink: "var(--ink)",
        paper: "var(--paper)",
        canvas: "var(--canvas)",
        accent: "var(--accent)",
        accentSoft: "var(--accent-soft)",
        muted: "var(--muted)",
        line: "var(--line)",
      },
      boxShadow: {
        soft: "0 10px 30px rgba(31, 31, 31, 0.08)",
        lift: "0 16px 40px rgba(31, 31, 31, 0.12)",
      },
    },
  },
  plugins: [],
};

export default config;
