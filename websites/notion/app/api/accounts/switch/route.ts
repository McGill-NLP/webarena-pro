import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { getActiveMembership } from "@/lib/access";
import { SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/auth";

export async function POST(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ error: "No workspace membership" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);
  const userId = body?.userId?.toString();
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const targetMembership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: membership.workspaceId,
        userId,
      },
    },
  });

  if (!targetMembership) {
    return NextResponse.json({ error: "Target user is not in this workspace" }, { status: 403 });
  }

  await prisma.workspaceMembership.update({
    where: { id: targetMembership.id },
    data: { lastActiveAt: new Date() },
  });

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, userId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  response.cookies.set(WORKSPACE_COOKIE, membership.workspaceId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  return response;
}
