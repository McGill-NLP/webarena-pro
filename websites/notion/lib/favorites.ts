export const FAVORITE_PAGES_KEY = "pages:favorites";

function parseFavorites(raw: string | null) {
  if (!raw) return new Set<string>();
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set<string>();
    return new Set(parsed.filter((item): item is string => typeof item === "string" && item.length > 0));
  } catch {
    return new Set<string>();
  }
}

export function getFavoritePageIds(): Set<string> {
  if (typeof window === "undefined") return new Set<string>();
  return parseFavorites(window.localStorage.getItem(FAVORITE_PAGES_KEY));
}

export function isFavoritePage(pageId: string) {
  return getFavoritePageIds().has(pageId);
}

export function setFavoritePage(pageId: string, next: boolean) {
  if (typeof window === "undefined") return;
  const ids = getFavoritePageIds();
  if (next) {
    ids.add(pageId);
  } else {
    ids.delete(pageId);
  }
  window.localStorage.setItem(FAVORITE_PAGES_KEY, JSON.stringify([...ids]));
  window.dispatchEvent(new Event("favorites:changed"));
}
