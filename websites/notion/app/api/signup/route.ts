import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { hashPassword } from "@/lib/password";
import { makeId } from "@/lib/ids";
import { SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/auth";

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function isStrongPassword(password: string) {
  if (password.length < 8) return false;
  return /[\d\W_]/.test(password);
}

function toSlug(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return normalized || "workspace";
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const email = body?.email?.toString().trim().toLowerCase() ?? "";
  const password = body?.password?.toString() ?? "";

  if (!email || !isValidEmail(email)) {
    return NextResponse.json({ error: "Valid email is required" }, { status: 400 });
  }
  if (!isStrongPassword(password)) {
    return NextResponse.json(
      { error: "Password must be at least 8 characters and include a number or special character" },
      { status: 400 }
    );
  }

  const existing = await prisma.user.findUnique({
    where: { email },
    select: { id: true },
  });
  if (existing) {
    return NextResponse.json({ error: "Account already exists" }, { status: 409 });
  }

  const user = await prisma.user.create({
    data: {
      id: makeId("user"),
      email,
      passwordHash: hashPassword(password),
    },
    select: { id: true, email: true },
  });

  let workspace = await prisma.workspace.findFirst({
    orderBy: { createdAt: "asc" },
    select: { id: true, name: true },
  });

  if (!workspace) {
    workspace = await prisma.workspace.create({
      data: {
        id: makeId("workspace"),
        name: "My Workspace",
        slug: `${toSlug(email.split("@")[0] ?? "workspace")}-${Date.now().toString(36)}`,
      },
      select: { id: true, name: true },
    });
  }

  const workspaceMemberCount = await prisma.workspaceMembership.count({
    where: { workspaceId: workspace.id },
  });

  await prisma.workspaceMembership.create({
    data: {
      id: makeId("membership"),
      workspaceId: workspace.id,
      userId: user.id,
      role: workspaceMemberCount === 0 ? "owner" : "viewer",
    },
  });

  const response = NextResponse.json({ ok: true, user: { id: user.id, email: user.email } });
  response.cookies.set(SESSION_COOKIE, user.id, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  response.cookies.set(WORKSPACE_COOKIE, workspace.id, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
  return response;
}
