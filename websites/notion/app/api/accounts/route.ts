import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { getActiveMembership } from "@/lib/access";
import { hashPassword } from "@/lib/password";
import { makeId } from "@/lib/ids";

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function isStrongPassword(password: string) {
  if (password.length < 8) return false;
  return /[\d\W_]/.test(password);
}

export async function GET() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ error: "No workspace membership" }, { status: 403 });
  }

  const accounts = await prisma.workspaceMembership.findMany({
    where: { workspaceId: membership.workspaceId },
    include: {
      user: {
        select: {
          id: true,
          email: true,
          createdAt: true,
        },
      },
    },
    orderBy: [{ role: "asc" }, { createdAt: "asc" }],
  });

  return NextResponse.json({
    accounts: accounts.map((item) => ({
      id: item.user.id,
      email: item.user.email,
      role: item.role,
      createdAt: item.user.createdAt.toISOString(),
      active: item.user.id === auth.session.userId,
    })),
  });
}

export async function POST(request: Request) {
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
  const email = body?.email?.toString().trim().toLowerCase() ?? "";
  const password = body?.password?.toString() ?? "password123";
  const role = body?.role === "owner" || body?.role === "editor" || body?.role === "viewer" ? body.role : "viewer";

  if (!email || !isValidEmail(email)) {
    return NextResponse.json({ error: "Valid email is required" }, { status: 400 });
  }
  if (!isStrongPassword(password)) {
    return NextResponse.json(
      { error: "Password must be at least 8 characters and include a number or special character" },
      { status: 400 }
    );
  }

  let user = await prisma.user.findUnique({
    where: { email },
    select: { id: true, email: true },
  });

  if (!user) {
    user = await prisma.user.create({
      data: {
        id: makeId("user"),
        email,
        passwordHash: hashPassword(password),
      },
      select: { id: true, email: true },
    });
  }

  await prisma.workspaceMembership.upsert({
    where: {
      workspaceId_userId: {
        workspaceId: membership.workspaceId,
        userId: user.id,
      },
    },
    update: {
      role,
    },
    create: {
      id: makeId("membership"),
      workspaceId: membership.workspaceId,
      userId: user.id,
      role,
    },
  });

  return NextResponse.json({
    account: {
      id: user.id,
      email: user.email,
      role,
    },
  });
}
