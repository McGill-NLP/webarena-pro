import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { activities } from "@/lib/db/schema";
import { activitySchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, and } from "drizzle-orm";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await req.json();
  const parsed = activitySchema.partial().safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const updated = db
    .update(activities)
    .set({ ...parsed.data, updatedAt: new Date().toISOString() })
    .where(and(eq(activities.id, parseInt(id)), eq(activities.userId, parseInt(session.user.id))))
    .returning()
    .get();

  if (!updated) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(updated);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const deleted = db
    .delete(activities)
    .where(and(eq(activities.id, parseInt(id)), eq(activities.userId, parseInt(session.user.id))))
    .returning()
    .all();

  if (!deleted.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ success: true });
}
