import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { getActiveMembership } from "@/lib/access";

export async function GET(request: Request) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const membership = await getActiveMembership(auth.session.userId, auth.session.workspaceId);
  if (!membership) {
    return NextResponse.json({ results: [] });
  }

  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q")?.trim();

  if (!query) {
    return NextResponse.json({ results: [] });
  }

  const pages = await prisma.page.findMany({
    where: {
      workspaceId: membership.workspaceId,
      deletedAt: null,
      OR: [
        { accessLevel: "workspace" },
        { createdById: auth.session.userId },
        { permissions: { some: { userId: auth.session.userId } } },
      ],
      AND: [
        {
          OR: [
            { title: { contains: query, mode: "insensitive" } },
            { blocks: { some: { contentText: { contains: query, mode: "insensitive" } } } },
          ],
        },
      ],
    },
    select: { id: true, title: true, type: true },
    orderBy: { title: "asc" },
  });

  return NextResponse.json({ results: pages });
}
