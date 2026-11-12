import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { pipelines, pipelineStages } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq } from "drizzle-orm";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const userId = parseInt(session.user.id);
  const results = db
    .select()
    .from(pipelines)
    .where(eq(pipelines.userId, userId))
    .all();

  return NextResponse.json(results);
}
