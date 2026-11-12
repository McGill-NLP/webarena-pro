import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canReadPage, getActiveMembership } from "@/lib/access";

export async function GET() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ error: "No workspace membership" }, { status: 403 });
  }

  const [members, pages] = await Promise.all([
    prisma.workspaceMembership.findMany({
      where: { workspaceId: membership.workspaceId },
      include: {
        user: {
          select: { id: true, email: true },
        },
      },
      orderBy: [{ role: "asc" }, { createdAt: "asc" }],
    }),
    prisma.page.findMany({
      where: {
        workspaceId: membership.workspaceId,
        deletedAt: null,
        createdById: auth.session.userId,
      },
      select: {
        id: true,
        title: true,
        type: true,
        accessLevel: true,
        createdById: true,
        permissions: {
          select: { userId: true, role: true },
        },
      },
      orderBy: { title: "asc" },
    }),
  ]);

  const memberByUserId = new Map(members.map((item) => [item.userId, item]));
  const permissionUserIds = new Set<string>();
  for (const page of pages) {
    for (const permission of page.permissions) {
      if (permission.userId !== auth.session.userId) {
        permissionUserIds.add(permission.userId);
      }
    }
  }

  const candidateIds = new Set<string>();
  for (const memberItem of members) {
    if (memberItem.userId !== auth.session.userId) candidateIds.add(memberItem.userId);
  }
  for (const permissionUserId of permissionUserIds) {
    candidateIds.add(permissionUserId);
  }

  const users = await prisma.user.findMany({
    where: { id: { in: [...candidateIds] } },
    select: { id: true, email: true },
    orderBy: { email: "asc" },
  });

  const people = users.map((user) => {
    const memberItem = memberByUserId.get(user.id) ?? null;
    const accessiblePages = pages
      .filter((page) => {
        const permissionRole = page.permissions.find((permission) => permission.userId === user.id)?.role;
        return canReadPage({
          accessLevel: page.accessLevel,
          workspaceRole: memberItem?.role ?? null,
          isPageCreator: page.createdById === user.id,
          permissionRole,
        });
      })
      .map((page) => {
        const explicit = page.permissions.find((permission) => permission.userId === user.id)?.role ?? null;
        let role = explicit;
        if (!role && page.createdById === user.id) role = "editor";
        if (!role && memberItem) role = memberItem.role === "viewer" ? "viewer" : "editor";
        if (!role) role = "viewer";
        return {
          id: page.id,
          title: page.title,
          type: page.type,
          accessLevel: page.accessLevel,
          role,
        };
      });

    return {
      user,
      workspaceRole: memberItem?.role ?? "page_only",
      pages: accessiblePages,
    };
  });

  return NextResponse.json({ people });
}
