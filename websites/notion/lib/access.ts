import { PageAccessLevel, PagePermissionRole, WorkspaceRole } from "@prisma/client";
import { NextResponse } from "next/server";
import { prisma } from "./prisma";

export type MembershipWithWorkspace = Awaited<ReturnType<typeof getActiveMembership>>;

export async function getActiveMembership(userId: string, preferredWorkspaceId: string | null) {
  if (preferredWorkspaceId) {
    const preferred = await prisma.workspaceMembership.findUnique({
      where: {
        workspaceId_userId: {
          workspaceId: preferredWorkspaceId,
          userId,
        },
      },
      include: { workspace: true },
    });
    if (preferred) {
      return preferred;
    }
  }

  return prisma.workspaceMembership.findFirst({
    where: { userId },
    include: { workspace: true },
    orderBy: { createdAt: "asc" },
  });
}

export async function getPageAccessContext(params: {
  pageId: string;
  userId: string;
  preferredWorkspaceId: string | null;
  includeTrashed?: boolean;
}) {
  const page = await prisma.page.findUnique({
    where: { id: params.pageId },
    include: {
      permissions: {
        where: { userId: params.userId },
      },
    },
  });

  if (!page) {
    return {
      ok: false as const,
      response: NextResponse.json({ error: "Not found" }, { status: 404 }),
    };
  }

  if (page.deletedAt && !params.includeTrashed) {
    return {
      ok: false as const,
      response: NextResponse.json({ error: "Not found" }, { status: 404 }),
    };
  }

  const permissionRole = page.permissions[0]?.role;
  let membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: page.workspaceId,
        userId: params.userId,
      },
    },
    include: { workspace: true },
  });

  if (!membership) {
    const isCreator = page.createdById === params.userId;
    if (!isCreator && !permissionRole) {
      return {
        ok: false as const,
        response: NextResponse.json({ error: "Forbidden" }, { status: 403 }),
      };
    }
    const workspace = await prisma.workspace.findUnique({
      where: { id: page.workspaceId },
      select: { id: true, name: true, slug: true, createdAt: true, updatedAt: true },
    });
    if (!workspace) {
      return {
        ok: false as const,
        response: NextResponse.json({ error: "Not found" }, { status: 404 }),
      };
    }
    membership = {
      id: "__virtual_membership__",
      workspaceId: page.workspaceId,
      userId: params.userId,
      role: "viewer",
      lastActiveAt: null,
      createdAt: workspace.createdAt,
      workspace,
    };
  }

  return {
    ok: true as const,
    page,
    membership,
    permissionRole,
  };
}

function isWorkspaceEditor(role: WorkspaceRole) {
  return role === "owner" || role === "editor";
}

function isPermissionEditor(role: PagePermissionRole | undefined) {
  return role === "editor";
}

function isPermissionCommenter(role: PagePermissionRole | undefined) {
  return role === "commenter" || role === "editor";
}

export function canReadPage(params: {
  accessLevel: PageAccessLevel;
  workspaceRole: WorkspaceRole | null | undefined;
  isPageCreator: boolean;
  permissionRole: PagePermissionRole | undefined;
}) {
  if (params.accessLevel === "workspace") {
    return Boolean(params.workspaceRole) || params.isPageCreator || Boolean(params.permissionRole);
  }

  if (params.workspaceRole === "owner" || params.isPageCreator) {
    return true;
  }

  return Boolean(params.permissionRole);
}

export function canEditPage(params: {
  accessLevel: PageAccessLevel;
  workspaceRole: WorkspaceRole | null | undefined;
  isPageCreator: boolean;
  permissionRole: PagePermissionRole | undefined;
}) {
  if (params.accessLevel === "workspace") {
    if (params.isPageCreator) return true;
    if (params.workspaceRole && isWorkspaceEditor(params.workspaceRole)) return true;
    return isPermissionEditor(params.permissionRole);
  }

  if (params.workspaceRole === "owner" || params.isPageCreator) {
    return true;
  }

  return isPermissionEditor(params.permissionRole);
}

export function canCommentPage(params: {
  accessLevel: PageAccessLevel;
  workspaceRole: WorkspaceRole | null | undefined;
  isPageCreator: boolean;
  permissionRole: PagePermissionRole | undefined;
}) {
  if (params.accessLevel === "workspace") {
    if (params.workspaceRole) return true;
    if (params.isPageCreator) return true;
    return isPermissionCommenter(params.permissionRole);
  }

  if (params.workspaceRole === "owner" || params.isPageCreator) {
    return true;
  }

  return isPermissionCommenter(params.permissionRole);
}
