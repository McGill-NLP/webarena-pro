import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { getActiveMembership } from "@/lib/access";

export async function GET() {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ error: "No workspace membership" }, { status: 403 });
  }

  const now = new Date();
  const links = await prisma.shareLink.findMany({
    where: {
      page: {
        workspaceId: membership.workspaceId,
        deletedAt: null,
      },
      isActive: true,
      OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
    },
    include: {
      page: {
        select: {
          id: true,
          title: true,
          type: true,
        },
      },
    },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({
    count: links.length,
    pages: links.map((item) => ({
      id: item.page.id,
      title: item.page.title,
      type: item.page.type,
      token: item.token,
      shareUrl: `/share/${item.token}`,
      createdAt: item.createdAt.toISOString(),
      expiresAt: item.expiresAt?.toISOString() ?? null,
    })),
  });
}
