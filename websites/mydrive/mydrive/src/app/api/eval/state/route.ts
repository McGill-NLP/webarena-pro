export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Read-only evaluation API for the WebArena-Pro evaluator.
 *
 * Exposes drive state (folders, files, shares) as JSON so file-management
 * tasks can be graded deterministically instead of relying on an LLM judge.
 * Folder/file rows carry their full resolved path ("COMP 222/A1.java") so
 * checks never need id joins; small text files include their content.
 *
 * Strictly read-only. Gated by a secret token (WP_EVAL_TOKEN) that the agent
 * under test never sees, so it cannot read answers. Disabled (403) when
 * WP_EVAL_TOKEN is unset.
 *
 * Usage:  GET /api/eval/state
 *         header  X-Eval-Token: <WP_EVAL_TOKEN>
 */

import { NextResponse } from "next/server";
import { prisma } from "../../../../lib/db";
import { s3 } from "../../../../lib/s3";
import { GetObjectCommand } from "@aws-sdk/client-s3";

const MAX_CONTENT_BYTES = 65536;
const TEXT_EXTENSIONS = /\.(txt|md|csv|json|xml|html|css|js|ts|jsx|tsx|py|java|c|h|cpp|sh|bash|sql|yml|yaml)$/i;

function isTextFile(name: string, mimeType: string): boolean {
  return mimeType.startsWith("text/") || TEXT_EXTENSIONS.test(name);
}

export async function GET(req: Request) {
  const token = process.env.WP_EVAL_TOKEN;
  const provided = req.headers.get("x-eval-token") ?? "";
  if (!token || provided !== token) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const users = await prisma.user.findMany();
  const userLabel = new Map(users.map((u) => [u.id, u.username ?? u.email ?? u.id]));
  const userEmail = new Map(users.map((u) => [u.id, u.email]));

  const folders = await prisma.folder.findMany();
  const folderMap = new Map(folders.map((f) => [f.id, f]));
  const pathCache = new Map<string, string>();
  const folderPath = (folderId: string | null): string => {
    if (!folderId) return "";
    if (pathCache.has(folderId)) return pathCache.get(folderId)!;
    const folder = folderMap.get(folderId);
    if (!folder) return "";
    const parent = folderPath(folder.parentId);
    const full = (parent ? parent + "/" : "") + folder.name;
    pathCache.set(folderId, full);
    return full;
  };

  const files = await prisma.fileObject.findMany();
  const fileRows = [];
  for (const f of files) {
    const row: Record<string, unknown> = {
      path: (folderPath(f.folderId) ? folderPath(f.folderId) + "/" : "") + f.name,
      name: f.name,
      size: f.size,
      mimeType: f.mimeType,
      owner: userLabel.get(f.ownerId) ?? f.ownerId,
      inTrash: f.inTrash,
      id: f.id,
      ownerEmail: userEmail.get(f.ownerId),
    };
    if (isTextFile(f.name, f.mimeType) && f.size <= MAX_CONTENT_BYTES && !f.inTrash) {
      try {
        const response = await s3.send(
          new GetObjectCommand({ Bucket: process.env.S3_BUCKET!, Key: f.s3Key })
        );
        if (response.Body) {
          row.content = new TextDecoder().decode(await response.Body.transformToByteArray());
        }
      } catch {
        // content unavailable — leave the row without it; metadata still counts
      }
    }
    fileRows.push(row);
  }

  const shares = await prisma.share.findMany({
    include: {
      file: { select: { name: true, folderId: true } },
      folder: { select: { id: true } },
      sharedWithUser: { select: { email: true, username: true } },
    },
  });

  return NextResponse.json({
    fileSnapshotVersion: 1,
    users: users.map((u) => ({ email: u.email, username: u.username })),
    folders: folders.map((f) => ({
      path: folderPath(f.id),
      name: f.name,
      owner: userLabel.get(f.ownerId) ?? f.ownerId,
      inTrash: f.inTrash,
    })),
    files: fileRows,
    shares: shares.map((s) => ({
      type: s.fileId ? "file" : s.folderId ? "folder" : "link",
      target: s.fileId
        ? (s.file?.folderId ? folderPath(s.file.folderId) + "/" : "") + (s.file?.name ?? "")
        : s.folderId
          ? folderPath(s.folderId)
          : null,
      sharedWith: s.sharedWithUser?.email ?? s.sharedWithUser?.username ?? null,
      permission: s.permission,
      owner: userLabel.get(s.ownerId) ?? s.ownerId,
    })),
  });
}
