import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";

function displayNameFromEmail(email: string) {
  const localPart = email.split("@")[0] ?? "";
  const normalized = localPart.replace(/[._-]+/g, " ").trim();
  if (!normalized) return "User";
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function initialsFromDisplayName(displayName: string) {
  const pieces = displayName.split(/\s+/).filter(Boolean);
  if (pieces.length === 0) return "U";
  if (pieces.length === 1) return pieces[0].slice(0, 2).toUpperCase();
  return `${pieces[0][0] ?? ""}${pieces[1][0] ?? ""}`.toUpperCase();
}

export async function GET() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const user = await prisma.user.findUnique({
    where: { id: auth.session.userId },
    select: { id: true, email: true },
  });
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const memberships = await prisma.workspaceMembership.findMany({
    where: { userId: user.id },
    include: { workspace: true },
    orderBy: { createdAt: "asc" },
  });

  const displayName = displayNameFromEmail(user.email);
  const activeMembership =
    memberships.find((membership: { workspaceId: string }) => membership.workspaceId === auth.session.workspaceId) ??
    memberships[0] ??
    null;
  const creatorMembership = activeMembership
    ? await prisma.workspaceMembership.findFirst({
        where: { workspaceId: activeMembership.workspaceId },
        orderBy: { createdAt: "asc" },
        select: { userId: true },
      })
    : null;
  const isWorkspaceCreator = Boolean(activeMembership && creatorMembership?.userId === user.id);

  return NextResponse.json({
    user: {
      id: user.id,
      email: user.email,
      displayName,
      initials: initialsFromDisplayName(displayName),
    },
    activeWorkspace: activeMembership
      ? {
          id: activeMembership.workspace.id,
          name: activeMembership.workspace.name,
          slug: activeMembership.workspace.slug,
          role: activeMembership.role,
          isCreator: isWorkspaceCreator,
        }
      : null,
  });
}
