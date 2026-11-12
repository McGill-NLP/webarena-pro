import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

// Read-only evaluation API for the WebArena-Pro evaluator.
//
// Exposes backend state as JSON so tasks can be graded deterministically
// instead of relying on an LLM judge. Strictly read-only and gated by a
// secret token (WP_EVAL_TOKEN) the agent under test never sees. Disabled
// (403) when WP_EVAL_TOKEN is unset. Unlike the session APIs this is not
// workspace-scoped: verifiers need to see pages across all workspaces.
//
// The emitted shape is deliberately flat (workspace/parent/page names are
// inlined on each row) so same-object regex joins stay simple.
export async function GET(request: Request) {
  const token = process.env.WP_EVAL_TOKEN;
  if (!token || request.headers.get("x-eval-token") !== token) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const pages = await prisma.page.findMany({
    select: {
      id: true,
      title: true,
      icon: true,
      type: true,
      deletedAt: true,
      workspace: { select: { name: true } },
      parentPage: { select: { title: true } },
      createdBy: { select: { email: true } },
      shareLinks: { select: { token: true, isActive: true } },
    },
    orderBy: { createdAt: "asc" },
  });

  const blocks = await prisma.block.findMany({
    select: {
      pageId: true,
      type: true,
      contentText: true,
      page: { select: { title: true, workspace: { select: { name: true } } } },
    },
    orderBy: [{ pageId: "asc" }, { position: "asc" }],
  });

  const databases = await prisma.database.findMany({
    select: {
      id: true,
      page: {
        select: {
          title: true,
          workspace: { select: { name: true } },
          parentPage: { select: { title: true } },
        },
      },
      properties: { select: { name: true, type: true }, orderBy: { position: "asc" } },
      rows: {
        select: {
          title: true,
          cells: {
            select: {
              valueJson: true,
              property: { select: { name: true } },
            },
          },
        },
        orderBy: { position: "asc" },
      },
    },
  });

  // Per-page database aggregation ("two tables with 5 columns each on one
  // new page" style checks need a same-page join that flat rows can't give).
  const dbByPage = new Map<string, number[]>();
  for (const d of databases) {
    const key = `${d.page?.workspace?.name ?? ""}::${d.page?.title ?? ""}`;
    const list = dbByPage.get(key) ?? [];
    list.push(d.properties.length);
    dbByPage.set(key, list);
  }

  return NextResponse.json({
    workspaces: await prisma.workspace.findMany({ select: { name: true, slug: true } }),
    database_pages: Array.from(dbByPage.entries()).map(([key, counts]) => ({
      workspace: key.split("::")[0],
      page: key.split("::")[1],
      db_count: counts.length,
      property_counts: counts.sort(),
    })),
    pages: pages.map((p) => ({
      title: p.title,
      icon: p.icon,
      type: p.type,
      workspace: p.workspace?.name ?? null,
      parent: p.parentPage?.title ?? null,
      created_by: p.createdBy?.email ?? null,
      deleted: p.deletedAt !== null,
      published: p.shareLinks.some((s) => s.isActive),
      share_tokens: p.shareLinks.filter((s) => s.isActive).map((s) => s.token),
    })),
    blocks: blocks.map((b) => ({
      page: b.page?.title ?? null,
      workspace: b.page?.workspace?.name ?? null,
      type: b.type,
      text: b.contentText,
    })),
    databases: databases.map((d) => ({
      page: d.page?.title ?? null,
      workspace: d.page?.workspace?.name ?? null,
      parent: d.page?.parentPage?.title ?? null,
      property_count: d.properties.length,
      properties: d.properties.map((p) => ({ name: p.name, type: p.type })),
      rows: d.rows.map((r) => ({
        title: r.title,
        cells: Object.fromEntries(r.cells.map((c) => [c.property.name, c.valueJson])),
      })),
    })),
  });
}
