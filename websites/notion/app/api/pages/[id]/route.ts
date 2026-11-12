import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage, getPageAccessContext } from "@/lib/access";
import { makeId } from "@/lib/ids";

async function collectDescendants(rootId: string, workspaceId: string) {
  const pages = await prisma.page.findMany({
    where: { workspaceId },
    select: { id: true, parentPageId: true },
  });

  const childrenMap = new Map<string | null, string[]>();
  for (const page of pages) {
    const key = page.parentPageId ?? null;
    const list = childrenMap.get(key) ?? [];
    list.push(page.id);
    childrenMap.set(key, list);
  }

  const ids: string[] = [];
  const stack = [rootId];
  while (stack.length) {
    const current = stack.pop()!;
    ids.push(current);
    const children = childrenMap.get(current) ?? [];
    stack.push(...children);
  }

  return ids;
}

function getLinkedPageId(propsJson: unknown): string | null {
  if (!propsJson || typeof propsJson !== "object") return null;
  const source = propsJson as { linkedPageId?: unknown };
  const value = typeof source.linkedPageId === "string" ? source.linkedPageId.trim() : "";
  return value || null;
}

function isAutoLinkedBlock(propsJson: unknown): boolean {
  if (!propsJson || typeof propsJson !== "object") return false;
  const source = propsJson as { linkedPageAuto?: unknown };
  return source.linkedPageAuto === true;
}

async function removeAutoLinkedBlocksForPages(workspaceId: string, pageIds: string[]) {
  if (pageIds.length === 0) return;
  const blocks = await prisma.block.findMany({
    where: {
      page: { workspaceId },
    },
    select: { id: true, propsJson: true },
  });
  const target = new Set(pageIds);
  const deleteIds = blocks
    .filter((block) => {
      if (!isAutoLinkedBlock(block.propsJson)) return false;
      const linkedPageId = getLinkedPageId(block.propsJson);
      return linkedPageId ? target.has(linkedPageId) : false;
    })
    .map((block) => block.id);
  if (deleteIds.length === 0) return;
  await prisma.block.deleteMany({ where: { id: { in: deleteIds } } });
}

async function ensureAutoLinkBlockForPage(args: {
  parentPageId: string;
  linkedPageId: string;
  linkedPageType: "document" | "database";
  linkedPageTitle: string;
  linkedPageView: "link" | "inline";
}) {
  const blocks = await prisma.block.findMany({
    where: { pageId: args.parentPageId },
    select: { id: true, propsJson: true },
  });
  const existing = blocks.some((block) => {
    if (!isAutoLinkedBlock(block.propsJson)) return false;
    const linkedPageId = getLinkedPageId(block.propsJson);
    return linkedPageId === args.linkedPageId;
  });
  if (existing) return;

  const lastBlock = await prisma.block.findFirst({
    where: { pageId: args.parentPageId },
    orderBy: { position: "desc" },
    select: { position: true },
  });
  const href = args.linkedPageType === "database" ? `/app/database/${args.linkedPageId}` : `/app/page/${args.linkedPageId}`;
  await prisma.block.create({
    data: {
      id: makeId("block"),
      pageId: args.parentPageId,
      type: "paragraph",
      contentText: args.linkedPageTitle,
      position: (lastBlock?.position ?? -1) + 1,
      propsJson: {
        linkedPageId: args.linkedPageId,
        linkedPageType: args.linkedPageType,
        linkedPageView: args.linkedPageView,
        linkedPageAuto: true,
      },
      richTextJson: {
        marks: [{ start: 0, end: args.linkedPageTitle.length, link: href }],
      },
    },
  });
}

async function syncAutoLinkedBlockTitles(workspaceId: string, linkedPageId: string, nextTitle: string, linkedPageType: "document" | "database") {
  const blocks = await prisma.block.findMany({
    where: {
      page: { workspaceId },
    },
    select: { id: true, propsJson: true },
  });
  const href = linkedPageType === "database" ? `/app/database/${linkedPageId}` : `/app/page/${linkedPageId}`;
  const updateIds = blocks
    .filter((block) => {
      const targetPageId = getLinkedPageId(block.propsJson);
      return targetPageId === linkedPageId;
    })
    .map((block) => block.id);
  if (updateIds.length === 0) return;

  await prisma.block.updateMany({
    where: { id: { in: updateIds } },
    data: {
      contentText: nextTitle,
      richTextJson: { marks: [{ start: 0, end: nextTitle.length, link: href }] },
    },
  });
}

export async function GET(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const requestUrl = new URL(request.url);
  const includeTrashed = requestUrl.searchParams.get("includeTrashed") === "1";

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
    includeTrashed,
  });
  if (!context.ok) return context.response;

  const readable = canReadPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!readable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const page = await prisma.page.findUnique({
    where: { id: params.id },
    include: {
      permissions: {
        include: { user: { select: { id: true, email: true } } },
      },
    },
  });

  return NextResponse.json({ page });
}

export async function PATCH(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
    includeTrashed: true,
  });
  if (!context.ok) return context.response;

  const editable = canEditPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);
  const data: {
    title?: string;
    parentPageId?: string | null;
    accessLevel?: "workspace" | "private";
    icon?: string | null;
    deletedAt?: Date | null;
    isSmallText?: boolean;
    isFullWidth?: boolean;
    isLocked?: boolean;
    fontStyle?: "default" | "serif" | "mono";
  } = {};

  if (typeof body?.title === "string") {
    data.title = body.title.trim() || "Untitled";
  }

  if (body?.parentPageId !== undefined) {
    const parentPageId = body.parentPageId ? String(body.parentPageId) : null;
    if (parentPageId === params.id) {
      return NextResponse.json({ error: "Invalid parent" }, { status: 400 });
    }
    if (parentPageId) {
      const parent = await prisma.page.findUnique({ where: { id: parentPageId } });
      if (!parent || parent.workspaceId !== context.page.workspaceId || parent.deletedAt) {
        return NextResponse.json({ error: "Invalid parent" }, { status: 400 });
      }
    }
    data.parentPageId = parentPageId;
  }

  if (body?.accessLevel === "workspace" || body?.accessLevel === "private") {
    data.accessLevel = body.accessLevel;
  }

  if (body?.icon !== undefined) {
    data.icon = body.icon ? String(body.icon) : null;
  }

  if (body?.trashAction === "move") {
    const ids = await collectDescendants(params.id, context.page.workspaceId);
    const deletedAt = new Date();
    await prisma.page.updateMany({
      where: { id: { in: ids }, workspaceId: context.page.workspaceId },
      data: { deletedAt },
    });
    await removeAutoLinkedBlocksForPages(context.page.workspaceId, ids);
    const page = await prisma.page.findUnique({ where: { id: params.id } });
    return NextResponse.json({ page });
  }

  if (body?.trashAction === "restore") {
    const ids = await collectDescendants(params.id, context.page.workspaceId);
    await prisma.page.updateMany({
      where: { id: { in: ids }, workspaceId: context.page.workspaceId },
      data: { deletedAt: null },
    });
    const restoredPages = await prisma.page.findMany({
      where: { id: { in: ids }, workspaceId: context.page.workspaceId },
      select: { id: true, parentPageId: true, type: true, title: true },
    });
    for (const restoredPage of restoredPages) {
      if (!restoredPage.parentPageId) continue;
      await ensureAutoLinkBlockForPage({
        parentPageId: restoredPage.parentPageId,
        linkedPageId: restoredPage.id,
        linkedPageType: restoredPage.type,
        linkedPageTitle: restoredPage.title,
        linkedPageView: "link",
      });
    }
    const page = await prisma.page.findUnique({ where: { id: params.id } });
    return NextResponse.json({ page });
  }

  if (body?.isSmallText !== undefined) {
    data.isSmallText = Boolean(body.isSmallText);
  }

  if (body?.isFullWidth !== undefined) {
    data.isFullWidth = Boolean(body.isFullWidth);
  }

  if (body?.isLocked !== undefined) {
    data.isLocked = Boolean(body.isLocked);
  }

  if (body?.fontStyle === "default" || body?.fontStyle === "serif" || body?.fontStyle === "mono") {
    data.fontStyle = body.fontStyle;
  }

  const page = await prisma.page.update({
    where: { id: params.id },
    data,
  });

  if (data.parentPageId !== undefined && data.parentPageId !== context.page.parentPageId) {
    await removeAutoLinkedBlocksForPages(context.page.workspaceId, [page.id]);
    if (page.parentPageId) {
      await ensureAutoLinkBlockForPage({
        parentPageId: page.parentPageId,
        linkedPageId: page.id,
        linkedPageType: page.type,
        linkedPageTitle: page.title,
        linkedPageView: "link",
      });
    }
  }

  if (data.title !== undefined) {
    await syncAutoLinkedBlockTitles(context.page.workspaceId, page.id, page.title, page.type);
  }

  return NextResponse.json({ page });
}

export async function DELETE(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const requestUrl = new URL(request.url);
  const permanent = requestUrl.searchParams.get("permanent") === "1";

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
    includeTrashed: true,
  });
  if (!context.ok) return context.response;

  const editable = canEditPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const ids = await collectDescendants(params.id, context.page.workspaceId);
  if (permanent) {
    await removeAutoLinkedBlocksForPages(context.page.workspaceId, ids);
    await prisma.page.deleteMany({
      where: { id: { in: ids }, workspaceId: context.page.workspaceId, deletedAt: { not: null } },
    });
  } else {
    await removeAutoLinkedBlocksForPages(context.page.workspaceId, ids);
    await prisma.page.updateMany({
      where: { id: { in: ids }, workspaceId: context.page.workspaceId },
      data: { deletedAt: new Date() },
    });
  }

  return NextResponse.json({ ok: true });
}
