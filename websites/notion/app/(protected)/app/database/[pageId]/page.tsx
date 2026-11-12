import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { canEditPage, canReadPage } from "@/lib/access";
import { getSessionUserId } from "@/lib/auth";
import DatabaseTable from "@/app/app/_components/DatabaseTable";
import PageHeader from "@/app/app/_components/PageHeader";
import OpenTabSync from "@/app/app/_components/OpenTabSync";
import { pageIdForDatabaseRow } from "@/lib/database-row-page";

export default async function DatabasePage({ params }: { params: { pageId: string } }) {
  const userId = getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const page = await prisma.page.findUnique({
    where: { id: params.pageId },
    include: {
      permissions: {
        where: { userId },
      },
    },
  });

  if (!page) {
    return <div className="p-8 text-sm text-[var(--muted)]">Database page not found.</div>;
  }
  if (page.deletedAt) {
    return <div className="p-8 text-sm text-[var(--muted)]">This page is in trash.</div>;
  }

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: page.workspaceId,
        userId,
      },
    },
    include: { workspace: true },
  });

  const readable = canReadPage({
    accessLevel: page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: page.createdById === userId,
    permissionRole: page.permissions[0]?.role,
  });
  if (!readable) {
    return <div className="p-8 text-sm text-[var(--muted)]">You do not have access to this page.</div>;
  }

  const editable = canEditPage({
    accessLevel: page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: page.createdById === userId,
    permissionRole: page.permissions[0]?.role,
  });

  if (page.type !== "database") {
    redirect(`/app/page/${page.id}`);
  }

  const database = await prisma.database.findUnique({
    where: { pageId: page.id },
    include: {
      properties: { orderBy: { position: "asc" } },
      rows: { orderBy: { position: "asc" }, include: { cells: true } },
    },
  });

  if (!database) {
    return <div className="p-8 text-sm text-[var(--muted)]">Database not initialized.</div>;
  }

  const allPages = await prisma.page.findMany({
    where: {
      workspaceId: page.workspaceId,
      OR: membership
        ? [{ accessLevel: "workspace" }, { createdById: userId }, { permissions: { some: { userId } } }]
        : [{ createdById: userId }, { permissions: { some: { userId } } }],
    },
    select: {
      id: true,
      title: true,
      parentPageId: true,
      type: true,
      accessLevel: true,
      icon: true,
      deletedAt: true,
      isSmallText: true,
      isFullWidth: true,
      isLocked: true,
      fontStyle: true,
    },
    orderBy: { title: "asc" },
  });

  const serializableDatabase = {
    id: database.id,
    pageId: database.pageId,
    properties: database.properties,
    rows: database.rows.map((row) => ({
      ...row,
      pageId: pageIdForDatabaseRow(row.id),
      createdAt: row.createdAt.toISOString(),
      updatedAt: row.updatedAt.toISOString(),
    })),
  };

  return (
    <div
      className={`mx-auto w-full ${
        page.isFullWidth ? "" : "max-w-[1100px]"
      } ${
        page.fontStyle === "serif" ? "font-serif" : page.fontStyle === "mono" ? "font-mono" : ""
      } ${page.isSmallText ? "text-[14px]" : ""} pb-36`}
    >
      <OpenTabSync pageId={page.id} />
      <PageHeader page={page} allPages={allPages} editable={editable} />
      <DatabaseTable database={serializableDatabase} editable={editable} />
    </div>
  );
}
