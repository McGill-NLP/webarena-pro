import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { makeId } from "@/lib/ids";
import { getActiveMembership } from "@/lib/access";
import { SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/auth";

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)+/g, "")
    .slice(0, 48);
}

export async function GET() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const memberships = await prisma.workspaceMembership.findMany({
    where: { userId: auth.session.userId },
    include: {
      workspace: true,
    },
    orderBy: { createdAt: "asc" },
  });

  return NextResponse.json({
    workspaces: memberships.map((membership: { workspace: { id: string; name: string; slug: string }; role: string; workspaceId: string }) => ({
      id: membership.workspace.id,
      name: membership.workspace.name,
      slug: membership.workspace.slug,
      role: membership.role,
      active: membership.workspaceId === auth.session.workspaceId,
    })),
  });
}

export async function POST(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const body = await request.json().catch(() => null);
  const name = body?.name?.toString().trim();
  if (!name) {
    return NextResponse.json({ error: "Workspace name is required" }, { status: 400 });
  }

  const slugBase = slugify(name) || "workspace";
  let slug = slugBase;
  let suffix = 1;
  while (await prisma.workspace.findUnique({ where: { slug } })) {
    slug = `${slugBase}-${suffix}`;
    suffix += 1;
  }

  const workspace = await prisma.workspace.create({
    data: {
      id: makeId("ws"),
      name,
      slug,
      memberships: {
        create: {
          id: makeId("membership"),
          userId: auth.session.userId,
          role: "owner",
        },
      },
    },
  });

  return NextResponse.json({ workspace });
}

export async function PATCH(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ error: "No workspace membership" }, { status: 403 });
  }
  if (membership.role !== "owner" && membership.role !== "editor") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);
  const name = body?.name?.toString().trim();
  if (!name) {
    return NextResponse.json({ error: "Workspace name is required" }, { status: 400 });
  }

  const workspace = await prisma.workspace.update({
    where: { id: membership.workspaceId },
    data: { name },
    select: { id: true, name: true, slug: true },
  });

  return NextResponse.json({ workspace });
}

export async function DELETE() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ error: "No workspace membership" }, { status: 403 });
  }
  if (membership.role !== "owner") {
    return NextResponse.json({ error: "Only owner can delete workspace" }, { status: 403 });
  }

  const fallbackMembership = await prisma.workspaceMembership.findFirst({
    where: {
      userId: auth.session.userId,
      workspaceId: { not: membership.workspaceId },
    },
    orderBy: { createdAt: "asc" },
    select: { workspaceId: true },
  });

  await prisma.workspace.delete({
    where: { id: membership.workspaceId },
  });

  const response = NextResponse.json({
    ok: true,
    nextWorkspaceId: fallbackMembership?.workspaceId ?? null,
  });

  if (fallbackMembership?.workspaceId) {
    response.cookies.set(WORKSPACE_COOKIE, fallbackMembership.workspaceId, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
    });
  } else {
    response.cookies.set(WORKSPACE_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
    response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
  }

  return response;
}
