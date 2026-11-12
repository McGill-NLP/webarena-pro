import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage } from "@/lib/access";
import { makeId } from "@/lib/ids";

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const body = await request.json().catch(() => null);
  const rowId = body?.rowId?.toString();
  const propertyId = body?.propertyId?.toString();
  const value = body?.value ?? "";

  if (!rowId || !propertyId) {
    return NextResponse.json({ error: "Missing rowId or propertyId" }, { status: 400 });
  }

  const row = await prisma.databaseRow.findUnique({
    where: { id: rowId },
    include: {
      database: {
        include: {
          page: {
            include: {
              permissions: {
                where: { userId: auth.session.userId },
              },
            },
          },
        },
      },
    },
  });

  if (!row || (row.database.id !== params.id && row.database.pageId !== params.id)) {
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

  const cell = await prisma.databaseCellValue.upsert({
    where: { rowId_propertyId: { rowId, propertyId } },
    update: { valueJson: value },
    create: {
      id: makeId("cell"),
      rowId,
      propertyId,
      valueJson: value,
    },
  });

  return NextResponse.json({ cell });
}
