import path from "path";
import { mkdir, writeFile } from "fs/promises";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage, getPageAccessContext } from "@/lib/access";
import { makeId } from "@/lib/ids";

export const runtime = "nodejs";

function safeFileName(name: string) {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}

export async function GET(_: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
  });
  if (!context.ok) return context.response;

  const readable = canReadPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!readable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const attachments = await prisma.attachment.findMany({
    where: { pageId: params.id },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json({ attachments });
}

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const context = await getPageAccessContext({
    pageId: params.id,
    userId: auth.session.userId,
    preferredWorkspaceId: auth.session.workspaceId,
  });
  if (!context.ok) return context.response;

  const editable = canEditPage({
    accessLevel: context.page.accessLevel,
    workspaceRole: context.membership.role,
    isPageCreator: context.page.createdById === auth.session.userId,
    permissionRole: context.permissionRole,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (context.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const contentType = request.headers.get("content-type") ?? "";

  let fileName = "";
  let fileUrl = "";
  let mimeType = "application/octet-stream";
  let sizeBytes = 0;

  if (contentType.includes("multipart/form-data")) {
    const formData = await request.formData();
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "file is required" }, { status: 400 });
    }

    const uploadsDir = path.join(process.cwd(), "public", "uploads");
    await mkdir(uploadsDir, { recursive: true });

    const storageName = `${makeId("upload")}_${safeFileName(file.name)}`;
    const absPath = path.join(uploadsDir, storageName);
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(absPath, buffer);

    fileName = file.name;
    fileUrl = `/uploads/${storageName}`;
    mimeType = file.type || mimeType;
    sizeBytes = buffer.length;
  } else {
    const body = await request.json().catch(() => null);
    fileName = body?.fileName?.toString().trim() ?? "attachment";
    fileUrl = body?.fileUrl?.toString().trim() ?? "";
    mimeType = body?.mimeType?.toString().trim() || mimeType;
    sizeBytes = Number(body?.sizeBytes ?? 0);

    if (!fileUrl) {
      return NextResponse.json({ error: "fileUrl is required" }, { status: 400 });
    }
  }

  const attachment = await prisma.attachment.create({
    data: {
      id: makeId("attachment"),
      pageId: params.id,
      uploadedById: auth.session.userId,
      fileName,
      fileUrl,
      mimeType,
      sizeBytes,
    },
  });

  return NextResponse.json({ attachment });
}
