export type CustomEmoji = {
  id: string;
  name: string;
  value: string;
};

function customEmojiKey(workspaceId: string) {
  return `workspace:${workspaceId}:custom-emojis`;
}

function workspaceIconKey(workspaceId: string) {
  return `workspace:${workspaceId}:icon`;
}

export function getWorkspaceIcon(workspaceId: string): string | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(workspaceIconKey(workspaceId));
  return value && value.trim().length > 0 ? value : null;
}

export function setWorkspaceIcon(workspaceId: string, icon: string | null) {
  if (typeof window === "undefined") return;
  if (!icon || !icon.trim()) {
    window.localStorage.removeItem(workspaceIconKey(workspaceId));
  } else {
    window.localStorage.setItem(workspaceIconKey(workspaceId), icon.trim());
  }
  window.dispatchEvent(new CustomEvent("workspace-ui:changed", { detail: { workspaceId } }));
}

export function getCustomEmojis(workspaceId: string): CustomEmoji[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(customEmojiKey(workspaceId));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => ({
        id: typeof item?.id === "string" ? item.id : "",
        name: typeof item?.name === "string" ? item.name : "",
        value: typeof item?.value === "string" ? item.value : "",
      }))
      .filter((item) => item.id && item.name && item.value);
  } catch {
    return [];
  }
}

export function saveCustomEmojis(workspaceId: string, emojis: CustomEmoji[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(customEmojiKey(workspaceId), JSON.stringify(emojis));
  window.dispatchEvent(new CustomEvent("workspace-ui:changed", { detail: { workspaceId } }));
}

export function resolveIcon(icon: string | null | undefined, customEmojis: CustomEmoji[]) {
  const raw = icon?.trim() ?? "";
  if (!raw) return null;
  if (raw.startsWith("custom:")) {
    const id = raw.slice("custom:".length);
    const match = customEmojis.find((item) => item.id === id);
    if (!match) return null;
    return {
      type: match.value.startsWith("data:") || match.value.startsWith("http") || match.value.startsWith("/") ? "image" : "emoji",
      value: match.value,
    } as const;
  }
  if (raw.startsWith("data:") || raw.startsWith("http") || raw.startsWith("/")) {
    return { type: "image", value: raw } as const;
  }
  return { type: "emoji", value: raw } as const;
}

export function randomEmojiId() {
  return `cemo_${Math.random().toString(36).slice(2, 10)}`;
}
