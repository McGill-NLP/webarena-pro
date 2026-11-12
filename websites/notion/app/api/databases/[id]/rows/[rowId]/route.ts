import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage } from "@/lib/access";
import { pageIdForDatabaseRow } from "@/lib/database-row-page";
import { makeId } from "@/lib/ids";
import type { PageAccessLevel, PagePermissionRole } from "@prisma/client";

async function getRowContext(rowId: string, userId: string) {
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
  return row;
}

async function syncRowPagePermissions(params: {
  rowPageId: string;
  accessLevel: PageAccessLevel;
  createdById: string;
  parentPageId: string;
}) {
  if (params.accessLevel !== "private") {
    await prisma.pagePermission.deleteMany({
      where: { pageId: params.rowPageId },
    });
    return;
  }

  const parentPermissions = await prisma.pagePermission.findMany({
    where: { pageId: params.parentPageId },
    select: { userId: true, role: true },
  });

  const desired = new Map<string, PagePermissionRole>();
  desired.set(params.createdById, "editor");
  for (const permission of parentPermissions) {
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

export async function PATCH(request: Request, { params }: { params: { id: string; rowId: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const row = await getRowContext(params.rowId, auth.session.userId);
  if (!row || (row.database.id !== params.id && row.database.pageId !== params.id)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (row.database.page.deletedAt) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: row.database.page.workspaceId,
        userId: auth.session.userId,
      },
    },
    select: { role: true },
  });

  const editable = canEditPage({
    accessLevel: row.database.page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: row.database.page.createdById === auth.session.userId,
    permissionRole: row.database.page.permissions[0]?.role,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (row.database.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const body = await request.json().catch(() => null);
  const title = body?.title?.toString().trim();
  const targetIndex = Number.isInteger(body?.targetIndex) ? Number(body.targetIndex) : null;

  if (targetIndex !== null) {
    const rows = await prisma.databaseRow.findMany({
      where: { databaseId: row.databaseId },
      orderBy: { position: "asc" },
      select: { id: true },
    });

    const currentIndex = rows.findIndex((item: { id: string }) => item.id === params.rowId);
    if (currentIndex === -1) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const clamped = Math.max(0, Math.min(rows.length - 1, targetIndex));
    if (clamped !== currentIndex) {
      const reordered = [...rows];
      const [moved] = reordered.splice(currentIndex, 1);
      reordered.splice(clamped, 0, moved);

      await prisma.$transaction(
        reordered.map((item: { id: string }, position) =>
          prisma.databaseRow.update({
            where: { id: item.id },
            data: { position },
          })
        )
      );
    }

    const movedRow = await prisma.databaseRow.findUnique({ where: { id: params.rowId } });
    return NextResponse.json({ row: movedRow });
  }

  const updated = await prisma.databaseRow.update({
    where: { id: params.rowId },
    data: { title: title ?? "" },
  });

  const rowPageId = pageIdForDatabaseRow(params.rowId);

  await prisma.page.upsert({
    where: { id: rowPageId },
    update: {
      title: title ?? "",
      parentPageId: row.database.page.id,
      accessLevel: row.database.page.accessLevel,
      deletedAt: null,
    },
    create: {
      id: rowPageId,
      workspaceId: row.database.page.workspaceId,
      createdById: auth.session.userId,
      title: title ?? "",
      type: "document",
      accessLevel: row.database.page.accessLevel,
      parentPageId: row.database.page.id,
    },
  });

  await syncRowPagePermissions({
    rowPageId,
    accessLevel: row.database.page.accessLevel,
    createdById: row.database.page.createdById,
    parentPageId: row.database.page.id,
  });

  return NextResponse.json({
    row: {
      ...updated,
      pageId: pageIdForDatabaseRow(updated.id),
    },
  });
}

export async function DELETE(_: Request, { params }: { params: { id: string; rowId: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const row = await getRowContext(params.rowId, auth.session.userId);
  if (!row || (row.database.id !== params.id && row.database.pageId !== params.id)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (row.database.page.deletedAt) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: row.database.page.workspaceId,
        userId: auth.session.userId,
      },
    },
    select: { role: true },
  });

  const editable = canEditPage({
    accessLevel: row.database.page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: row.database.page.createdById === auth.session.userId,
    permissionRole: row.database.page.permissions[0]?.role,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (row.database.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  await prisma.databaseRow.delete({ where: { id: params.rowId } });
  await prisma.page.updateMany({
    where: { id: pageIdForDatabaseRow(params.rowId) },
    data: { deletedAt: new Date() },
  });
  return NextResponse.json({ ok: true });
}
