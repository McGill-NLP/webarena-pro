import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canCommentPage, canReadPage, getPageAccessContext } from "@/lib/access";
import { makeId } from "@/lib/ids";

function extractMentionEmails(content: string) {
  const matches = content.match(/@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})/g) ?? [];
  return [...new Set(matches.map((match) => match.slice(1).toLowerCase()))];
}

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

  const comments = await prisma.comment.findMany({
    where: { pageId: params.id },
    include: {
      author: { select: { id: true, email: true } },
      mentions: { include: { user: { select: { id: true, email: true } } } },
    },
    orderBy: { createdAt: "asc" },
  });

  return NextResponse.json({ comments });
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

  const commentable = canCommentPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!commentable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);
  const content = body?.content?.toString().trim();
  const parentCommentId = body?.parentCommentId ? String(body.parentCommentId) : null;
  const mentionUserIds = Array.isArray(body?.mentionUserIds)
    ? body.mentionUserIds.map((id: unknown) => String(id))
    : [];

  if (!content) {
    return NextResponse.json({ error: "content is required" }, { status: 400 });
  }

  const emails = extractMentionEmails(content);
  const usersByEmail = emails.length
    ? await prisma.user.findMany({
        where: { email: { in: emails } },
        select: { id: true },
      })
    : [];

  const workspaceMembers = await prisma.workspaceMembership.findMany({
    where: { workspaceId: context.page.workspaceId },
    select: { userId: true },
  });
  const memberSet = new Set(workspaceMembers.map((member: { userId: string }) => member.userId));

  const mentionedIds = [...new Set([...usersByEmail.map((user: { id: string }) => user.id), ...mentionUserIds])].filter((id) =>
    memberSet.has(id)
  );

  const comment = await prisma.comment.create({
    data: {
      id: makeId("comment"),
      pageId: params.id,
      authorId: auth.session.userId,
      parentCommentId,
      content,
      mentions: {
        createMany: {
          data: mentionedIds.map((userId) => ({
            id: makeId("mention"),
            userId,
          })),
        },
      },
    },
    include: {
      author: { select: { id: true, email: true } },
      mentions: { include: { user: { select: { id: true, email: true } } } },
    },
  });

  return NextResponse.json({ comment });
}
