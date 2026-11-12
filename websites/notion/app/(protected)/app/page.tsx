import { redirect } from "next/navigation";
import { getSessionUserId, getSessionWorkspaceId } from "@/lib/auth";
import { getActiveMembership } from "@/lib/access";
import { prisma } from "@/lib/prisma";

export default async function AppIndex() {
  const userId = getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const membership = await getActiveMembership(userId, getSessionWorkspaceId());
  if (!membership) {
    return <div className="p-8 text-sm text-[var(--muted)]">No workspace membership found.</div>;
  }

  const page = await prisma.page.findFirst({
    where: {
      workspaceId: membership.workspaceId,
      deletedAt: null,
      OR: [
        { accessLevel: "workspace" },
        { createdById: userId },
        { permissions: { some: { userId } } },
      ],
    },
    orderBy: { title: "asc" },
  });

  if (!page) {
    return <div className="p-8 text-sm text-[var(--muted)]">This workspace has no pages yet.</div>;
  }

  redirect(page.type === "database" ? `/app/database/${page.id}` : `/app/page/${page.id}`);
}
