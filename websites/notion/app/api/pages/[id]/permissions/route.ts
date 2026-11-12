import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage, getPageAccessContext } from "@/lib/access";
import { makeId } from "@/lib/ids";

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

  const permissions = await prisma.pagePermission.findMany({
    where: { pageId: params.id },
    include: { user: { select: { id: true, email: true } } },
    orderBy: { createdAt: "asc" },
  });

  const workspaceMembers = await prisma.workspaceMembership.findMany({
    where: { workspaceId: context.page.workspaceId },
    include: { user: { select: { id: true, email: true } } },
    orderBy: { createdAt: "asc" },
  });
  const candidateIds = new Set<string>();
  for (const member of workspaceMembers) {
    candidateIds.add(member.user.id);
  }
  for (const permission of permissions) {
    candidateIds.add(permission.user.id);
  }
  candidateIds.add(context.page.createdById);
  const users = await prisma.user.findMany({
    where: { id: { in: [...candidateIds] } },
    select: { id: true, email: true },
    orderBy: { email: "asc" },
  });
  const members = users.map((user) => ({ user }));

  return NextResponse.json({ permissions, members });
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

  const body = await request.json().catch(() => null);
  const userId = body?.userId?.toString();
  const role = body?.role;

  if (!userId || !["editor", "commenter", "viewer"].includes(role)) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { id: true },
  });
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  const permission = await prisma.pagePermission.upsert({
    where: {
      pageId_userId: {
        pageId: params.id,
        userId,
      },
    },
    update: { role },
    create: {
      id: makeId("perm"),
      pageId: params.id,
      userId,
      role,
    },
    include: {
      user: {
        select: {
          id: true,
          email: true,
        },
      },
    },
  });

  return NextResponse.json({ permission });
}

export async function DELETE(request: Request, { params }: { params: { id: string } }) {
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

  const body = await request.json().catch(() => null);
  const userId = body?.userId?.toString();
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  await prisma.pagePermission.deleteMany({
    where: {
      pageId: params.id,
      userId,
    },
  });

  return NextResponse.json({ ok: true });
}
