import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canCommentPage, canEditPage, getPageAccessContext } from "@/lib/access";

export async function PATCH(
  request: Request,
  { params }: { params: { id: string; commentId: string } }
) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
  });
  if (!context.ok) return context.response;

  const commentable = canCommentPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!commentable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const comment = await prisma.comment.findFirst({
    where: { id: params.commentId, pageId: params.id },
  });
  if (!comment) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const editable = canEditPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!editable && comment.authorId !== auth.session.userId) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);
  const content = body?.content?.toString().trim();
  if (!content) {
    return NextResponse.json({ error: "content is required" }, { status: 400 });
  }

  const updated = await prisma.comment.update({
    where: { id: params.commentId },
    data: { content },
    include: {
      author: { select: { id: true, email: true } },
      mentions: { include: { user: { select: { id: true, email: true } } } },
    },
  });

  return NextResponse.json({ comment: updated });
}

export async function DELETE(
  _: Request,
  { params }: { params: { id: string; commentId: string } }
) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
  });
  if (!context.ok) return context.response;

  const commentable = canCommentPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!commentable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const root = await prisma.comment.findFirst({
    where: { id: params.commentId, pageId: params.id },
    select: { id: true, authorId: true },
  });
  if (!root) {
    return NextResponse.json({ ok: true });
  }

  const editable = canEditPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!editable && root.authorId !== auth.session.userId) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const ids = new Set<string>([root.id]);
  let frontier = [root.id];
  while (frontier.length > 0) {
    const children = await prisma.comment.findMany({
      where: { pageId: params.id, parentCommentId: { in: frontier } },
      select: { id: true },
    });
    const next: string[] = [];
    for (const child of children) {
      if (!ids.has(child.id)) {
        ids.add(child.id);
        next.push(child.id);
      }
    }
    frontier = next;
  }

  await prisma.comment.deleteMany({
    where: { pageId: params.id, id: { in: [...ids] } },
  });

  return NextResponse.json({ ok: true, deleted: ids.size });
}
