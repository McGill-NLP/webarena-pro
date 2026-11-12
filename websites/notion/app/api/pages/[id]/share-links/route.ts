import crypto from "crypto";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage, getPageAccessContext } from "@/lib/access";
import { makeId } from "@/lib/ids";

function makeShareToken() {
  return crypto.randomBytes(16).toString("hex");
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

  const shareLinks = await prisma.shareLink.findMany({
    where: { pageId: params.id },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ shareLinks });
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
  const expiresAt = body?.expiresAt ? new Date(String(body.expiresAt)) : null;

  const shareLink = await prisma.shareLink.create({
    data: {
      id: makeId("share"),
      token: makeShareToken(),
      pageId: params.id,
      createdById: auth.session.userId,
      expiresAt,
      isActive: true,
    },
  });

  return NextResponse.json({ shareLink });
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

  const body = await request.json().catch(() => null);
  const shareLinkId = body?.shareLinkId?.toString();
  if (!shareLinkId) {
    return NextResponse.json({ error: "shareLinkId is required" }, { status: 400 });
  }

  const target = await prisma.shareLink.findFirst({
    where: { id: shareLinkId, pageId: params.id },
    select: { id: true },
  });
  if (!target) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const updated = await prisma.shareLink.update({
    where: { id: shareLinkId },
    data: {
      isActive: body?.isActive === undefined ? undefined : Boolean(body.isActive),
      expiresAt: body?.expiresAt === undefined ? undefined : body.expiresAt ? new Date(String(body.expiresAt)) : null,
    },
  });

  return NextResponse.json({ shareLink: updated });
}
