import path from "path";
import { stat, readFile } from "fs/promises";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME_TYPES: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".pdf": "application/pdf",
  ".ico": "image/x-icon",
};

export async function GET(_request: Request, { params }: { params: { path: string[] } }) {
  const segments = params.path;
  if (!segments || segments.length === 0) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const fileName = segments[segments.length - 1];
  if (fileName.includes("..") || segments.some((s) => s === "..")) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const filePath = path.join(process.cwd(), "public", "uploads", ...segments);

  try {
    const info = await stat(filePath);
    if (!info.isFile()) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const ext = path.extname(fileName).toLowerCase();
    const contentType = MIME_TYPES[ext] ?? "application/octet-stream";
    const buffer = await readFile(filePath);

    return new NextResponse(buffer, {
      headers: {
        "Content-Type": contentType,
        "Content-Length": String(buffer.length),
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
}
