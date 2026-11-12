import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { pipelineStages, deals } from "@/lib/db/schema";
import { stageSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq } from "drizzle-orm";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await req.json();
  const parsed = stageSchema.partial().safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const updated = db
    .update(pipelineStages)
    .set(parsed.data)
    .where(eq(pipelineStages.id, parseInt(id)))
    .returning()
    .get();

  if (!updated) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(updated);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  // Check for deals in this stage
  const dealsInStage = db
    .select()
    .from(deals)
    .where(eq(deals.stageId, parseInt(id)))
    .all();

  if (dealsInStage.length > 0) {
    return NextResponse.json(
      { error: "Cannot delete stage with existing deals. Move or delete deals first." },
      { status: 400 }
    );
  }

  const deleted = db
    .delete(pipelineStages)
    .where(eq(pipelineStages.id, parseInt(id)))
    .returning()
    .all();

  if (!deleted.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ success: true });
}
