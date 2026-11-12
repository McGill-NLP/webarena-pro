import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { getActiveMembership } from "@/lib/access";
import { hashPassword } from "@/lib/password";
import { makeId } from "@/lib/ids";

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
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
  const message = body?.message?.toString().trim() ?? "";

  if (!email || !isValidEmail(email)) {
    return NextResponse.json({ error: "Valid email is required" }, { status: 400 });
  }
  if (!message) {
    return NextResponse.json({ error: "Message is required" }, { status: 400 });
  }

  let user = await prisma.user.findUnique({
    where: { email },
    select: { id: true, email: true },
  });
  let createdUser = false;
  if (!user) {
    user = await prisma.user.create({
      data: {
        id: makeId("user"),
        email,
        passwordHash: hashPassword("password123"),
      },
      select: { id: true, email: true },
    });
    createdUser = true;
  }

  await prisma.workspaceMembership.upsert({
    where: {
      workspaceId_userId: {
        workspaceId: membership.workspaceId,
        userId: user.id,
      },
    },
    update: {},
    create: {
      id: makeId("membership"),
      workspaceId: membership.workspaceId,
      userId: user.id,
      role: "viewer",
    },
  });

  return NextResponse.json({
    ok: true,
    invite: {
      email: user.email,
      message,
      createdUser,
      sentAt: new Date().toISOString(),
    },
  });
}
