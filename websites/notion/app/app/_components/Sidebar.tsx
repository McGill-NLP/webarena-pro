"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Database,
  FilePlus2,
  FileText,
  GripVertical,
  Lock,
  NotebookPen,
  RotateCcw,
  Search,
  SendHorizontal,
  Settings,
  Star,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { getFavoritePageIds } from "@/lib/favorites";
import { getSavedLanguage, t, type UiLanguage } from "@/lib/ui-language";
import { getCustomEmojis, getWorkspaceIcon, resolveIcon, type CustomEmoji } from "@/lib/workspace-ui";
import { DATABASE_ROW_PAGE_PREFIX } from "@/lib/database-row-page";

const SIDEBAR_COLLAPSED_KEY = "sidebar:collapsed";
const SIDEBAR_EXPANDED_KEY = "sidebar:expanded";
const LINKED_ACCOUNTS_KEY = "accounts:linked";

export type PageItem = {
  id: string;
  title: string;
  type: "document" | "database";
  parentPageId: string | null;
  accessLevel: "workspace" | "private";
  icon: string | null;
  deletedAt: string | Date | null;
  isSmallText: boolean;
  isFullWidth: boolean;
  isLocked: boolean;
  fontStyle: "default" | "serif" | "mono";
};

type WorkspaceItem = {
  id: string;
  name: string;
  slug: string;
  role: "owner" | "editor" | "viewer";
  active: boolean;
};

type SearchResult = {
  id: string;
  title: string;
  type: "document" | "database";
};

type CurrentUser = {
  id: string;
  email: string;
  displayName: string;
  initials: string;
};

type AccountItem = {
  id: string;
  email: string;
  role: "owner" | "editor" | "viewer";
  createdAt: string;
  active: boolean;
};

type TemplateBlock = {
  type: "paragraph" | "heading_1" | "heading_2" | "bulleted_list_item" | "todo";
  contentText: string;
};

type PageTemplate = {
  id: string;
  label: string;
  title: string;
  blocks: TemplateBlock[];
};

const PAGE_TEMPLATES: PageTemplate[] = [
  {
    id: "meeting_notes",
    label: "AI Meeting Notes",
    title: "AI Meeting Notes",
    blocks: [
      { type: "heading_1", contentText: "Meeting" },
      { type: "paragraph", contentText: "Date: " },
      { type: "paragraph", contentText: "Attendees: " },
      { type: "heading_2", contentText: "Agenda" },
      { type: "bulleted_list_item", contentText: "Topic 1" },
      { type: "bulleted_list_item", contentText: "Topic 2" },
      { type: "heading_2", contentText: "Action items" },
      { type: "todo", contentText: "Owner + due date" },
    ],
  },
  {
    id: "project_brief",
    label: "Project Brief",
    title: "Project Brief",
    blocks: [
      { type: "heading_1", contentText: "Project Brief" },
      { type: "heading_2", contentText: "Goal" },
      { type: "paragraph", contentText: "What are we trying to achieve?" },
      { type: "heading_2", contentText: "Scope" },
      { type: "bulleted_list_item", contentText: "In scope" },
      { type: "bulleted_list_item", contentText: "Out of scope" },
      { type: "heading_2", contentText: "Timeline" },
      { type: "todo", contentText: "Milestone 1" },
    ],
  },
  {
    id: "weekly_review",
    label: "Weekly Review",
    title: "Weekly Review",
    blocks: [
      { type: "heading_1", contentText: "Weekly Review" },
      { type: "heading_2", contentText: "Wins" },
      { type: "bulleted_list_item", contentText: "What went well?" },
      { type: "heading_2", contentText: "Learnings" },
      { type: "bulleted_list_item", contentText: "What can be improved?" },
      { type: "heading_2", contentText: "Next week" },
      { type: "todo", contentText: "Top priority 1" },
      { type: "todo", contentText: "Top priority 2" },
    ],
  },
  {
    id: "weekly_sync",
    label: "Weekly Sync",
    title: "Weekly Sync",
    blocks: [
      { type: "heading_1", contentText: "Weekly Sync" },
      { type: "paragraph", contentText: "Date: " },
      { type: "paragraph", contentText: "Attendees: " },
      { type: "heading_2", contentText: "Updates" },
      { type: "bulleted_list_item", contentText: "Project update" },
      { type: "bulleted_list_item", contentText: "Risk / blocker" },
      { type: "heading_2", contentText: "Decisions" },
      { type: "bulleted_list_item", contentText: "Decision made" },
      { type: "heading_2", contentText: "Action items" },
      { type: "todo", contentText: "Owner + due date" },
    ],
  },
];

function getActivePageId(pathname: string | null): string | null {
  if (!pathname) return null;
  const pageMatch = pathname.match(/\/app\/page\/([^/]+)/);
  if (pageMatch?.[1]) return pageMatch[1];
  const dbMatch = pathname.match(/\/app\/database\/([^/]+)/);
  if (dbMatch?.[1]) return dbMatch[1];
  return null;
}

function readLinkedAccounts(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LINKED_ACCOUNTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return Array.from(new Set(parsed.map((item) => String(item).trim()).filter((item) => item.length > 0)));
  } catch {
    return [];
  }
}

function persistLinkedAccounts(ids: Iterable<string>) {
  if (typeof window === "undefined") return;
  const next = Array.from(new Set(Array.from(ids).map((item) => item.trim()).filter((item) => item.length > 0)));
  window.localStorage.setItem(LINKED_ACCOUNTS_KEY, JSON.stringify(next));
}

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();

  const [pages, setPages] = useState<PageItem[]>([]);
  const [trashPages, setTrashPages] = useState<PageItem[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>("");
  const [collapsed, setCollapsed] = useState(false);
  const [draggingPageId, setDraggingPageId] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [accountPanelOpen, setAccountPanelOpen] = useState(false);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [linkedAccountIds, setLinkedAccountIds] = useState<Set<string>>(new Set());
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteMessage, setInviteMessage] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteNotice, setInviteNotice] = useState<string | null>(null);
  const [expandedPageIds, setExpandedPageIds] = useState<Set<string>>(new Set());
  const [language, setLanguage] = useState<UiLanguage>("en");
  const [workspaceIcon, setWorkspaceIcon] = useState<string | null>(null);
  const [customEmojis, setCustomEmojis] = useState<CustomEmoji[]>([]);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const accountPanelRef = useRef<HTMLDivElement | null>(null);
  const createMenuRef = useRef<HTMLDivElement | null>(null);

  const activePageId = getActivePageId(pathname);

  async function refreshPages() {
    const response = await fetch("/api/pages");
    if (!response.ok) return;
    const data = await response.json();
    setPages(data.pages ?? []);
    if (data.workspace?.id) {
      setActiveWorkspaceId(data.workspace.id);
    }
  }

  async function refreshTrash() {
    const response = await fetch("/api/pages?scope=trash");
    if (!response.ok) return;
    const data = await response.json();
    setTrashPages(data.pages ?? []);
  }

  async function refreshWorkspaces() {
    const response = await fetch("/api/workspaces");
    if (!response.ok) return;
    const data = await response.json();
    const list = data.workspaces ?? [];
    setWorkspaces(list);
    const active = list.find((workspace: WorkspaceItem) => workspace.active);
    if (active) {
      setActiveWorkspaceId(active.id);
    }
  }

  async function refreshCurrentUser() {
    const response = await fetch("/api/me");
    if (!response.ok) return;
    const data = await response.json();
    if (data?.user) {
      setCurrentUser(data.user);
      setLinkedAccountIds((prev) => {
        const next = new Set(prev);
        next.add(String(data.user.id));
        persistLinkedAccounts(next);
        return next;
      });
    }
  }

  async function refreshAccounts() {
    const response = await fetch("/api/accounts");
    if (!response.ok) return;
    const data = await response.json();
    setAccounts(Array.isArray(data?.accounts) ? (data.accounts as AccountItem[]) : []);
  }

  useEffect(() => {
    setLanguage(getSavedLanguage());
    setLinkedAccountIds(new Set(readLinkedAccounts()));
    refreshPages();
    refreshTrash();
    refreshWorkspaces();
    refreshCurrentUser();
    refreshAccounts();
    setFavoriteIds(getFavoritePageIds());
    const handler = () => {
      refreshPages();
      refreshTrash();
      refreshWorkspaces();
      refreshAccounts();
      refreshCurrentUser();
    };
    window.addEventListener("pages:refresh", handler);
    const onFavorite = () => setFavoriteIds(getFavoritePageIds());
    window.addEventListener("favorites:changed", onFavorite);
    const onLanguage = () => setLanguage(getSavedLanguage());
    const onWorkspaceUi = () => {
      if (!activeWorkspaceId) return;
      setWorkspaceIcon(getWorkspaceIcon(activeWorkspaceId));
      setCustomEmojis(getCustomEmojis(activeWorkspaceId));
    };
    window.addEventListener("ui-language:changed", onLanguage);
    window.addEventListener("workspace-ui:changed", onWorkspaceUi);
    return () => {
      window.removeEventListener("pages:refresh", handler);
      window.removeEventListener("favorites:changed", onFavorite);
      window.removeEventListener("ui-language:changed", onLanguage);
      window.removeEventListener("workspace-ui:changed", onWorkspaceUi);
    };
  }, []);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    setWorkspaceIcon(getWorkspaceIcon(activeWorkspaceId));
    setCustomEmojis(getCustomEmojis(activeWorkspaceId));
  }, [activeWorkspaceId]);

  useEffect(() => {
    const onOutsideClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (accountPanelRef.current && !accountPanelRef.current.contains(target)) {
        setAccountPanelOpen(false);
      }
      if (createMenuRef.current && !createMenuRef.current.contains(target)) {
        setCreateMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", onOutsideClick);
    return () => window.removeEventListener("mousedown", onOutsideClick);
  }, []);

  useEffect(() => {
    setAccountPanelOpen(false);
    setCreateMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    const saved = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (saved === "1") {
      setCollapsed(true);
    }
    const savedExpanded = window.localStorage.getItem(SIDEBAR_EXPANDED_KEY);
    if (savedExpanded) {
      try {
        const parsed = JSON.parse(savedExpanded);
        if (Array.isArray(parsed)) {
          setExpandedPageIds(new Set(parsed.map((item) => String(item))));
        }
      } catch {}
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "\\") {
        event.preventDefault();
        setCollapsed((prev) => {
          const next = !prev;
          window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
          return next;
        });
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_EXPANDED_KEY, JSON.stringify([...expandedPageIds]));
  }, [expandedPageIds]);

  useEffect(() => {
    if (!activePageId) return;
    const byId = new Map(pages.map((page) => [page.id, page]));
    const ancestors: string[] = [];
    let cursor = byId.get(activePageId);
    while (cursor?.parentPageId) {
      ancestors.push(cursor.parentPageId);
      cursor = byId.get(cursor.parentPageId);
    }
    if (ancestors.length === 0) return;
    setExpandedPageIds((prev) => {
      const next = new Set(prev);
      for (const ancestorId of ancestors) {
        next.add(ancestorId);
      }
      return next;
    });
  }, [activePageId, pages]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
        signal: controller.signal,
      });
      if (!response.ok) return;
      const data = await response.json();
      setResults(data.results ?? []);
    }, 200);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query]);

  const tree = useMemo(() => {
    const visiblePages = pages.filter((page) => !page.id.startsWith(DATABASE_ROW_PAGE_PREFIX));
    const map = new Map<string, PageItem[]>();
    for (const page of visiblePages) {
      const key = page.parentPageId ?? "root";
      const list = map.get(key) ?? [];
      list.push(page);
      map.set(key, list);
    }

    for (const list of map.values()) {
      list.sort((a, b) => a.title.localeCompare(b.title));
    }

    return map;
  }, [pages]);

  const favoritePages = useMemo(
    () =>
      pages
        .filter((page) => !page.id.startsWith(DATABASE_ROW_PAGE_PREFIX))
        .filter((page) => favoriteIds.has(page.id))
        .sort((a, b) => a.title.localeCompare(b.title)),
    [favoriteIds, pages]
  );

  const switchableAccounts = useMemo(() => {
    const allowed = new Set(linkedAccountIds);
    if (currentUser?.id) allowed.add(currentUser.id);
    return accounts.filter((account) => allowed.has(account.id));
  }, [accounts, currentUser?.id, linkedAccountIds]);
  const activeWorkspaceRole = useMemo(
    () => workspaces.find((workspace) => workspace.id === activeWorkspaceId)?.role ?? null,
    [workspaces, activeWorkspaceId]
  );
  const canCreateContent = activeWorkspaceRole ? activeWorkspaceRole !== "viewer" : false;

  async function createPage(options: {
    parentPageId: string | null;
    type: "document" | "database";
    accessLevel: "workspace" | "private";
    createMode?: "full_page" | "inline";
    title?: string;
    icon?: string | null;
    navigate?: boolean;
    createInitialRow?: boolean;
  }) {
    if (!canCreateContent) return null;
    const response = await fetch("/api/pages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: options.title ?? (options.type === "database" ? "New database" : "New page"),
        parentPageId: options.parentPageId,
        activePageId,
        type: options.type,
        accessLevel: options.accessLevel,
        createMode: options.createMode ?? "full_page",
        icon: options.icon ?? null,
        createInitialRow: options.createInitialRow ?? true,
      }),
    });
    const data = await response.json();
    if (!response.ok) return null;
    window.dispatchEvent(new Event("pages:refresh"));
    const shouldNavigate = options.navigate ?? (options.createMode ?? "full_page") === "full_page";
    if (shouldNavigate) {
      router.push(options.type === "database" ? `/app/database/${data.page.id}` : `/app/page/${data.page.id}`);
    }
    return data.page as PageItem;
  }

  async function switchWorkspace(workspaceId: string) {
    await fetch("/api/workspaces/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspaceId }),
    });
    await refreshPages();
    await refreshTrash();
    await refreshWorkspaces();
    router.push("/app");
    router.refresh();
  }

  async function switchAccount(userId: string) {
    const response = await fetch("/api/accounts/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId }),
    });
    if (!response.ok) return;
    setLinkedAccountIds((prev) => {
      const next = new Set(prev);
      next.add(userId);
      persistLinkedAccounts(next);
      return next;
    });
    setAccountPanelOpen(false);
    await Promise.all([refreshCurrentUser(), refreshPages(), refreshTrash(), refreshWorkspaces(), refreshAccounts()]);
    router.push("/app");
    router.refresh();
  }

  async function sendInvite() {
    if (!inviteEmail.trim() || !inviteMessage.trim()) return;
    setInviteBusy(true);
    setInviteNotice(null);
    try {
      const response = await fetch("/api/workspaces/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: inviteEmail.trim(),
          message: inviteMessage.trim(),
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setInviteNotice(data?.error ?? "Failed to send invite");
        return;
      }
      setInviteNotice("Invite sent.");
      setInviteEmail("");
      setInviteMessage("");
      await refreshAccounts();
    } finally {
      setInviteBusy(false);
    }
  }

  function goToAddAccountLogin() {
    const returnTo = pathname && pathname.startsWith("/") ? pathname : "/app";
    setAccountPanelOpen(false);
    router.push(`/login?addAccount=1&returnTo=${encodeURIComponent(returnTo)}`);
  }

  async function movePage(draggedId: string, parentPageId: string | null) {
    await fetch(`/api/pages/${draggedId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parentPageId }),
    });
    window.dispatchEvent(new Event("pages:refresh"));
  }

  async function moveToTrash(pageId: string) {
    await fetch(`/api/pages/${pageId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trashAction: "move" }),
    });
    window.dispatchEvent(new Event("pages:refresh"));
    if (activePageId === pageId) {
      router.push("/app");
    }
  }

  async function restorePage(pageId: string) {
    await fetch(`/api/pages/${pageId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trashAction: "restore" }),
    });
    window.dispatchEvent(new Event("pages:refresh"));
  }

  async function permanentDelete(pageId: string) {
    await fetch(`/api/pages/${pageId}?permanent=1`, { method: "DELETE" });
    window.dispatchEvent(new Event("pages:refresh"));
  }

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  async function createFromTemplate(template: PageTemplate) {
    if (!canCreateContent) return;
    const page = await createPage({
      parentPageId: null,
      type: "document",
      accessLevel: "workspace",
      title: template.title,
      navigate: false,
    });
    if (!page?.id) return;

    let afterBlockId: string | undefined;
    for (const block of template.blocks) {
      const response = await fetch(`/api/pages/${page.id}/blocks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: block.type,
          contentText: block.contentText,
          afterBlockId,
        }),
      });
      if (!response.ok) continue;
      const data = await response.json();
      afterBlockId = data?.block?.id;
    }

    router.push(`/app/page/${page.id}`);
  }

  function renderPageIcon(page: PageItem) {
    const icon = page.icon?.trim() ?? "";
    const resolved = resolveIcon(icon, customEmojis);
    if (resolved?.type === "image") {
      return <img src={resolved.value} alt="" className="h-3.5 w-3.5 rounded object-cover" />;
    }
    const normalized = resolved?.type === "emoji" ? resolved.value.toLowerCase() : icon.toLowerCase();

    if (normalized) {
      if (normalized.includes("table") || normalized.includes("database")) {
        return <Database className="h-3.5 w-3.5" />;
      }
      if (normalized.includes("team") || normalized.includes("group")) {
        return <Users className="h-3.5 w-3.5" />;
      }
      if (normalized.includes("note") || normalized.includes("doc")) {
        return <FileText className="h-3.5 w-3.5" />;
      }
      if (resolved?.type === "emoji" && /\p{Extended_Pictographic}/u.test(resolved.value)) {
        return <span className="leading-none">{resolved.value}</span>;
      }
    }

    return page.type === "database" ? <Database className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />;
  }

  function renderTree(parentId: string | null, depth: number) {
    const list = tree.get(parentId ?? "root") ?? [];
    return list.map((page) => {
      const isActive = pathname?.includes(page.id);
      const href = page.type === "database" ? `/app/database/${page.id}` : `/app/page/${page.id}`;
      const children = tree.get(page.id) ?? [];
      const hasChildren = children.length > 0;
      const isExpanded = expandedPageIds.has(page.id);
      return (
        <div key={page.id} className="space-y-1">
          <div
            className={`group flex items-center justify-between overflow-hidden rounded-md px-2 py-1 text-[13px] ${
              isActive ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"
            }`}
            style={{ marginLeft: depth * 12 }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!draggingPageId || draggingPageId === page.id) return;
              movePage(draggingPageId, page.id);
            }}
          >
            <div className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
              <button
                type="button"
                draggable
                onDragStart={(event) => {
                  event.stopPropagation();
                  setDraggingPageId(page.id);
                  if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", page.id);
                  }
                }}
                onDragEnd={() => setDraggingPageId(null)}
                onClick={(event) => event.preventDefault()}
                className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[var(--muted)] opacity-0 transition hover:bg-[var(--hover)] group-hover:opacity-100"
                title="Drag to move page"
              >
                <GripVertical className="h-3 w-3" />
              </button>
              <button
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  if (!hasChildren) return;
                  setExpandedPageIds((prev) => {
                    const next = new Set(prev);
                    if (next.has(page.id)) next.delete(page.id);
                    else next.add(page.id);
                    return next;
                  });
                }}
                className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[var(--muted)] transition ${
                  hasChildren ? "opacity-0 hover:bg-[var(--hover)] group-hover:opacity-100" : "opacity-0"
                }`}
                title={hasChildren ? (isExpanded ? "Collapse" : "Expand") : undefined}
              >
                {hasChildren ? <ChevronDown className={`h-3 w-3 transition-transform ${isExpanded ? "" : "-rotate-90"}`} /> : null}
              </button>
              <Link
                href={href}
                draggable={false}
                onDragStart={(event) => event.preventDefault()}
                className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden"
                title={page.title}
              >
                <span className="mr-1 inline-flex h-4 w-4 items-center justify-center text-[12px] text-[var(--muted)]">
                  {renderPageIcon(page)}
                </span>
                <span className="truncate">{page.title}</span>
                {page.accessLevel === "private" ? (
                  <span className="ml-1 inline-flex shrink-0 items-center gap-1 text-[11px] text-[var(--muted)]">
                    <Lock className="h-3 w-3" />
                    {t(language, "private")}
                  </span>
                ) : null}
              </Link>
            </div>
            <div className="hidden items-center gap-1 group-hover:flex">
              <button
                onClick={() => createPage({ parentPageId: page.id, type: "document", accessLevel: "workspace", createMode: "inline" })}
                disabled={!canCreateContent}
                className="text-[11px] text-[var(--muted)] hover:text-[var(--text)] disabled:cursor-default disabled:opacity-35"
                title="Add child page"
              >
                +
              </button>
              <button
                onClick={() => moveToTrash(page.id)}
                className="text-[11px] text-[var(--muted)] hover:text-[#b42318]"
                title="Move to trash"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          {hasChildren && isExpanded ? renderTree(page.id, depth + 1) : null}
        </div>
      );
    });
  }

  return (
    <aside className={`${collapsed ? "w-[52px]" : "w-[280px]"} flex h-screen shrink-0 flex-col overflow-visible border-r border-[var(--line)] bg-[var(--sidebar)] px-2 py-3 transition-[width]`}>
      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <div className="flex items-center justify-between px-1">
          {!collapsed ? <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">{t(language, "workspace")}</p> : null}
          <button
            onClick={() => {
              setCollapsed((prev) => {
                const next = !prev;
                window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
                return next;
              });
            }}
            className="rounded px-2 py-1 text-xs text-[var(--muted)] hover:bg-[var(--hover)]"
            title="Toggle sidebar (Cmd/Ctrl + \\)"
          >
            {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
          </button>
        </div>

        <div ref={accountPanelRef} className="relative">
          <button
            onClick={() => setAccountPanelOpen((prev) => !prev)}
            className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--hover)] ${collapsed ? "justify-center" : ""}`}
            title={currentUser?.email ?? "Account"}
          >
            <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[var(--selected)] text-xs font-semibold text-[var(--text)]">
              {workspaceIcon ? (
                workspaceIcon.startsWith("data:") || workspaceIcon.startsWith("http") || workspaceIcon.startsWith("/") ? (
                  <img src={workspaceIcon} alt="Workspace icon" className="h-full w-full object-cover" />
                ) : (
                  <span className="text-sm leading-none">{workspaceIcon}</span>
                )
              ) : (
                currentUser?.initials ?? "U"
              )}
            </span>
            {!collapsed ? (
              <>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[13px] font-medium">{currentUser?.displayName ?? "User"}</span>
                  <span className="block truncate text-[11px] text-[var(--muted)]">{currentUser?.email ?? "No email"}</span>
                </span>
                <ChevronDown className="h-4 w-4 text-[var(--muted)]" />
              </>
            ) : null}
          </button>

          {accountPanelOpen ? (
            <div className={`absolute z-40 w-[340px] rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-xl ${collapsed ? "left-0 top-[105%]" : "left-0 top-[105%]"}`}>
              <div className="border-b border-[var(--line)] p-3">
                <p className="truncate text-[13px] font-semibold">{currentUser?.displayName ?? "User"}</p>
                <p className="truncate text-xs text-[var(--muted)]">{currentUser?.email ?? "No email"}</p>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => {
                      setAccountPanelOpen(false);
                      router.push("/app/settings");
                    }}
                    className="inline-flex items-center gap-1 rounded-md border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]"
                  >
                    <Settings className="h-4 w-4" />
                    Settings
                  </button>
                  <button
                    onClick={() => {
                      setInviteOpen(true);
                      setAccountPanelOpen(false);
                    }}
                    className="inline-flex items-center gap-1 rounded-md border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]"
                  >
                    <UserPlus className="h-4 w-4" />
                    {t(language, "invite_members")}
                  </button>
                </div>
              </div>

              <div className="max-h-[240px] overflow-y-auto overscroll-contain p-2">
                <p className="px-2 pb-1 text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">Accounts</p>
                {switchableAccounts.map((account) => (
                  <button
                    key={account.id}
                    onClick={() => {
                      void switchAccount(account.id);
                      setAccountPanelOpen(false);
                    }}
                    className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                  >
                    <span className="min-w-0 truncate">
                      <span className="block truncate">{account.email}</span>
                      <span className="block text-xs text-[var(--muted)]">{account.role}</span>
                    </span>
                    {account.active ? <Check className="h-4 w-4 text-[var(--muted)]" /> : null}
                  </button>
                ))}
                {switchableAccounts.length === 0 ? <p className="px-2 py-1 text-xs text-[var(--muted)]">No linked accounts</p> : null}
                <div className="my-2 border-t border-[var(--line)]" />
                <p className="px-2 pb-1 text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">Workspaces</p>
                {workspaces.map((workspace) => (
                  <button
                    key={workspace.id}
                    onClick={() => {
                      void switchWorkspace(workspace.id);
                      setAccountPanelOpen(false);
                    }}
                    className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                  >
                    <span className="min-w-0 truncate">{workspace.name}</span>
                    {workspace.id === activeWorkspaceId ? <Check className="h-4 w-4 text-[var(--muted)]" /> : null}
                  </button>
                ))}
              </div>

              <div className="border-t border-[var(--line)] p-2 text-sm">
                <button onClick={goToAddAccountLogin} className="mb-1 w-full rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]">{t(language, "add_account")}</button>
                <button onClick={logout} className="w-full rounded px-2 py-1.5 text-left text-[#b42318] hover:bg-[var(--hover)]">{t(language, "logout")}</button>
              </div>
            </div>
          ) : null}
        </div>

        {collapsed ? (
          <div className="space-y-1 px-1">
            <button
              onClick={() => createPage({ parentPageId: null, type: "document", accessLevel: "workspace" })}
              disabled={!canCreateContent}
              className="flex h-8 w-8 items-center justify-center rounded hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-40"
              title="New page"
            >
              <FilePlus2 className="h-4 w-4" />
            </button>
            <button
              onClick={() => createPage({ parentPageId: activePageId, type: "database", accessLevel: "workspace", createMode: "inline", navigate: false })}
              disabled={!canCreateContent}
              className="flex h-8 w-8 items-center justify-center rounded hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-40"
              title="New inline DB"
            >
              <Database className="h-4 w-4" />
            </button>
            <button
              onClick={() => searchInputRef.current?.focus()}
              className="flex h-8 w-8 items-center justify-center rounded hover:bg-[var(--hover)]"
              title="Search"
            >
              <Search className="h-4 w-4" />
            </button>
            <button
              onClick={() => router.push("/app/settings")}
              className="flex h-8 w-8 items-center justify-center rounded hover:bg-[var(--hover)]"
              title="Settings"
            >
              <Settings className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <div className="space-y-1">
                <button onClick={() => searchInputRef.current?.focus()} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-[var(--hover)]">
                  <Search className="h-4 w-4 text-[var(--muted)]" />
                  <span>{t(language, "search")}</span>
                </button>
                <button
                  onClick={() => router.push("/app/settings")}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-[var(--hover)]"
                >
                  <Settings className="h-4 w-4 text-[var(--muted)]" />
                  <span>{t(language, "settings")}</span>
                </button>

                <div ref={createMenuRef} className="relative">
                  <button
                    onClick={() => setCreateMenuOpen((prev) => !prev)}
                    disabled={!canCreateContent}
                    className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-[13px] hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-45"
                  >
                    <span className="inline-flex items-center gap-2">
                      <NotebookPen className="h-4 w-4 text-[var(--muted)]" />
                      {t(language, "new_page")}
                    </span>
                    <ChevronDown className="h-4 w-4 text-[var(--muted)]" />
                  </button>
                  {createMenuOpen ? (
                    <div className="absolute left-0 top-[105%] z-40 w-[220px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-1 shadow-xl">
                      <button
                        onClick={() => {
                          setCreateMenuOpen(false);
                          void createPage({ parentPageId: null, type: "document", accessLevel: "workspace", createMode: "full_page", navigate: true });
                        }}
                        disabled={!canCreateContent}
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                      >
                        <FilePlus2 className="h-4 w-4 text-[var(--muted)]" />
                        {t(language, "new_page")}
                      </button>
                      <button
                        onClick={() => {
                          setCreateMenuOpen(false);
                          void createPage({ parentPageId: null, type: "database", accessLevel: "workspace", createMode: "full_page", navigate: true });
                        }}
                        disabled={!canCreateContent}
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                      >
                        <Database className="h-4 w-4 text-[var(--muted)]" />
                        {t(language, "new_database")}
                      </button>
                      <button
                        onClick={() => {
                          setCreateMenuOpen(false);
                          void createPage({
                            parentPageId: activePageId,
                            type: "database",
                            accessLevel: "workspace",
                            createMode: "inline",
                            navigate: false,
                          });
                        }}
                        disabled={!canCreateContent}
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                      >
                        <Database className="h-4 w-4 text-[var(--muted)]" />
                        {t(language, "inline_database")}
                      </button>
                      <div className="my-1 border-t border-[var(--line)]" />
                      <p className="px-2 pb-1 pt-0.5 text-xs font-medium text-[var(--muted)]">{t(language, "templates")}</p>
                      {PAGE_TEMPLATES.map((template) => (
                        <button
                          key={template.id}
                          onClick={() => {
                            setCreateMenuOpen(false);
                            void createFromTemplate(template);
                          }}
                          disabled={!canCreateContent}
                          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                        >
                          <FileText className="h-4 w-4 text-[var(--muted)]" />
                          {template.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <input
                ref={searchInputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t(language, "search")}
                className="w-full rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-[13px]"
              />

              {query && results.length > 0 ? (
                <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-2">
                  {results.map((result) => (
                    <Link
                      key={result.id}
                      href={result.type === "database" ? `/app/database/${result.id}` : `/app/page/${result.id}`}
                      className="block rounded px-2 py-1 text-[13px] hover:bg-[var(--hover)]"
                      onClick={() => setQuery("")}
                    >
                      {result.title}
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <div className="rounded-md border border-transparent p-1">
                <p className="px-1 text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">{t(language, "favorites")}</p>
                <div className="space-y-1 pt-2">
                  {favoritePages.length === 0 ? (
                    <p className="px-2 py-1 text-xs text-[var(--muted)]">{t(language, "no_favorites")}</p>
                  ) : (
                    favoritePages.map((page) => (
                      <Link
                        key={page.id}
                        href={page.type === "database" ? `/app/database/${page.id}` : `/app/page/${page.id}`}
                        draggable={false}
                        onDragStart={(event) => event.preventDefault()}
                        className="flex items-center gap-2 rounded px-2 py-1 text-[13px] hover:bg-[var(--hover)]"
                      >
                        <Star className="h-3.5 w-3.5 text-[#f79009]" />
                        <span className="truncate">{page.title}</span>
                      </Link>
                    ))
                  )}
                </div>
              </div>

              <div
                className="rounded-md border border-transparent p-1"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (!draggingPageId) return;
                  movePage(draggingPageId, null);
                }}
              >
                <p className="px-1 text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">{t(language, "pages")}</p>
                <div className="space-y-1 pt-2">{renderTree(null, 0)}</div>
              </div>

              <div className="mt-3 space-y-1 border-t border-[var(--line)] pt-2">
                <p className="px-1 text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">{t(language, "trash")}</p>
                <div className="space-y-1">
                  {trashPages.length === 0 ? <p className="px-2 py-1 text-xs text-[var(--muted)]">{t(language, "no_trash")}</p> : null}
                  {trashPages.map((page) => (
                    <div key={page.id} className="flex items-center justify-between rounded px-2 py-1 text-[13px] hover:bg-[var(--hover)]">
                      <span className="truncate" title={page.title}>{page.title}</span>
                      <div className="flex items-center gap-1">
                        <button onClick={() => restorePage(page.id)} className="text-[11px] text-[var(--muted)] hover:text-[var(--text)]" title="Restore">
                          <RotateCcw className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => permanentDelete(page.id)} className="text-[11px] text-[var(--muted)] hover:text-[#b42318]" title="Delete permanently">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
      {inviteOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold">{t(language, "invite_members")}</p>
              <button onClick={() => setInviteOpen(false)} className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]">
                ✕
              </button>
            </div>
            <input
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="Email"
              type="email"
              className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
            />
            <textarea
              value={inviteMessage}
              onChange={(event) => setInviteMessage(event.target.value)}
              placeholder="Message"
              rows={4}
              className="mb-3 w-full resize-none rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setInviteOpen(false)}
                className="rounded border border-[var(--line)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]"
              >
                Cancel
              </button>
              <button
                onClick={() => void sendInvite()}
                disabled={!inviteEmail.trim() || !inviteMessage.trim() || inviteBusy}
                className="inline-flex items-center gap-1 rounded bg-[var(--blue)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                <SendHorizontal className="h-3.5 w-3.5" />
                {t(language, "send_invite")}
              </button>
            </div>
            {inviteNotice ? <p className="mt-2 text-xs text-[var(--muted)]">{inviteNotice}</p> : null}
          </div>
        </div>
      ) : null}
    </aside>
  );
}
