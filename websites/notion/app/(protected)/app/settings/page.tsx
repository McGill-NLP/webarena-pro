"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Bell, Copy, Globe, Settings2, Trash2, Users, X } from "lucide-react";
import { applyThemeMode, getSavedThemeMode, type ThemeMode } from "@/lib/theme-mode";
import { applyLanguage, getSavedLanguage, t, type UiLanguage } from "@/lib/ui-language";
import { getCustomEmojis, getWorkspaceIcon, randomEmojiId, saveCustomEmojis, setWorkspaceIcon, type CustomEmoji } from "@/lib/workspace-ui";

type SettingsSection = "preferences" | "notifications" | "general" | "people" | "public_pages" | "emoji";

type MePayload = {
  user?: {
    email: string;
    displayName: string;
  };
  activeWorkspace?: {
    id: string;
    name: string;
    role: "owner" | "editor" | "viewer";
    isCreator?: boolean;
  } | null;
};

type PublicPageItem = {
  id: string;
  title: string;
  type: "document" | "database";
  shareUrl: string;
  createdAt: string;
};

type WorkspacePerson = {
  user: {
    id: string;
    email: string;
  };
  workspaceRole: "owner" | "editor" | "viewer" | "page_only";
  pages: Array<{
    id: string;
    title: string;
    type: "document" | "database";
    accessLevel: "workspace" | "private";
    role: "editor" | "commenter" | "viewer" | null;
  }>;
};

const MENU: { group: string; items: { id: SettingsSection; label: string; icon: typeof Settings2 }[] }[] = [
  {
    group: "Account",
    items: [
      { id: "preferences", label: "Preferences", icon: Settings2 },
      { id: "notifications", label: "Notifications", icon: Bell },
    ],
  },
  {
    group: "Workspace",
    items: [
      { id: "general", label: "General", icon: Settings2 },
      { id: "people", label: "People", icon: Users },
    ],
  },
  {
    group: "Features",
    items: [
      { id: "public_pages", label: "Public pages", icon: Globe },
      { id: "emoji", label: "Emoji", icon: Globe },
    ],
  },
];

const NOTIFICATION_INBOX_KEY = "settings:notifications:inbox";
const NOTIFICATION_EMAIL_KEY = "settings:notifications:email";
const CREATOR_ONLY_MENU = new Set<SettingsSection>(["people", "public_pages", "emoji"]);

function titleForSection(section: SettingsSection, language: UiLanguage) {
  if (section === "preferences") return t(language, "preferences");
  if (section === "notifications") return t(language, "notifications");
  if (section === "general") return t(language, "general");
  if (section === "people") return t(language, "people");
  if (section === "public_pages") return t(language, "public_pages");
  return t(language, "emoji");
}

async function fileToDataUrl(file: File): Promise<string> {
  const maxBytes = 1_200_000;
  if (file.size > maxBytes) {
    throw new Error("File is too large. Please use an image under 1.2MB.");
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      if (!result) {
        reject(new Error("Failed to read file"));
        return;
      }
      resolve(result);
    };
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const initialSection = (searchParams.get("section") as SettingsSection | null) ?? "preferences";
  const [active, setActive] = useState<SettingsSection>(initialSection);
  const [themeMode, setThemeMode] = useState<ThemeMode>("system");
  const [language, setLanguage] = useState<UiLanguage>("en");
  const [userName, setUserName] = useState("User");
  const [userEmail, setUserEmail] = useState("No email");
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceRole, setWorkspaceRole] = useState<"owner" | "editor" | "viewer">("viewer");
  const [workspaceName, setWorkspaceName] = useState("My Workspace");
  const [workspaceIsCreator, setWorkspaceIsCreator] = useState(false);
  const [workspaceIcon, setWorkspaceIconState] = useState<string | null>(null);
  const [workspaceNotice, setWorkspaceNotice] = useState<string | null>(null);
  const [publicPages, setPublicPages] = useState<PublicPageItem[]>([]);
  const [publicPagesOpen, setPublicPagesOpen] = useState(false);
  const [people, setPeople] = useState<WorkspacePerson[]>([]);
  const [customEmojis, setCustomEmojis] = useState<CustomEmoji[]>([]);
  const [newEmojiName, setNewEmojiName] = useState("");
  const [newEmojiChar, setNewEmojiChar] = useState("");
  const [emojiBusy, setEmojiBusy] = useState(false);
  const [notificationInbox, setNotificationInbox] = useState(true);
  const [notificationEmail, setNotificationEmail] = useState(false);

  useEffect(() => {
    const next = (searchParams.get("section") as SettingsSection | null) ?? "preferences";
    setActive(next);
  }, [searchParams]);

  useEffect(() => {
    setThemeMode(getSavedThemeMode());
    setLanguage(getSavedLanguage());
    if (typeof window !== "undefined") {
      const savedInbox = window.localStorage.getItem(NOTIFICATION_INBOX_KEY);
      const savedEmail = window.localStorage.getItem(NOTIFICATION_EMAIL_KEY);
      if (savedInbox === "0" || savedInbox === "1") {
        setNotificationInbox(savedInbox === "1");
      }
      if (savedEmail === "0" || savedEmail === "1") {
        setNotificationEmail(savedEmail === "1");
      }
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(NOTIFICATION_INBOX_KEY, notificationInbox ? "1" : "0");
  }, [notificationInbox]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(NOTIFICATION_EMAIL_KEY, notificationEmail ? "1" : "0");
  }, [notificationEmail]);

  useEffect(() => {
    const onWorkspaceUiChanged = () => {
      if (!workspaceId) return;
      setWorkspaceIconState(getWorkspaceIcon(workspaceId));
      setCustomEmojis(getCustomEmojis(workspaceId));
    };
    window.addEventListener("workspace-ui:changed", onWorkspaceUiChanged);
    return () => window.removeEventListener("workspace-ui:changed", onWorkspaceUiChanged);
  }, [workspaceId]);

  useEffect(() => {
    const fetchMe = async () => {
      const response = await fetch("/api/me");
      if (!response.ok) return;
      const data = (await response.json()) as MePayload;
      if (data.user?.displayName) setUserName(data.user.displayName);
      if (data.user?.email) setUserEmail(data.user.email);
      if (data.activeWorkspace?.id) {
        setWorkspaceId(data.activeWorkspace.id);
        setWorkspaceName(data.activeWorkspace.name);
        setWorkspaceRole(data.activeWorkspace.role);
        setWorkspaceIsCreator(Boolean(data.activeWorkspace.isCreator ?? data.activeWorkspace.role === "owner"));
        setWorkspaceIconState(getWorkspaceIcon(data.activeWorkspace.id));
        setCustomEmojis(getCustomEmojis(data.activeWorkspace.id));
      }
    };
    void fetchMe();
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    if (active === "public_pages") {
      void (async () => {
        const response = await fetch("/api/workspaces/public-pages");
        if (!response.ok) return;
        const data = await response.json();
        setPublicPages(Array.isArray(data?.pages) ? data.pages : []);
      })();
    }
    if (active === "people") {
      void (async () => {
        const response = await fetch("/api/workspaces/people");
        if (!response.ok) return;
        const data = await response.json();
        setPeople(Array.isArray(data?.people) ? data.people : []);
      })();
    }
  }, [active, workspaceId]);

  const heading = useMemo(() => titleForSection(active, language), [active, language]);
  const visibleMenu = useMemo(() => {
    if (workspaceIsCreator) return MENU;
    return MENU.map((group) => ({
      ...group,
      items: group.items.filter((item) => !CREATOR_ONLY_MENU.has(item.id)),
    })).filter((group) => group.items.length > 0);
  }, [workspaceIsCreator]);

  useEffect(() => {
    applyThemeMode(themeMode);
  }, [themeMode]);

  useEffect(() => {
    applyLanguage(language);
  }, [language]);

  async function copyShareUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setWorkspaceNotice("Copied share URL.");
    } catch {
      setWorkspaceNotice("Could not copy share URL.");
    }
  }

  async function deleteShareLink(id: string) {
    const response = await fetch(`/api/share-links/${id}`, { method: "DELETE" });
    if (!response.ok) return;
    setPublicPages((current) => current.filter((page) => page.id !== id));
  }

  async function updateWorkspaceIcon(nextIcon: string | null) {
    if (!workspaceId) return;
    setWorkspaceIcon(workspaceId, nextIcon);
    setWorkspaceIconState(nextIcon);
    setWorkspaceNotice(nextIcon ? "Workspace icon updated." : "Workspace icon removed.");
    window.dispatchEvent(new Event("workspace-ui:changed"));
  }

  async function onWorkspaceIconSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    try {
      const dataUrl = await fileToDataUrl(file);
      await updateWorkspaceIcon(dataUrl);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to upload workspace icon.";
      setWorkspaceNotice(message);
    }
  }

  async function addCustomEmoji() {
    if (!workspaceId || emojiBusy) return;
    const name = newEmojiName.trim().toLowerCase();
    const value = newEmojiChar.trim();
    if (!name || !value) return;
    setEmojiBusy(true);
    try {
      const next = [
        ...customEmojis.filter((emoji) => emoji.name !== name),
        { id: randomEmojiId(), name, value },
      ];
      setCustomEmojis(next);
      saveCustomEmojis(workspaceId, next);
      setNewEmojiName("");
      setNewEmojiChar("");
      setWorkspaceNotice(`Saved :${name}:`);
      window.dispatchEvent(new Event("workspace-ui:changed"));
    } finally {
      setEmojiBusy(false);
    }
  }

  function removeCustomEmoji(id: string) {
    if (!workspaceId) return;
    const next = customEmojis.filter((emoji) => emoji.id !== id);
    setCustomEmojis(next);
    saveCustomEmojis(workspaceId, next);
    setWorkspaceNotice("Custom emoji removed.");
    window.dispatchEvent(new Event("workspace-ui:changed"));
  }

  const closeHref = active === "preferences" ? "/app" : `/app/settings?section=preferences`;

  return (
    <div className="mx-auto flex w-full max-w-[1180px] gap-6">
      <aside className="sticky top-0 hidden h-[calc(100vh-3rem)] w-[260px] shrink-0 overflow-y-auto rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-4 lg:block">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-[var(--muted)]">Settings</p>
            <h1 className="mt-1 text-lg font-semibold">{workspaceName}</h1>
          </div>
          <Link href={closeHref} className="rounded-md p-2 text-[var(--muted)] hover:bg-[var(--hover)]" aria-label="Close settings">
            <X className="h-4 w-4" />
          </Link>
        </div>

        <nav className="space-y-5">
          {visibleMenu.map((group) => (
            <div key={group.group}>
              <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
                {group.group}
              </p>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const selected = active === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => {
                        setActive(item.id);
                        router.replace(`/app/settings?section=${item.id}`);
                      }}
                      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition ${
                        selected ? "bg-[var(--hover)] text-[var(--fg)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      <span>{titleForSection(item.id, language)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.12em] text-[var(--muted)]">{workspaceName}</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">{heading}</h1>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Manage your account, workspace, and WebArena-style sharing controls.
            </p>
          </div>
          <Link href={closeHref} className="rounded-xl border border-[var(--line)] px-3 py-2 text-sm hover:bg-[var(--hover)]">
            Done
          </Link>
        </div>

        {workspaceNotice ? (
          <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-sm text-[var(--muted)]">
            {workspaceNotice}
          </div>
        ) : null}

        <section className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.12em] text-[var(--muted)]">Account</p>
              <h2 className="mt-1 text-xl font-semibold">{userName}</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">{userEmail}</p>
            </div>
            <div className="rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm">
              Workspace role: <span className="font-medium">{workspaceRole}</span>
            </div>
          </div>
        </section>

        {active === "preferences" ? (
          <section className="grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
              <h3 className="text-lg font-semibold">{t(language, "preferences")}</h3>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Personalize theme and language preferences for the current browser.
              </p>
              <div className="mt-6 space-y-6">
                <div>
                  <label className="text-sm font-medium">Theme</label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(["light", "dark", "system"] as ThemeMode[]).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setThemeMode(mode)}
                        className={`rounded-xl border px-4 py-2 text-sm ${
                          themeMode === mode
                            ? "border-[var(--fg)] bg-[var(--hover)]"
                            : "border-[var(--line)] hover:bg-[var(--hover)]"
                        }`}
                      >
                        {mode}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-sm font-medium">Language</label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(["en", "ko"] as UiLanguage[]).map((value) => (
                      <button
                        key={value}
                        onClick={() => setLanguage(value)}
                        className={`rounded-xl border px-4 py-2 text-sm ${
                          language === value
                            ? "border-[var(--fg)] bg-[var(--hover)]"
                            : "border-[var(--line)] hover:bg-[var(--hover)]"
                        }`}
                      >
                        {value === "en" ? "English" : "Korean"}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
              <h3 className="text-lg font-semibold">Tips</h3>
              <ul className="mt-4 space-y-3 text-sm text-[var(--muted)]">
                <li>Theme and language preferences are saved in local storage.</li>
                <li>System theme follows your OS appearance automatically.</li>
                <li>These settings apply immediately without a page reload.</li>
              </ul>
            </div>
          </section>
        ) : null}

        {active === "notifications" ? (
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
            <h3 className="text-lg font-semibold">{t(language, "notifications")}</h3>
            <div className="mt-5 space-y-4">
              <label className="flex items-center justify-between rounded-xl border border-[var(--line)] px-4 py-3">
                <div>
                  <p className="text-sm font-medium">Inbox notifications</p>
                  <p className="text-sm text-[var(--muted)]">Show in-app updates for mentions and share links.</p>
                </div>
                <input type="checkbox" checked={notificationInbox} onChange={(event) => setNotificationInbox(event.target.checked)} />
              </label>
              <label className="flex items-center justify-between rounded-xl border border-[var(--line)] px-4 py-3">
                <div>
                  <p className="text-sm font-medium">Email notifications</p>
                  <p className="text-sm text-[var(--muted)]">Demo-only toggle for future email delivery behavior.</p>
                </div>
                <input type="checkbox" checked={notificationEmail} onChange={(event) => setNotificationEmail(event.target.checked)} />
              </label>
            </div>
          </section>
        ) : null}

        {active === "general" ? (
          <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
              <h3 className="text-lg font-semibold">{t(language, "general")}</h3>
              <p className="mt-2 text-sm text-[var(--muted)]">Customize workspace visuals used throughout the app.</p>
              <div className="mt-5 space-y-4">
                <div>
                  <label className="text-sm font-medium">Workspace name</label>
                  <p className="mt-2 rounded-xl border border-[var(--line)] bg-[var(--bg)] px-4 py-3 text-sm">{workspaceName}</p>
                </div>
                <div>
                  <label className="text-sm font-medium">Workspace icon</label>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--bg)] text-2xl">
                      {workspaceIcon ?? "N"}
                    </div>
                    <label className="rounded-xl border border-[var(--line)] px-4 py-2 text-sm hover:bg-[var(--hover)]">
                      Upload icon
                      <input type="file" accept="image/*" className="hidden" onChange={onWorkspaceIconSelected} />
                    </label>
                    <button
                      onClick={() => void updateWorkspaceIcon(null)}
                      className="rounded-xl border border-[var(--line)] px-4 py-2 text-sm hover:bg-[var(--hover)]"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
              <h3 className="text-lg font-semibold">Workspace info</h3>
              <div className="mt-5 space-y-3 text-sm text-[var(--muted)]">
                <p>Role: {workspaceRole}</p>
                <p>Workspace ID: {workspaceId || "Unavailable"}</p>
                <p>Creator privileges: {workspaceIsCreator ? "Enabled" : "Disabled"}</p>
              </div>
            </div>
          </section>
        ) : null}

        {active === "people" ? (
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
            <h3 className="text-lg font-semibold">{t(language, "people")}</h3>
            <div className="mt-5 space-y-3">
              {people.length === 0 ? (
                <p className="text-sm text-[var(--muted)]">No workspace members found.</p>
              ) : (
                people.map((person) => (
                  <div key={person.user.id} className="rounded-xl border border-[var(--line)] px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-medium">{person.user.email}</p>
                        <p className="text-sm text-[var(--muted)]">{person.workspaceRole}</p>
                      </div>
                      <span className="rounded-full bg-[var(--hover)] px-3 py-1 text-xs uppercase tracking-[0.08em]">
                        {person.pages.length} pages
                      </span>
                    </div>
                    {person.workspaceRole === "page_only" && person.pages.length > 0 ? (
                      <div className="mt-3 border-t border-[var(--line)] pt-3">
                        <p className="mb-1.5 text-xs font-medium uppercase tracking-[0.08em] text-[var(--muted)]">Accessible pages</p>
                        <div className="space-y-1">
                          {person.pages.map((pg) => (
                            <div key={pg.id} className="flex items-center justify-between rounded-md px-2 py-1 text-sm hover:bg-[var(--hover)]">
                              <span className="truncate">{pg.title || "Untitled"}</span>
                              <span className="shrink-0 text-xs text-[var(--muted)]">{pg.role ?? "viewer"}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </section>
        ) : null}

        {active === "public_pages" ? (
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">{t(language, "public_pages")}</h3>
                <p className="mt-2 text-sm text-[var(--muted)]">Review shareable pages and copy their public URLs.</p>
              </div>
              <button
                onClick={() => setPublicPagesOpen((open) => !open)}
                className="rounded-xl border border-[var(--line)] px-4 py-2 text-sm hover:bg-[var(--hover)]"
              >
                {publicPagesOpen ? "Hide links" : "Show links"}
              </button>
            </div>
            {publicPagesOpen ? (
              <div className="mt-5 space-y-3">
                {publicPages.length === 0 ? (
                  <p className="text-sm text-[var(--muted)]">No public pages yet.</p>
                ) : (
                  publicPages.map((page) => (
                    <div key={page.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--line)] px-4 py-3">
                      <div>
                        <p className="font-medium">{page.title}</p>
                        <p className="text-sm text-[var(--muted)]">{page.type}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => void copyShareUrl(page.shareUrl)}
                          className="inline-flex items-center gap-2 rounded-xl border border-[var(--line)] px-3 py-2 text-sm hover:bg-[var(--hover)]"
                        >
                          <Copy className="h-4 w-4" />
                          Copy URL
                        </button>
                        <button
                          onClick={() => void deleteShareLink(page.id)}
                          className="inline-flex items-center gap-2 rounded-xl border border-[var(--line)] px-3 py-2 text-sm text-[#b42318] hover:bg-[var(--hover)]"
                        >
                          <Trash2 className="h-4 w-4" />
                          Remove
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            ) : null}
          </section>
        ) : null}

        {active === "emoji" ? (
          <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
              <h3 className="text-lg font-semibold">{t(language, "emoji")}</h3>
              <p className="mt-2 text-sm text-[var(--muted)]">Create lightweight custom emoji shortcuts for workspace visuals.</p>
              <div className="mt-5 space-y-3">
                <input
                  value={newEmojiName}
                  onChange={(event) => setNewEmojiName(event.target.value)}
                  placeholder="emoji name"
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-4 py-3 text-sm outline-none"
                />
                <input
                  value={newEmojiChar}
                  onChange={(event) => setNewEmojiChar(event.target.value)}
                  placeholder="emoji character"
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-4 py-3 text-sm outline-none"
                />
                <button
                  onClick={() => void addCustomEmoji()}
                  disabled={emojiBusy}
                  className="rounded-xl border border-[var(--line)] px-4 py-2 text-sm hover:bg-[var(--hover)] disabled:opacity-50"
                >
                  Save emoji
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5">
              <h3 className="text-lg font-semibold">Custom emoji library</h3>
              <div className="mt-5 space-y-3">
                {customEmojis.length === 0 ? (
                  <p className="text-sm text-[var(--muted)]">No custom emoji saved.</p>
                ) : (
                  customEmojis.map((emoji) => (
                    <div key={emoji.id} className="flex items-center justify-between rounded-xl border border-[var(--line)] px-4 py-3">
                      <div>
                        <p className="font-medium">:{emoji.name}:</p>
                        <p className="text-sm text-[var(--muted)]">{emoji.value}</p>
                      </div>
                      <button
                        onClick={() => removeCustomEmoji(emoji.id)}
                        className="rounded-xl border border-[var(--line)] px-3 py-2 text-sm text-[#b42318] hover:bg-[var(--hover)]"
                      >
                        Remove
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
