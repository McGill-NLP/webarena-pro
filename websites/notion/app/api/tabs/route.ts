import { NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canReadPage, getActiveMembership } from "@/lib/access";
import { makeId } from "@/lib/ids";

export async function GET() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ tabs: [] });
  }

  const tabs = await prisma.workspaceTab.findMany({
    where: { membershipId: membership.id, page: { deletedAt: null } },
    include: {
      page: true,
    },
    orderBy: { position: "asc" },
  });

  return NextResponse.json({ tabs });
}

export async function POST(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const body = await request.json().catch(() => null);
  const pageId = body?.pageId?.toString();
  if (!pageId) {
    return NextResponse.json({ error: "pageId is required" }, { status: 400 });
  }

  const page = await prisma.page.findUnique({
    where: { id: pageId },
    include: {
      permissions: {
        where: { userId: auth.session.userId },
      },
    },
  });

  if (!page || page.workspaceId !== membership.workspaceId || page.deletedAt) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const readable = canReadPage({
    accessLevel: page.accessLevel,
    workspaceRole: membership.role,
    isPageCreator: page.createdById === auth.session.userId,
    permissionRole: page.permissions[0]?.role,
  });
  if (!readable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const existing = await prisma.workspaceTab.findUnique({
    where: {
      membershipId_pageId: {
        membershipId: membership.id,
        pageId,
      },
    },
    include: { page: true },
  });

  if (existing) {
    return NextResponse.json({ tab: existing });
  }

  const last = await prisma.workspaceTab.findFirst({
    where: { membershipId: membership.id },
    orderBy: { position: "desc" },
  });

  let tab;
  try {
    tab = await prisma.workspaceTab.create({
      data: {
        id: makeId("tab"),
        membershipId: membership.id,
        pageId,
        position: (last?.position ?? -1) + 1,
      },
      include: { page: true },
    });
  } catch (error) {
    // In dev strict mode or concurrent requests, the same tab may be opened twice.
    // Treat unique conflicts as idempotent and return the existing tab.
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2002") {
      const concurrentExisting = await prisma.workspaceTab.findUnique({
        where: {
          membershipId_pageId: {
            membershipId: membership.id,
            pageId,
          },
        },
        include: { page: true },
      });
      if (concurrentExisting) {
        return NextResponse.json({ tab: concurrentExisting });
      }
    }
    throw error;
  }

  return NextResponse.json({ tab });
}

export async function PATCH(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const body = await request.json().catch(() => null);
  const tabId = body?.tabId?.toString();
  const position = Number(body?.position);
  if (!tabId || Number.isNaN(position)) {
    return NextResponse.json({ error: "tabId and numeric position are required" }, { status: 400 });
  }

  const tab = await prisma.workspaceTab.findUnique({ where: { id: tabId } });
  if (!tab || tab.membershipId !== membership.id) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const updated = await prisma.workspaceTab.update({
    where: { id: tabId },
    data: { position },
    include: { page: true },
  });

  return NextResponse.json({ tab: updated });
}

export async function DELETE(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const { searchParams } = new URL(request.url);
  const tabId = searchParams.get("tabId");
  if (!tabId) {
    return NextResponse.json({ error: "tabId is required" }, { status: 400 });
  }

  const tab = await prisma.workspaceTab.findUnique({ where: { id: tabId } });
  if (!tab || tab.membershipId !== membership.id) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await prisma.workspaceTab.delete({ where: { id: tabId } });
  return NextResponse.json({ ok: true });
}
