import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, getPageAccessContext } from "@/lib/access";
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

export async function PATCH(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const block = await prisma.block.findUnique({ where: { id: params.id } });
  if (!block) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const context = await getPageAccessContext({
    pageId: block.pageId,
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

  const body = await request.json().catch(() => null);

  if (context.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  if (body?.action === "duplicate") {
    const duplicated = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
      await tx.block.updateMany({
        where: { pageId: block.pageId, position: { gt: block.position } },
        data: { position: { increment: 1 } },
      });

      return tx.block.create({
        data: {
          id: makeId("block"),
          pageId: block.pageId,
          type: block.type,
          contentText: block.contentText,
          checked: block.checked,
          imageUrl: block.imageUrl,
          position: block.position + 1,
          parentBlockId: block.parentBlockId,
          propsJson: block.propsJson as any,
          richTextJson: block.richTextJson as any,
        },
      });
    });
    return NextResponse.json({ block: duplicated });
  }

  const data: {
    contentText?: string;
    checked?: boolean | null;
    type?: any;
    imageUrl?: string | null;
    position?: number;
    parentBlockId?: string | null;
    propsJson?: any;
    richTextJson?: any;
  } = {};

  if (body?.contentText !== undefined) {
    data.contentText = String(body.contentText);
  }

  if (body?.checked !== undefined) {
    data.checked = Boolean(body.checked);
  }

  if (body?.type !== undefined && BLOCK_TYPES.has(body.type)) {
    data.type = body.type;
    if (body.type === "todo" && block.checked === null) {
      data.checked = false;
    }
    if (body.type === "image" && !block.imageUrl) {
      data.imageUrl = "";
    }
  }

  if (body?.imageUrl !== undefined) {
    data.imageUrl = body.imageUrl ? String(body.imageUrl) : null;
  }

  if (body?.position !== undefined && Number.isInteger(body.position) && body.position >= 0) {
    data.position = Number(body.position);
  }

  if (body?.parentBlockId !== undefined) {
    data.parentBlockId = body.parentBlockId ? String(body.parentBlockId) : null;
  }

  if (body?.propsJson !== undefined) {
    data.propsJson = body.propsJson && typeof body.propsJson === "object" ? body.propsJson : null;
  }

  if (body?.richTextJson !== undefined) {
    data.richTextJson = body.richTextJson && typeof body.richTextJson === "object" ? body.richTextJson : null;
  }

  const updated = await prisma.block.update({
    where: { id: params.id },
    data,
  });

  return NextResponse.json({ block: updated });
}

export async function DELETE(_: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const block = await prisma.block.findUnique({ where: { id: params.id } });
  if (!block) {
    return NextResponse.json({ ok: true });
  }

  const context = await getPageAccessContext({
    pageId: block.pageId,
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

  await prisma.block.delete({ where: { id: params.id } });
  return NextResponse.json({ ok: true });
}
