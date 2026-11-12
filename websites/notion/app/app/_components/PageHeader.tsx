"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Copy,
  Download,
  Expand,
  Globe,
  ImagePlus,
  Laptop,
  Link2,
  Lock,
  MessageSquare,
  MoreHorizontal,
  Moon,
  RotateCcw,
  Shrink,
  Star,
  Sun,
  Trash2,
  Type,
  Unlock,
} from "lucide-react";
import type { PageItem } from "./Sidebar";
import IconPicker from "./IconPicker";
import { applyThemeMode, getSavedThemeMode, type ThemeMode } from "@/lib/theme-mode";
import { getFavoritePageIds, setFavoritePage } from "@/lib/favorites";
import { getCustomEmojis, resolveIcon, type CustomEmoji } from "@/lib/workspace-ui";

type PageHeaderProps = {
  page: {
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
    workspaceId: string;
  };
  allPages: PageItem[];
  editable?: boolean;
};

type PermissionItem = {
  user: {
    id: string;
    email: string;
  };
  role: "editor" | "commenter" | "viewer";
};

type MemberItem = {
  user: {
    id: string;
    email: string;
  };
};

type ShareLinkItem = {
  id: string;
  token: string;
  isActive: boolean;
  expiresAt: string | null;
  createdAt: string;
};

type ExportBlock = {
  id: string;
  type: string;
  contentText: string | null;
  checked: boolean | null;
  imageUrl: string | null;
  parentBlockId: string | null;
  position: number;
  propsJson?: Record<string, any> | null;
};

type ExportComment = {
  content: string;
  createdAt: string;
  author: {
    email: string;
  };
};

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function downloadFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function blockDepth(block: ExportBlock, blockMap: Map<string, ExportBlock>) {
  let depth = 0;
  let currentParent = block.parentBlockId;
  const visited = new Set<string>();
  while (currentParent) {
    if (visited.has(currentParent)) break;
    visited.add(currentParent);
    const parent = blockMap.get(currentParent);
    if (!parent) break;
    depth += 1;
    currentParent = parent.parentBlockId;
  }
  return depth;
}

function blocksToMarkdown(blocks: ExportBlock[]) {
  const ordered = [...blocks].sort((a, b) => a.position - b.position);
  const map = new Map(ordered.map((block) => [block.id, block]));
  const numberedCountByParent = new Map<string, number>();
  const lines: string[] = [];

  for (const block of ordered) {
    const depth = blockDepth(block, map);
    const indent = "  ".repeat(depth);
    const text = block.contentText ?? "";
    const parentKey = block.parentBlockId ?? "root";

    if (block.type !== "numbered_list_item") {
      numberedCountByParent.delete(parentKey);
    }

    if (block.type === "heading_1") {
      lines.push(`${indent}# ${text}`);
      continue;
    }
    if (block.type === "heading_2") {
      lines.push(`${indent}## ${text}`);
      continue;
    }
    if (block.type === "heading_3") {
      lines.push(`${indent}### ${text}`);
      continue;
    }
    if (block.type === "bulleted_list_item") {
      lines.push(`${indent}- ${text}`);
      continue;
    }
    if (block.type === "numbered_list_item") {
      const next = (numberedCountByParent.get(parentKey) ?? 0) + 1;
      numberedCountByParent.set(parentKey, next);
      lines.push(`${indent}${next}. ${text}`);
      continue;
    }
    if (block.type === "todo") {
      lines.push(`${indent}- [${block.checked ? "x" : " "}] ${text}`);
      continue;
    }
    if (block.type === "toggle") {
      lines.push(`${indent}- ${text}`);
      continue;
    }
    if (block.type === "quote") {
      lines.push(`${indent}> ${text}`);
      continue;
    }
    if (block.type === "divider") {
      lines.push(`${indent}---`);
      continue;
    }
    if (block.type === "code") {
      lines.push(`${indent}\`\`\``);
      lines.push(`${indent}${text}`);
      lines.push(`${indent}\`\`\``);
      continue;
    }
    if (block.type === "callout") {
      lines.push(`${indent}> [!NOTE] ${text}`);
      continue;
    }
    if (block.type === "image") {
      const src = block.imageUrl ?? "";
      lines.push(`${indent}![${text || "image"}](${src})`);
      continue;
    }
    const inlineTable = (block.propsJson as any)?.inlineTable;
    if (inlineTable && Array.isArray(inlineTable.cells) && inlineTable.cells.length > 0) {
      const cells: string[][] = inlineTable.cells;
      const headerRow = cells[0] ?? [];
      const cols = Number(inlineTable.cols) || headerRow.length;
      const header = Array.from({ length: cols }, (_, i) => headerRow[i] ?? "");
      lines.push(`${indent}| ${header.join(" | ")} |`);
      lines.push(`${indent}| ${header.map(() => "---").join(" | ")} |`);
      for (let r = 1; r < cells.length; r++) {
        const row = Array.from({ length: cols }, (_, i) => cells[r]?.[i] ?? "");
        lines.push(`${indent}| ${row.join(" | ")} |`);
      }
      continue;
    }
    lines.push(`${indent}${text}`);
  }

  return lines.join("\n").trim();
}

function commentsToMarkdown(comments: ExportComment[]) {
  if (comments.length === 0) return "";
  const lines = ["", "## Comments", ""];
  for (const comment of comments) {
    lines.push(`- ${comment.author.email} (${new Date(comment.createdAt).toLocaleString()}): ${comment.content}`);
  }
  return lines.join("\n");
}

function markdownToHtmlDocument(title: string, markdown: string) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(title)}</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; padding: 32px; color: #1f2328; }
      pre { white-space: pre-wrap; line-height: 1.6; font-size: 14px; }
    </style>
  </head>
  <body>
    <h1>${escapeHtml(title)}</h1>
    <pre>${escapeHtml(markdown)}</pre>
  </body>
</html>`;
}

export default function PageHeader({ page, allPages, editable = true }: PageHeaderProps) {
  const router = useRouter();
  const [title, setTitle] = useState(page.title);
  const [parentId, setParentId] = useState(page.parentPageId ?? "");
  const [accessLevel, setAccessLevel] = useState<"workspace" | "private">(page.accessLevel);
  const [icon, setIcon] = useState(page.icon ?? "");
  const [saving, setSaving] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareTab, setShareTab] = useState<"share" | "publish">("share");
  const [themeMode, setThemeMode] = useState<ThemeMode>("system");
  const [isFavorite, setIsFavorite] = useState(false);
  const [permissions, setPermissions] = useState<PermissionItem[]>([]);
  const [members, setMembers] = useState<MemberItem[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [selectedRole, setSelectedRole] = useState<"editor" | "commenter" | "viewer">("viewer");
  const [shareLinks, setShareLinks] = useState<ShareLinkItem[]>([]);
  const [origin, setOrigin] = useState("");
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [includeCommentsInExport, setIncludeCommentsInExport] = useState(true);
  const [customEmojis, setCustomEmojis] = useState<CustomEmoji[]>([]);
  const [confirmDialog, setConfirmDialog] = useState<{ message: string; onConfirm: () => void } | null>(null);
  const [promptDialog, setPromptDialog] = useState<{ message: string; defaultValue: string; onSubmit: (value: string) => void } | null>(null);
  const [promptDialogValue, setPromptDialogValue] = useState("");
  const menuRef = useRef<HTMLDivElement | null>(null);
  const shareRef = useRef<HTMLDivElement | null>(null);

  async function updatePage(
    updated: Partial<{
      title: string;
      parentPageId: string | null;
      accessLevel: "workspace" | "private";
      icon: string | null;
      trashAction: "move" | "restore";
      isSmallText: boolean;
      isFullWidth: boolean;
      isLocked: boolean;
      fontStyle: "default" | "serif" | "mono";
    }>
  ) {
    if (!editable) return;
    setSaving(true);
    await fetch(`/api/pages/${page.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updated),
    });
    setSaving(false);
    window.dispatchEvent(new Event("pages:refresh"));
    router.refresh();
  }

  async function loadPermissions() {
    const response = await fetch(`/api/pages/${page.id}/permissions`);
    if (!response.ok) return;
    const data = await response.json();
    setPermissions(data.permissions ?? []);
    setMembers(data.members ?? []);
  }

  async function loadShareLinks() {
    const response = await fetch(`/api/pages/${page.id}/share-links`);
    if (!response.ok) return;
    const data = await response.json();
    setShareLinks(data.shareLinks ?? []);
  }

  async function createShareLink() {
    if (!editable) return null;
    const response = await fetch(`/api/pages/${page.id}/share-links`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!response.ok) return null;
    const data = await response.json();
    await loadShareLinks();
    return (data?.shareLink as ShareLinkItem | undefined) ?? null;
  }

  async function setShareLinkActive(shareLinkId: string, isActive: boolean) {
    if (!editable) return;
    await fetch(`/api/pages/${page.id}/share-links`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shareLinkId, isActive }),
    });
  }

  async function publishPage() {
    if (!editable) return;
    const alreadyPublished = activeShareLink;
    if (alreadyPublished) return;

    if (shareLinks.length > 0) {
      await setShareLinkActive(shareLinks[0].id, true);
      await loadShareLinks();
      return;
    }

    await createShareLink();
  }

  async function unpublishPage() {
    if (!editable) return;
    const active = shareLinks.filter((item) => item.isActive);
    await Promise.all(active.map((item) => setShareLinkActive(item.id, false)));
    await loadShareLinks();
  }

  async function copyToClipboard(value: string) {
    await navigator.clipboard.writeText(value);
  }

  async function duplicatePage() {
    if (!editable) return;
    const response = await fetch("/api/pages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: `${title || "Untitled"} (copy)`,
        type: page.type,
        accessLevel,
        parentPageId: parentId || null,
        icon: icon || null,
        createLinkInParent: false,
        createInitialRow: false,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data?.page?.id) return;
    const newPageId = data.page.id;

    if (page.type === "database") {
      // Copy database properties and rows
      const [dbRes, rowsRes] = await Promise.all([
        fetch(`/api/databases/${page.id}`),
        fetch(`/api/databases/${page.id}/rows`),
      ]);
      if (dbRes.ok && rowsRes.ok) {
        const dbData = await dbRes.json();
        const rowsData = await rowsRes.json();
        const sourceProps: any[] = dbData.database?.properties ?? [];
        const sourceRows: any[] = rowsData.rows ?? [];

        // Add non-title properties to new database
        const propIdMap = new Map<string, string>();
        for (const prop of sourceProps) {
          if (prop.type === "title") continue;
          const addRes = await fetch(`/api/databases/${newPageId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: "add_property",
              name: prop.name,
              type: prop.type,
              options: (prop.configJson as any)?.options,
            }),
          });
          if (addRes.ok) {
            const addData = await addRes.json();
            if (addData.property?.id) propIdMap.set(prop.id, addData.property.id);
          }
        }

        // Create rows and copy cell values
        for (const row of sourceRows) {
          const rowRes = await fetch(`/api/databases/${newPageId}/rows`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: row.title }),
          });
          if (!rowRes.ok) continue;
          const rowData = await rowRes.json();
          const newRowId = rowData.row?.id;
          if (!newRowId) continue;

          const cells: any[] = row.cells ?? [];
          await Promise.all(
            cells
              .filter((cell: any) => propIdMap.has(cell.propertyId))
              .map((cell: any) =>
                fetch(`/api/databases/${newPageId}/cells`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    rowId: newRowId,
                    propertyId: propIdMap.get(cell.propertyId),
                    value: cell.valueJson,
                  }),
                })
              )
          );
        }
      }
    } else {
      // Copy blocks from the source page
      const blocksRes = await fetch(`/api/pages/${page.id}/blocks`);
      if (blocksRes.ok) {
        const blocksData = await blocksRes.json();
        const sourceBlocks: any[] = blocksData.blocks ?? [];
        if (sourceBlocks.length > 0) {
          const idMap = new Map<string, string>();
          const cloned = sourceBlocks.map((block: any, index: number) => {
            const newId = `${newPageId}_b${index}`;
            idMap.set(block.id, newId);
            return { ...block, id: newId };
          });
          const remapped = cloned.map((block: any) => ({
            ...block,
            parentBlockId: block.parentBlockId ? idMap.get(block.parentBlockId) ?? null : null,
          }));
          await fetch(`/api/pages/${newPageId}/blocks`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ blocks: remapped }),
          });
        }
      }
    }

    window.dispatchEvent(new Event("pages:refresh"));
    router.push(page.type === "database" ? `/app/database/${newPageId}` : `/app/page/${newPageId}`);
  }

  async function moveToTrash() {
    if (!editable) return;
    await updatePage({ trashAction: "move" });
    router.push("/app");
  }

  async function restoreFromTrash() {
    if (!editable) return;
    await updatePage({ trashAction: "restore" });
  }

  function deletePermanently() {
    if (!editable) return;
    setMenuOpen(false);
    setConfirmDialog({
      message: "Delete this page permanently?",
      onConfirm: async () => {
        setConfirmDialog(null);
        await fetch(`/api/pages/${page.id}?permanent=1`, { method: "DELETE" });
        window.dispatchEvent(new Event("pages:refresh"));
        router.push("/app");
      },
    });
  }

  async function copyPageLink() {
    const url = `${window.location.origin}${page.type === "database" ? `/app/database/${page.id}` : `/app/page/${page.id}`}`;
    await copyToClipboard(url);
    setMenuOpen(false);
  }

  async function addPermission() {
    if (!editable) return;
    if (!selectedMemberId) return;
    const response = await fetch(`/api/pages/${page.id}/permissions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userId: selectedMemberId,
        role: selectedRole,
      }),
    });
    if (!response.ok) return;
    setSelectedMemberId("");
    await loadPermissions();
  }

  async function removePermission(userId: string) {
    if (!editable) return;
    const response = await fetch(`/api/pages/${page.id}/permissions`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId }),
    });
    if (!response.ok) return;
    await loadPermissions();
  }

  async function onIconChange(nextIcon: string) {
    if (!editable) return;
    setIcon(nextIcon);
    await updatePage({ icon: nextIcon });
  }

  async function onIconRemove() {
    if (!editable) return;
    setIcon("");
    await updatePage({ icon: null });
  }

  function persistCover(nextCover: string | null) {
    setCoverUrl(nextCover);
    try {
      if (!nextCover) {
        localStorage.removeItem(`page-cover:${page.id}`);
      } else {
        localStorage.setItem(`page-cover:${page.id}`, nextCover);
      }
    } catch {}
  }

  function onAddCover() {
    if (!editable) return;
    setMenuOpen(false);
    setPromptDialogValue(coverUrl ?? "");
    setPromptDialog({
      message: "Paste cover image URL",
      defaultValue: coverUrl ?? "",
      onSubmit: (value) => {
        setPromptDialog(null);
        const next = value.trim();
        if (!next) return;
        persistCover(next);
      },
    });
  }

  function onRemoveCover() {
    if (!editable) return;
    persistCover(null);
  }

  function onAddComment() {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("page:add-comment", {
        detail: { pageId: page.id },
      })
    );
  }

  async function collectExportMarkdown() {
    if (page.type === "database") {
      const [databaseRes, rowsRes] = await Promise.all([
        fetch(`/api/databases/${page.id}`),
        fetch(`/api/databases/${page.id}/rows`),
      ]);
      if (!databaseRes.ok || !rowsRes.ok) {
        throw new Error("Failed to load database for export");
      }
      const databaseData = await databaseRes.json();
      const rowsData = await rowsRes.json();
      const properties = databaseData?.database?.properties ?? [];
      const rows = rowsData?.rows ?? [];
      const header = properties.map((property: { name: string }) => property.name);
      const table: string[] = [];
      table.push(`| ${header.join(" | ")} |`);
      table.push(`| ${header.map(() => "---").join(" | ")} |`);
      for (const row of rows) {
        const values = properties.map((property: { id: string; type: string }) => {
          if (property.type === "title") return row.title ?? "";
          const cell = (row.cells ?? []).find((item: { propertyId: string }) => item.propertyId === property.id);
          const value = cell?.valueJson;
          if (Array.isArray(value)) return value.join(", ");
          return value == null ? "" : String(value);
        });
        table.push(`| ${values.join(" | ")} |`);
      }
      return `# ${title}\n\n${table.join("\n")}`;
    }

    const blocksRes = await fetch(`/api/pages/${page.id}/blocks`);
    if (!blocksRes.ok) {
      throw new Error("Failed to load blocks for export");
    }
    const blocksData = await blocksRes.json();
    const blocks = (blocksData.blocks ?? []) as ExportBlock[];
    let markdown = `# ${title}\n\n${blocksToMarkdown(blocks)}`;

    if (includeCommentsInExport) {
      const commentsRes = await fetch(`/api/pages/${page.id}/comments`);
      if (commentsRes.ok) {
        const commentsData = await commentsRes.json();
        markdown += commentsToMarkdown((commentsData.comments ?? []) as ExportComment[]);
      }
    }

    return markdown.trim();
  }

  async function exportPage(format: "pdf" | "markdown" | "html" | "txt") {
    if (format === "pdf") {
      setMenuOpen(false);
      setExportOpen(false);
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      window.print();
      return;
    }

    const markdown = await collectExportMarkdown();
    const safeTitle = (title.trim() || "untitled").replace(/[^\w\-]+/g, "_");

    if (format === "markdown") {
      downloadFile(`${safeTitle}.md`, markdown, "text/markdown;charset=utf-8");
      return;
    }

    if (format === "txt") {
      downloadFile(`${safeTitle}.txt`, markdown, "text/plain;charset=utf-8");
      return;
    }

    const html = markdownToHtmlDocument(title, markdown);
    downloadFile(`${safeTitle}.html`, html, "text/html;charset=utf-8");
  }

  useEffect(() => {
    setThemeMode(getSavedThemeMode());
    setIsFavorite(getFavoritePageIds().has(page.id));
    setOrigin(window.location.origin);
    try {
      const saved = localStorage.getItem(`page-cover:${page.id}`);
      setCoverUrl(saved && saved.trim().length > 0 ? saved : null);
    } catch {
      setCoverUrl(null);
    }
    setCustomEmojis(getCustomEmojis(page.workspaceId));

    const onFavoritesChanged = () => setIsFavorite(getFavoritePageIds().has(page.id));
    const onWorkspaceUiChanged = () => setCustomEmojis(getCustomEmojis(page.workspaceId));
    window.addEventListener("favorites:changed", onFavoritesChanged);
    window.addEventListener("workspace-ui:changed", onWorkspaceUiChanged);
    return () => {
      window.removeEventListener("favorites:changed", onFavoritesChanged);
      window.removeEventListener("workspace-ui:changed", onWorkspaceUiChanged);
    };
  }, [page.id, page.workspaceId]);

  useEffect(() => {
    if (!shareOpen) return;
    setShareTab("share");
    void loadPermissions();
    void loadShareLinks();
  }, [shareOpen]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (menuRef.current && !menuRef.current.contains(target)) {
        setMenuOpen(false);
        setExportOpen(false);
      }
      if (shareRef.current && !shareRef.current.contains(target)) {
        setShareOpen(false);
      }
    };
    window.addEventListener("mousedown", onClickOutside);
    return () => window.removeEventListener("mousedown", onClickOutside);
  }, []);

  function changeTheme(mode: ThemeMode) {
    setThemeMode(mode);
    applyThemeMode(mode);
  }

  const inTrash = Boolean(page.deletedAt);
  const activeShareLink = useMemo(
    () =>
      shareLinks.find((item) => {
        if (!item.isActive) return false;
        if (!item.expiresAt) return true;
        return new Date(item.expiresAt).getTime() > Date.now();
      }) ?? null,
    [shareLinks]
  );

  const publishedUrl = activeShareLink && origin ? `${origin}/share/${activeShareLink.token}` : null;
  const pageMap = useMemo(() => new Map(allPages.map((item) => [item.id, item])), [allPages]);

  const breadcrumbs = useMemo(() => {
    const chain: PageItem[] = [];
    let currentParentId = page.parentPageId;

    while (currentParentId) {
      const parent = pageMap.get(currentParentId);
      if (!parent) break;
      chain.unshift(parent);
      currentParentId = parent.parentPageId;
    }

    return chain;
  }, [page.parentPageId, pageMap]);

  return (
    <div className="space-y-3 pb-3">
      <div className="flex items-center justify-between gap-2 text-xs text-[var(--muted)] print:hidden">
        <div className="flex min-w-0 items-center gap-1">
          {breadcrumbs.map((crumb) => (
            <span key={crumb.id} className="inline-flex items-center gap-1">
              <Link
                href={crumb.type === "database" ? `/app/database/${crumb.id}` : `/app/page/${crumb.id}`}
                className="inline-flex max-w-[220px] items-center gap-1 truncate rounded px-1 hover:bg-[var(--hover)]"
              >
                {crumb.icon ? (() => {
                  const resolved = resolveIcon(crumb.icon, customEmojis);
                  if (!resolved) return null;
                  if (resolved.type === "image") {
                    return <img src={resolved.value} alt="" className="h-4 w-4 shrink-0 rounded object-cover" />;
                  }
                  return <span className="shrink-0 text-sm leading-none">{resolved.value}</span>;
                })() : null}
                {crumb.title}
              </Link>
              <span>/</span>
            </span>
          ))}
          <span className="inline-flex max-w-[260px] items-center gap-1 truncate rounded px-1 text-[var(--text)]">
            {icon ? (() => {
              const resolved = resolveIcon(icon, customEmojis);
              if (!resolved) return null;
              if (resolved.type === "image") {
                return <img src={resolved.value} alt="" className="h-4 w-4 shrink-0 rounded object-cover" />;
              }
              return <span className="shrink-0 text-sm leading-none">{resolved.value}</span>;
            })() : null}
            {title || "Untitled"}
          </span>
          <span className="rounded bg-[var(--hover)] px-2 py-0.5 text-[11px]">
            {accessLevel === "private" ? "Private" : "Workspace"}
          </span>
          {inTrash ? <span className="rounded bg-[var(--surface)] px-2 py-0.5 text-[11px] text-[#b42318]">In trash</span> : null}
        </div>

        <div className="relative flex items-center gap-1" ref={menuRef}>
          <div className="relative" ref={shareRef}>
            <button
              onClick={() => setShareOpen((prev) => !prev)}
              className="inline-flex items-center gap-1 rounded border border-[var(--line)] px-2 py-1 hover:bg-[var(--hover)]"
            >
              <Lock className="h-3.5 w-3.5" />
              Share
            </button>

            {shareOpen ? (
              <div className="absolute right-0 top-[110%] z-40 w-[420px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-3 text-sm shadow-xl">
                <div className="mb-3">
                  <p className="text-sm font-semibold">Share this page</p>
                  <p className="text-xs text-[var(--muted)]">Manage members and publish settings.</p>
                </div>

                <div className="mb-3 inline-flex rounded-lg bg-[var(--surface)] p-1">
                  <button
                    onClick={() => setShareTab("share")}
                    className={`rounded px-3 py-1.5 text-xs ${shareTab === "share" ? "bg-[var(--panel)] shadow-sm" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
                  >
                    Share
                  </button>
                  <button
                    onClick={() => setShareTab("publish")}
                    className={`rounded px-3 py-1.5 text-xs ${shareTab === "publish" ? "bg-[var(--panel)] shadow-sm" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
                  >
                    Publish
                  </button>
                </div>

                {shareTab === "publish" ? (
                  <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2">
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-xs font-medium text-[var(--muted)]">Publish to web</p>
                      {publishedUrl ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[#ecfdf3] px-2 py-0.5 text-[11px] text-[#067647]">
                          <Globe className="h-3 w-3" />
                          Published
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[var(--panel)] px-2 py-0.5 text-[11px] text-[var(--muted)]">
                          Not published
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {!publishedUrl ? (
                        <button
                          onClick={() => void publishPage()}
                          disabled={!editable}
                          className="rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                        >
                          Publish
                        </button>
                      ) : (
                        <button
                          onClick={() => void unpublishPage()}
                          disabled={!editable}
                          className="rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                        >
                          Unpublish
                        </button>
                      )}
                      {publishedUrl ? (
                        <button
                          onClick={() => void copyToClipboard(publishedUrl)}
                          className="rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs hover:bg-[var(--hover)]"
                        >
                          Copy link
                        </button>
                      ) : null}
                    </div>
                    {publishedUrl ? (
                      <a href={publishedUrl} target="_blank" rel="noreferrer" className="mt-2 block truncate text-xs text-[var(--blue)] underline">
                        {publishedUrl}
                      </a>
                    ) : null}
                  </div>
                ) : (
                  <>
                    <div className="mb-3 flex flex-wrap items-end gap-2">
                      <div className="min-w-[220px] flex-1">
                        <p className="mb-1 text-xs text-[var(--muted)]">Invite member</p>
                        <select
                          value={selectedMemberId}
                          onChange={(event) => setSelectedMemberId(event.target.value)}
                          disabled={!editable}
                          className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5"
                        >
                          <option value="">Select member</option>
                          {members
                            .filter((member) => !permissions.some((permission) => permission.user.id === member.user.id))
                            .map((member) => (
                              <option key={member.user.id} value={member.user.id}>
                                {member.user.email}
                              </option>
                            ))}
                        </select>
                      </div>
                      <div>
                        <p className="mb-1 text-xs text-[var(--muted)]">Role</p>
                        <select
                          value={selectedRole}
                          onChange={(event) => setSelectedRole(event.target.value as "editor" | "commenter" | "viewer")}
                          disabled={!editable}
                          className="rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5"
                        >
                          <option value="viewer">Viewer</option>
                          <option value="commenter">Commenter</option>
                          <option value="editor">Editor</option>
                        </select>
                      </div>
                      <button
                        onClick={addPermission}
                        disabled={!editable}
                        className="rounded border border-[var(--line)] px-3 py-1.5 hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                      >
                        Invite
                      </button>
                    </div>

                    <div className="space-y-1 border-t border-[var(--line)] pt-2">
                      <p className="text-xs font-medium text-[var(--muted)]">People with access</p>
                      {permissions.length === 0 ? <p className="text-xs text-[var(--muted)]">No explicit page members</p> : null}
                      {permissions.map((permission) => (
                        <div key={permission.user.id} className="flex items-center justify-between rounded px-2 py-1 hover:bg-[var(--hover)]">
                          <span className="truncate">{permission.user.email}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-[var(--muted)]">{permission.role}</span>
                            <button
                              onClick={() => void removePermission(permission.user.id)}
                              disabled={!editable}
                              className="text-xs text-[#b42318] disabled:cursor-default disabled:opacity-60"
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : null}
          </div>

          <button
            onClick={() => {
              const next = !isFavorite;
              setFavoritePage(page.id, next);
              setIsFavorite(next);
            }}
            className="rounded border border-[var(--line)] px-2 py-1 hover:bg-[var(--hover)]"
            title="Add to favorites"
          >
            <Star className={`h-4 w-4 ${isFavorite ? "fill-[#f79009] text-[#f79009]" : ""}`} />
          </button>

          <button
            onClick={() => setMenuOpen((prev) => !prev)}
            className="rounded border border-[var(--line)] px-2 py-1 hover:bg-[var(--hover)]"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>

          {menuOpen ? (
            <div className="absolute right-0 top-[110%] z-30 w-[320px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-1 text-sm shadow-lg">
              <button onClick={() => void copyPageLink()} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"><Link2 className="h-4 w-4" />Copy link</button>
              <button
                onClick={() => void duplicatePage()}
                disabled={!editable}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
              >
                <Copy className="h-4 w-4" />
                Duplicate
              </button>

              <div className="relative">
                <button
                  onClick={() => setExportOpen((prev) => !prev)}
                  className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                >
                  <span className="inline-flex items-center gap-2"><Download className="h-4 w-4" />Export</span>
                  <span>{exportOpen ? "−" : "+"}</span>
                </button>
                {exportOpen ? (
                  <div className="mx-1 mb-1 rounded-md border border-[var(--line)] bg-[var(--surface)] p-2">
                    <label className="mb-2 flex items-center gap-2 text-xs text-[var(--muted)]">
                      <input
                        type="checkbox"
                        checked={includeCommentsInExport}
                        onChange={(event) => setIncludeCommentsInExport(event.target.checked)}
                      />
                      Include comments
                    </label>
                    <div className="grid grid-cols-2 gap-1">
                      <button onClick={() => void exportPage("pdf")} className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]">PDF</button>
                      <button onClick={() => void exportPage("markdown")} className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]">Markdown</button>
                      <button onClick={() => void exportPage("html")} className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]">HTML</button>
                      <button onClick={() => void exportPage("txt")} className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]">Text</button>
                    </div>
                  </div>
                ) : null}
              </div>

              {!inTrash ? (
                <button
                  onClick={() => void moveToTrash()}
                  disabled={!editable}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                  Move to Trash
                </button>
              ) : null}
              {inTrash ? (
                <button
                  onClick={() => void restoreFromTrash()}
                  disabled={!editable}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                >
                  <RotateCcw className="h-4 w-4" />
                  Restore
                </button>
              ) : null}
              {inTrash ? (
                <button
                  onClick={() => void deletePermanently()}
                  disabled={!editable}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[#b42318] hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete permanently
                </button>
              ) : null}
              <button
                onClick={() => void updatePage({ isSmallText: !page.isSmallText })}
                disabled={!editable}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
              >
                <Type className="h-4 w-4" />
                Small text {page.isSmallText ? "on" : "off"}
              </button>
              <button
                onClick={() => void updatePage({ isFullWidth: !page.isFullWidth })}
                disabled={!editable}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
              >
                {page.isFullWidth ? <Shrink className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
                Full width {page.isFullWidth ? "on" : "off"}
              </button>
              <button
                onClick={() => void updatePage({ isLocked: !page.isLocked })}
                disabled={!editable}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
              >
                {page.isLocked ? <Unlock className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
                Lock page {page.isLocked ? "on" : "off"}
              </button>
              <div className="px-2 py-1 text-xs text-[var(--muted)]">Theme</div>
              <div className="flex gap-1 px-1 pb-2">
                <button onClick={() => changeTheme("light")} className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs ${themeMode === "light" ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"}`}><Sun className="h-3.5 w-3.5" />Light</button>
                <button onClick={() => changeTheme("dark")} className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs ${themeMode === "dark" ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"}`}><Moon className="h-3.5 w-3.5" />Dark</button>
                <button onClick={() => changeTheme("system")} className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs ${themeMode === "system" ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"}`}><Laptop className="h-3.5 w-3.5" />System</button>
              </div>
              <div className="px-2 py-1 text-xs text-[var(--muted)]">Font</div>
              <div className="flex gap-1 px-1 pb-1">
                <button
                  onClick={() => void updatePage({ fontStyle: "default" })}
                  disabled={!editable}
                  className={`rounded px-2 py-1 text-xs ${page.fontStyle === "default" ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"} disabled:cursor-default disabled:opacity-60`}
                >
                  Default
                </button>
                <button
                  onClick={() => void updatePage({ fontStyle: "serif" })}
                  disabled={!editable}
                  className={`rounded px-2 py-1 text-xs ${page.fontStyle === "serif" ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"} disabled:cursor-default disabled:opacity-60`}
                >
                  Serif
                </button>
                <button
                  onClick={() => void updatePage({ fontStyle: "mono" })}
                  disabled={!editable}
                  className={`rounded px-2 py-1 text-xs ${page.fontStyle === "mono" ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"} disabled:cursor-default disabled:opacity-60`}
                >
                  Mono
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-3 text-sm text-[var(--muted)]">
        <div className={editable ? "" : "pointer-events-none opacity-75"}>
          <IconPicker icon={icon || null} onChange={onIconChange} onRemove={onIconRemove} workspaceId={page.workspaceId} />
        </div>
        <button
          onClick={onAddCover}
          disabled={!editable}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
        >
          <ImagePlus className="h-4 w-4" />
          {coverUrl ? "Change cover" : "Add cover"}
        </button>
        {page.type === "document" ? (
          <button
            onClick={onAddComment}
            data-header-comment="1"
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-[var(--hover)]"
          >
            <MessageSquare className="h-4 w-4" />
            Add comment
          </button>
        ) : null}
        {coverUrl ? (
          <button
            onClick={onRemoveCover}
            disabled={!editable}
            className="rounded-md px-1.5 py-1 hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
          >
            Remove cover
          </button>
        ) : null}
      </div>

      {coverUrl ? (
        <div className="relative h-44 w-full overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface)]">
          <img src={coverUrl} alt="Cover" className="h-full w-full object-cover" />
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          readOnly={!editable}
          onBlur={() => {
            if (!editable) return;
            const safeTitle = title.trim() || "Untitled";
            setTitle(safeTitle);
            void updatePage({ title: safeTitle });
          }}
          className={`w-full border-0 bg-transparent text-5xl font-semibold tracking-[-0.03em] outline-none ${editable ? "cursor-text" : "cursor-default"}`}
        />
      </div>

      {saving ? <p className="text-xs text-[var(--muted)]">Saving...</p> : null}

      {confirmDialog ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setConfirmDialog(null)}>
          <div className="w-[360px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 text-sm">{confirmDialog.message}</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDialog(null)} className="rounded border border-[var(--line)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]">Cancel</button>
              <button onClick={() => confirmDialog.onConfirm()} className="rounded bg-[#b42318] px-3 py-1.5 text-sm text-white hover:opacity-90">Delete</button>
            </div>
          </div>
        </div>
      ) : null}

      {promptDialog ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setPromptDialog(null)}>
          <div className="w-[400px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="mb-3 text-sm font-medium">{promptDialog.message}</p>
            <form onSubmit={(e) => { e.preventDefault(); promptDialog.onSubmit(promptDialogValue); }}>
              <input
                autoFocus
                type="text"
                value={promptDialogValue}
                onChange={(e) => setPromptDialogValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") setPromptDialog(null); }}
                className="mb-3 w-full rounded border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--blue)]"
              />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setPromptDialog(null)} className="rounded border border-[var(--line)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]">Cancel</button>
                <button type="submit" className="rounded bg-[var(--blue)] px-3 py-1.5 text-sm text-white hover:opacity-90">OK</button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
