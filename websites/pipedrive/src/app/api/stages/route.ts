import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { pipelineStages } from "@/lib/db/schema";
import { stageSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, asc } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const pipelineId = req.nextUrl.searchParams.get("pipelineId");
  let results = db
    .select()
    .from(pipelineStages)
    .orderBy(asc(pipelineStages.position))
    .all();

  if (pipelineId) {
    results = results.filter((s) => s.pipelineId === parseInt(pipelineId));
  }

  return NextResponse.json(results);
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const parsed = stageSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const now = new Date().toISOString();
  const stage = db
    .insert(pipelineStages)
    .values({ ...parsed.data, createdAt: now })
    .returning()
    .get();

  return NextResponse.json(stage, { status: 201 });
}
