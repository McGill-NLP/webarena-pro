import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { canEditPage, canReadPage } from "@/lib/access";
import { getSessionUserId } from "@/lib/auth";
import PageEditor from "@/app/app/_components/PageEditor";
import PageHeader from "@/app/app/_components/PageHeader";
import OpenTabSync from "@/app/app/_components/OpenTabSync";
import RowPropertiesPanel from "@/app/app/_components/RowPropertiesPanel";
import { rowIdFromDatabaseRowPageId } from "@/lib/database-row-page";
import { makeId } from "@/lib/ids";

async function ensureDatabaseRowPage(pageId: string, userId: string) {
  const rowId = rowIdFromDatabaseRowPageId(pageId);
  if (!rowId) return;

  const row = await prisma.databaseRow.findUnique({
    where: { id: rowId },
    include: {
      database: {
        include: {
          page: {
            include: {
              permissions: {
                where: { userId },
              },
            },
          },
        },
      },
    },
  });

  if (!row || row.database.page.deletedAt) return;

  await prisma.page.upsert({
    where: { id: pageId },
    update: {
      title: row.title || "Untitled",
      parentPageId: row.database.page.id,
      accessLevel: row.database.page.accessLevel,
      deletedAt: null,
    },
    create: {
      id: pageId,
      workspaceId: row.database.page.workspaceId,
      createdById: row.database.page.createdById,
      title: row.title || "Untitled",
      type: "document",
      accessLevel: row.database.page.accessLevel,
      parentPageId: row.database.page.id,
    },
  });

  if (row.database.page.accessLevel !== "private") {
    await prisma.pagePermission.deleteMany({
      where: { pageId },
    });
    return;
  }

  const parentPermissions = await prisma.pagePermission.findMany({
    where: { pageId: row.database.page.id },
    select: { userId: true, role: true },
  });

  const desired = new Map<string, "editor" | "commenter" | "viewer">();
  desired.set(row.database.page.createdById, "editor");
  for (const permission of parentPermissions) {
    desired.set(permission.userId, permission.role);
  }

  const desiredUserIds = Array.from(desired.keys());
  await prisma.pagePermission.deleteMany({
    where: {
      pageId,
      userId: { notIn: desiredUserIds },
    },
  });

  await Promise.all(
    Array.from(desired.entries()).map(([targetUserId, role]) =>
      prisma.pagePermission.upsert({
        where: {
          pageId_userId: {
            pageId,
            userId: targetUserId,
          },
        },
        update: { role },
        create: {
          id: makeId("perm"),
          pageId,
          userId: targetUserId,
          role,
        },
      })
    )
  );
}

export default async function DocumentPage({ params }: { params: { pageId: string } }) {
  const userId = getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  await ensureDatabaseRowPage(params.pageId, userId);

  const page = await prisma.page.findUnique({
    where: { id: params.pageId },
    include: {
      permissions: {
        where: { userId },
      },
    },
  });

  if (!page) {
    return <div className="p-8 text-sm text-[var(--muted)]">Page not found.</div>;
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

  if (page.type === "database") {
    redirect(`/app/database/${page.id}`);
  }

  const blocks = await prisma.block.findMany({
    where: { pageId: page.id },
    orderBy: { position: "asc" },
    select: {
      id: true,
      type: true,
      contentText: true,
      checked: true,
      imageUrl: true,
      position: true,
      parentBlockId: true,
      propsJson: true,
      richTextJson: true,
    },
  });

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

  const rowId = rowIdFromDatabaseRowPageId(page.id);
  const rowContext = rowId
    ? await prisma.databaseRow.findUnique({
        where: { id: rowId },
        include: {
          cells: true,
          database: {
            include: {
              page: { select: { id: true, workspaceId: true, title: true } },
              properties: { orderBy: { position: "asc" } },
            },
          },
        },
      })
    : null;

  const shouldShowRowProperties = Boolean(
    rowContext &&
      rowContext.database.page.workspaceId === page.workspaceId &&
      rowContext.database.page.id === page.parentPageId
  );

  const rowPropertyItems = shouldShowRowProperties && rowContext
    ? rowContext.database.properties
        .filter((property) => property.type !== "title")
        .map((property) => {
          const raw = rowContext.cells.find((cell) => cell.propertyId === property.id)?.valueJson ?? "";
          return {
            id: property.id,
            name: property.name,
            type: property.type,
            configJson: property.configJson,
            value: raw,
          };
        })
    : [];

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
      {shouldShowRowProperties ? (
        <RowPropertiesPanel
          databasePageId={rowContext!.database.page.id}
          rowId={rowContext!.id}
          title={rowContext!.database.page.title}
          items={rowPropertyItems}
          editable={editable}
        />
      ) : null}
      <PageEditor key={page.id} pageId={page.id} initialBlocks={blocks} editable={editable} />
    </div>
  );
}
