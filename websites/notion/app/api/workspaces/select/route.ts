import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { WORKSPACE_COOKIE } from "@/lib/auth";

export async function POST(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const body = await request.json().catch(() => null);
  const workspaceId = body?.workspaceId?.toString();
  if (!workspaceId) {
    return NextResponse.json({ error: "workspaceId is required" }, { status: 400 });
  }

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId,
        userId: auth.session.userId,
      },
    },
  });

  if (!membership) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  await prisma.workspaceMembership.update({
    where: { id: membership.id },
    data: { lastActiveAt: new Date() },
  });

  const response = NextResponse.json({ ok: true });
  response.cookies.set(WORKSPACE_COOKIE, workspaceId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });

  return response;
}
