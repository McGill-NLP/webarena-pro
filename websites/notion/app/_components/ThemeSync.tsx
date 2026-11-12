"use client";

import { useEffect } from "react";
import { applyThemeMode, getSavedThemeMode } from "@/lib/theme-mode";

export default function ThemeSync() {
  useEffect(() => {
    applyThemeMode(getSavedThemeMode());

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleMediaChange = () => {
      if (getSavedThemeMode() === "system") {
        applyThemeMode("system");
      }
    };

    media.addEventListener("change", handleMediaChange);
    return () => media.removeEventListener("change", handleMediaChange);
  }, []);

  return null;
}
