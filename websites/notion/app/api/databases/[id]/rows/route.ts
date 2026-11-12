import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage } from "@/lib/access";
import { makeId } from "@/lib/ids";
import { pageIdForDatabaseRow } from "@/lib/database-row-page";
import type { PageAccessLevel, PagePermissionRole } from "@prisma/client";

async function resolveDatabaseWithPage(id: string, userId: string) {
  return (
    (await prisma.database.findUnique({
      where: { id },
      include: {
        page: {
          include: {
            permissions: { where: { userId } },
          },
        },
      },
    })) ||
    (await prisma.database.findUnique({
      where: { pageId: id },
      include: {
        page: {
          include: {
            permissions: { where: { userId } },
          },
        },
      },
    }))
  );
}

async function syncRowPagePermissions(params: {
  rowPageId: string;
  accessLevel: PageAccessLevel;
  createdById: string;
  parentPermissions: Array<{ userId: string; role: PagePermissionRole }>;
}) {
  if (params.accessLevel !== "private") {
    await prisma.pagePermission.deleteMany({
      where: { pageId: params.rowPageId },
    });
    return;
  }

  const desired = new Map<string, PagePermissionRole>();
  desired.set(params.createdById, "editor");
  for (const permission of params.parentPermissions) {
    desired.set(permission.userId, permission.role);
  }

  const desiredUserIds = Array.from(desired.keys());
  await prisma.pagePermission.deleteMany({
    where: {
      pageId: params.rowPageId,
      userId: { notIn: desiredUserIds },
    },
  });

  await Promise.all(
    Array.from(desired.entries()).map(([userId, role]) =>
      prisma.pagePermission.upsert({
        where: {
          pageId_userId: {
            pageId: params.rowPageId,
            userId,
          },
        },
        update: { role },
        create: {
          id: makeId("perm"),
          pageId: params.rowPageId,
          userId,
          role,
        },
      })
    )
  );
}

export async function GET(_: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const database = await resolveDatabaseWithPage(params.id, auth.session.userId);
  if (!database) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (database.page.deletedAt) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: database.page.workspaceId,
        userId: auth.session.userId,
      },
    },
    select: { role: true },
  });

  const readable = canReadPage({
    accessLevel: database.page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: database.page.createdById === auth.session.userId,
    permissionRole: database.page.permissions[0]?.role,
  });
  if (!readable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const rows = await prisma.databaseRow.findMany({
    where: { databaseId: database.id },
    orderBy: { position: "asc" },
    include: { cells: true },
  });

  const parentPermissions =
    database.page.accessLevel === "private"
      ? await prisma.pagePermission.findMany({
          where: { pageId: database.page.id },
          select: { userId: true, role: true },
        })
      : [];

  await Promise.all(
    rows.map(async (row) => {
      const rowPageId = pageIdForDatabaseRow(row.id);
      await prisma.page.upsert({
        where: { id: rowPageId },
        update: {
          title: row.title || "Untitled",
          parentPageId: database.page.id,
          accessLevel: database.page.accessLevel,
          deletedAt: null,
        },
        create: {
          id: rowPageId,
          workspaceId: database.page.workspaceId,
          createdById: database.page.createdById,
          title: row.title || "Untitled",
          type: "document",
          accessLevel: database.page.accessLevel,
          parentPageId: database.page.id,
        },
      });
      await syncRowPagePermissions({
        rowPageId,
        accessLevel: database.page.accessLevel,
        createdById: database.page.createdById,
        parentPermissions,
      });
    })
  );

  const enriched = rows.map((row) => ({
    ...row,
    pageId: pageIdForDatabaseRow(row.id),
  }));

  return NextResponse.json({ rows: enriched });
}

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const database = await resolveDatabaseWithPage(params.id, auth.session.userId);
  if (!database) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (database.page.deletedAt) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: database.page.workspaceId,
        userId: auth.session.userId,
      },
    },
    select: { role: true },
  });

  const editable = canEditPage({
    accessLevel: database.page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: database.page.createdById === auth.session.userId,
    permissionRole: database.page.permissions[0]?.role,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (database.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const body = await request.json().catch(() => null);
  const title = body?.title?.toString().trim() || "New Row";

  const lastRow = await prisma.databaseRow.findFirst({
    where: { databaseId: database.id },
    orderBy: { position: "desc" },
  });

  const row = await prisma.databaseRow.create({
    data: {
      id: makeId("row"),
      databaseId: database.id,
      title,
      position: (lastRow?.position ?? -1) + 1,
    },
    include: { cells: true },
  });

  const rowPageId = pageIdForDatabaseRow(row.id);

  await prisma.page.upsert({
    where: { id: rowPageId },
    update: {
      title: row.title || "Untitled",
      parentPageId: database.page.id,
      accessLevel: database.page.accessLevel,
      deletedAt: null,
    },
    create: {
      id: rowPageId,
      workspaceId: database.page.workspaceId,
      createdById: auth.session.userId,
      title: row.title || "Untitled",
      type: "document",
      accessLevel: database.page.accessLevel,
      parentPageId: database.page.id,
    },
  });

  const parentPermissions =
    database.page.accessLevel === "private"
      ? await prisma.pagePermission.findMany({
          where: { pageId: database.page.id },
          select: { userId: true, role: true },
        })
      : [];

  await syncRowPagePermissions({
    rowPageId,
    accessLevel: database.page.accessLevel,
    createdById: database.page.createdById,
    parentPermissions,
  });

  return NextResponse.json({
    row: {
      ...row,
      pageId: rowPageId,
    },
  });
}
