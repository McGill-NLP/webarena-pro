export type ThemeMode = "light" | "dark" | "system";

export const THEME_MODE_KEY = "ui:theme-mode";

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function resolveTheme(mode: ThemeMode): "light" | "dark" {
  return mode === "system" ? getSystemTheme() : mode;
}

export function getSavedThemeMode(): ThemeMode {
  if (typeof window === "undefined") return "system";
  const value = window.localStorage.getItem(THEME_MODE_KEY);
  if (value === "light" || value === "dark" || value === "system") return value;
  return "system";
}

export function applyThemeMode(mode: ThemeMode) {
  if (typeof window === "undefined") return;
  const resolved = resolveTheme(mode);
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  window.localStorage.setItem(THEME_MODE_KEY, mode);
  window.dispatchEvent(new CustomEvent("theme:changed", { detail: mode }));
}
