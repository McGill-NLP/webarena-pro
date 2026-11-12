"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Database, FileText, Plus, X } from "lucide-react";

type TabItem = {
  id: string;
  pageId: string;
  position: number;
  page: {
    id: string;
    title: string;
    type: "document" | "database";
  };
};

export default function TabsBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [tabs, setTabs] = useState<TabItem[]>([]);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const [workspacePrompt, setWorkspacePrompt] = useState(false);
  const [workspaceName, setWorkspaceName] = useState("New workspace");
  const createMenuRef = useRef<HTMLDivElement | null>(null);

  async function refreshTabs() {
    const response = await fetch("/api/tabs");
    if (!response.ok) return;
    const data = await response.json();
    setTabs(data.tabs ?? []);
  }

  useEffect(() => {
    refreshTabs();
    const handler = () => refreshTabs();
    window.addEventListener("tabs:refresh", handler);
    return () => window.removeEventListener("tabs:refresh", handler);
  }, []);

  async function closeTab(tabId: string) {
    await fetch(`/api/tabs?tabId=${encodeURIComponent(tabId)}`, { method: "DELETE" });
    refreshTabs();
  }

  async function createNewPageTab() {
    const response = await fetch("/api/pages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "New page",
        type: "document",
        accessLevel: "workspace",
      }),
    });
    if (!response.ok) return;
    const data = await response.json();
    if (!data?.page?.id) return;
    window.dispatchEvent(new Event("pages:refresh"));
    window.dispatchEvent(new Event("tabs:refresh"));
    router.push(`/app/page/${data.page.id}`);
  }

  function openWorkspacePrompt() {
    setWorkspaceName("New workspace");
    setWorkspacePrompt(true);
  }

  async function submitCreateWorkspace() {
    const name = workspaceName.trim();
    setWorkspacePrompt(false);
    if (!name) return;
    const response = await fetch("/api/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) return;
    const data = await response.json().catch(() => null);
    const workspaceId = data?.workspace?.id ? String(data.workspace.id) : "";
    if (!workspaceId) return;
    await fetch("/api/workspaces/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspaceId }),
    });
    window.dispatchEvent(new Event("pages:refresh"));
    window.dispatchEvent(new Event("tabs:refresh"));
    router.push("/app");
    router.refresh();
  }

  useEffect(() => {
    if (!createMenuOpen) return;
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (createMenuRef.current?.contains(target)) return;
      setCreateMenuOpen(false);
    };
    window.addEventListener("mousedown", onMouseDown);
    return () => window.removeEventListener("mousedown", onMouseDown);
  }, [createMenuOpen]);

  return (
    <div className="sticky top-0 z-20 border-b border-[var(--line)] bg-[var(--panel)] px-3 py-1.5">
      <div className="mx-auto flex max-w-[1200px] items-center gap-1 overflow-x-auto scrollbar-thin">
        {tabs.map((tab) => {
          const active = pathname?.includes(tab.pageId);
          return (
            <div
              key={tab.id}
              className={`group flex items-center rounded-md px-2 py-1 text-sm ${
                active ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"
              }`}
            >
              <Link
                href={tab.page.type === "database" ? `/app/database/${tab.page.id}` : `/app/page/${tab.page.id}`}
                className="inline-flex max-w-[220px] items-center gap-1 truncate"
              >
                {tab.page.type === "database" ? <Database className="h-3.5 w-3.5 shrink-0 text-[var(--muted)]" /> : <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--muted)]" />}
                {tab.page.title}
              </Link>
              <button
                className="ml-2 text-xs text-[var(--muted)] hover:text-[var(--text)]"
                onClick={() => closeTab(tab.id)}
                aria-label="Close tab"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
        <div ref={createMenuRef} className="relative">
          <button
            onClick={() => setCreateMenuOpen((prev) => !prev)}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--line)] text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--text)]"
            title="Create"
          >
            <Plus className="h-4 w-4" />
          </button>
          {createMenuOpen ? (
            <div className="absolute right-0 top-[110%] z-30 w-44 rounded-md border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
              <button
                onClick={() => {
                  setCreateMenuOpen(false);
                  void createNewPageTab();
                }}
                className="flex w-full items-center rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
              >
                New page
              </button>
              <button
                onClick={() => {
                  setCreateMenuOpen(false);
                  openWorkspacePrompt();
                }}
                className="flex w-full items-center rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
              >
                New workspace
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {workspacePrompt ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setWorkspacePrompt(false)}>
          <div className="w-[400px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="mb-3 text-sm font-medium">Workspace name</p>
            <form onSubmit={(e) => { e.preventDefault(); void submitCreateWorkspace(); }}>
              <input
                autoFocus
                type="text"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") setWorkspacePrompt(false); }}
                className="mb-3 w-full rounded border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--blue)]"
              />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setWorkspacePrompt(false)} className="rounded border border-[var(--line)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]">Cancel</button>
                <button type="submit" className="rounded bg-[var(--blue)] px-3 py-1.5 text-sm text-white hover:opacity-90">Create</button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
