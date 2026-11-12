import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { verifyPassword } from "@/lib/password";
import { SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/auth";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const email = body?.email?.toString().trim();
  const password = body?.password?.toString() ?? "";

  if (!email || !password) {
    return NextResponse.json({ error: "Missing credentials" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { email } });
  if (!user || !verifyPassword(password, user.passwordHash)) {
    return NextResponse.json({ error: "Invalid email or password" }, { status: 401 });
  }

  const membership = await prisma.workspaceMembership.findFirst({
    where: { userId: user.id },
    orderBy: { createdAt: "asc" },
  });

  const response = NextResponse.json({
    ok: true,
    user: {
      id: user.id,
      email: user.email,
    },
    workspaceId: membership?.workspaceId ?? null,
  });
  response.cookies.set(SESSION_COOKIE, user.id, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });

  if (membership) {
    response.cookies.set(WORKSPACE_COOKIE, membership.workspaceId, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
    });
  }

  return response;
}
