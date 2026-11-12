import { NextResponse } from "next/server";
import { Prisma as PrismaValue } from "@prisma/client";
import type { Prisma, BlockType as PrismaBlockType } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage, getPageAccessContext } from "@/lib/access";
import { makeId } from "@/lib/ids";

const BLOCK_TYPES = new Set([
  "paragraph",
  "heading_1",
  "heading_2",
  "heading_3",
  "bulleted_list_item",
  "numbered_list_item",
  "todo",
  "toggle",
  "image",
  "quote",
  "divider",
  "code",
  "callout",
]);

type PatchBlockPayload = {
  id: string;
  type: PrismaBlockType;
  contentText: string | null;
  checked: boolean | null;
  imageUrl: string | null;
  position: number;
  parentBlockId: string | null;
  propsJson: Prisma.InputJsonValue | null;
  richTextJson: Prisma.InputJsonValue | null;
};

export async function GET(_: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
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

  const blocks = await prisma.block.findMany({
    where: { pageId: params.id },
    orderBy: { position: "asc" },
  });

  return NextResponse.json({ blocks });
}

export async function PATCH(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
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

  if (context.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const body = await request.json().catch(() => null);
  if (!Array.isArray(body?.blocks)) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }

  const mapped: PatchBlockPayload[] = (body.blocks as any[]).map(
    (item: any, index: number): PatchBlockPayload => {
      const type = (BLOCK_TYPES.has(item?.type) ? item.type : "paragraph") as PrismaBlockType;
      return {
        id: typeof item?.id === "string" && item.id.length > 0 ? item.id : makeId("block"),
        type,
        contentText: item?.contentText !== undefined ? String(item.contentText ?? "") : type === "divider" ? null : "",
        checked: type === "todo" ? Boolean(item?.checked) : null,
        imageUrl: type === "image" ? String(item?.imageUrl ?? "") : null,
        position: Number.isInteger(item?.position) ? Number(item.position) : index,
        parentBlockId: typeof item?.parentBlockId === "string" ? item.parentBlockId : null,
        propsJson:
          item?.propsJson && typeof item.propsJson === "object"
            ? (item.propsJson as Prisma.InputJsonValue)
            : null,
        richTextJson:
          item?.richTextJson && typeof item.richTextJson === "object"
            ? (item.richTextJson as Prisma.InputJsonValue)
            : null,
      };
    }
  );
  const normalized: PatchBlockPayload[] = mapped
    .sort((a: PatchBlockPayload, b: PatchBlockPayload) => a.position - b.position)
    .map((item: PatchBlockPayload, position: number) => ({ ...item, position }));

  const validIds = new Set(normalized.map((item) => item.id));
  const sanitized: PatchBlockPayload[] = normalized.map((item) => ({
    ...item,
    parentBlockId: item.parentBlockId && validIds.has(item.parentBlockId) ? item.parentBlockId : null,
  }));
  const itemMap = new Map<string, PatchBlockPayload>(sanitized.map((item) => [item.id, item]));
  const depthMemo = new Map<string, number>();
  const calcDepth = (id: string): number => {
    if (depthMemo.has(id)) return depthMemo.get(id)!;
    const item = itemMap.get(id);
    if (!item || !item.parentBlockId || !itemMap.has(item.parentBlockId)) {
      depthMemo.set(id, 0);
      return 0;
    }
    const depth = calcDepth(item.parentBlockId) + 1;
    depthMemo.set(id, depth);
    return depth;
  };
  const upsertOrder = [...sanitized].sort((a, b) => {
    const depthDiff = calcDepth(a.id) - calcDepth(b.id);
    if (depthDiff !== 0) return depthDiff;
    return a.position - b.position;
  });

  await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
    if (sanitized.length === 0) {
      await tx.block.deleteMany({ where: { pageId: params.id } });
      return;
    }

    await tx.block.deleteMany({
      where: {
        pageId: params.id,
        id: { notIn: sanitized.map((item) => item.id) },
      },
    });

    for (const block of upsertOrder) {
      await tx.block.upsert({
        where: { id: block.id },
        update: {
          pageId: params.id,
          type: block.type,
          contentText: block.contentText,
          checked: block.checked,
          imageUrl: block.imageUrl,
          position: block.position,
          parentBlockId: block.parentBlockId,
          propsJson: block.propsJson ?? PrismaValue.DbNull,
          richTextJson: block.richTextJson ?? PrismaValue.DbNull,
        },
        create: {
          id: block.id,
          pageId: params.id,
          type: block.type,
          contentText: block.contentText,
          checked: block.checked,
          imageUrl: block.imageUrl,
          position: block.position,
          parentBlockId: block.parentBlockId,
          propsJson: block.propsJson ?? PrismaValue.DbNull,
          richTextJson: block.richTextJson ?? PrismaValue.DbNull,
        },
      });
    }
  });

  return NextResponse.json({ ok: true, count: sanitized.length });
}

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
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

  if (context.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const body = await request.json().catch(() => null);
  const type = BLOCK_TYPES.has(body?.type) ? body.type : "paragraph";
  const afterBlockId = typeof body?.afterBlockId === "string" ? body.afterBlockId : null;
  const explicitPosition = Number.isInteger(body?.position) ? Number(body.position) : null;
  const parentBlockId = body?.parentBlockId ? String(body.parentBlockId) : null;
  const contentText =
    body?.contentText !== undefined ? String(body.contentText) : type === "divider" ? null : "";
  const checked = type === "todo" ? Boolean(body?.checked) : null;
  const imageUrl = type === "image" ? body?.imageUrl?.toString() ?? "" : null;
  const propsJson = body?.propsJson && typeof body.propsJson === "object" ? body.propsJson : null;
  const richTextJson = body?.richTextJson && typeof body.richTextJson === "object" ? body.richTextJson : null;

  if (parentBlockId) {
    const parent = await prisma.block.findFirst({ where: { id: parentBlockId, pageId: params.id }, select: { id: true } });
    if (!parent) {
      return NextResponse.json({ error: "Invalid parent block" }, { status: 400 });
    }
  }

  const block = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
    let insertPosition = explicitPosition;

    if (afterBlockId) {
      const afterBlock = await tx.block.findFirst({
        where: { id: afterBlockId, pageId: params.id },
        select: { position: true },
      });
      if (afterBlock) {
        insertPosition = afterBlock.position + 1;
      }
    }

    if (insertPosition === null || insertPosition < 0) {
      const lastBlock = await tx.block.findFirst({
        where: { pageId: params.id },
        orderBy: { position: "desc" },
        select: { position: true },
      });
      insertPosition = (lastBlock?.position ?? -1) + 1;
    } else {
      await tx.block.updateMany({
        where: { pageId: params.id, position: { gte: insertPosition } },
        data: { position: { increment: 1 } },
      });
    }

    return tx.block.create({
      data: {
        id: makeId("block"),
        pageId: params.id,
        type,
        contentText,
        imageUrl,
        checked,
        position: insertPosition,
        parentBlockId,
        propsJson,
        richTextJson,
      },
    });
  });

  return NextResponse.json({ block });
}
