import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, getPageAccessContext } from "@/lib/access";

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const body = await request.json().catch(() => null);
  const direction = body?.direction === "up" || body?.direction === "down" ? body.direction : null;
  const targetIndex = Number.isInteger(body?.targetIndex) ? Number(body.targetIndex) : null;

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

  if (context.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const blocks = await prisma.block.findMany({
    where: { pageId: block.pageId },
    orderBy: { position: "asc" },
    select: { id: true },
  });

  const index = blocks.findIndex((item: { id: string }) => item.id === block.id);
  if (index === -1) {
    return NextResponse.json({ ok: true });
  }

  let nextIndex = targetIndex;
  if (nextIndex === null && direction) {
    nextIndex = direction === "up" ? index - 1 : index + 1;
  }
  if (nextIndex === null) {
    return NextResponse.json({ error: "Invalid move request" }, { status: 400 });
  }

  const clamped = Math.max(0, Math.min(blocks.length - 1, nextIndex));
  if (clamped === index) {
    return NextResponse.json({ ok: true });
  }

  const reordered = [...blocks];
  const [moved] = reordered.splice(index, 1);
  reordered.splice(clamped, 0, moved);

  await prisma.$transaction(
    reordered.map((item: { id: string }, position) =>
      prisma.block.update({
        where: { id: item.id },
        data: { position },
      })
    )
  );

  return NextResponse.json({ ok: true });
}
