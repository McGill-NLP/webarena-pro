import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { deals, contacts, companies, pipelineStages, activities } from "@/lib/db/schema";
import { dealSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, and, desc } from "drizzle-orm";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const deal = db
    .select({
      id: deals.id,
      title: deals.title,
      value: deals.value,
      status: deals.status,
      position: deals.position,
      expectedCloseDate: deals.expectedCloseDate,
      stageId: deals.stageId,
      stageName: pipelineStages.name,
      stageProbability: pipelineStages.probability,
      contactId: deals.contactId,
      contactFirstName: contacts.firstName,
      contactLastName: contacts.lastName,
      contactEmail: contacts.email,
      companyId: deals.companyId,
      companyName: companies.name,
      pipelineId: deals.pipelineId,
      createdAt: deals.createdAt,
      updatedAt: deals.updatedAt,
    })
    .from(deals)
    .leftJoin(contacts, eq(deals.contactId, contacts.id))
    .leftJoin(companies, eq(deals.companyId, companies.id))
    .leftJoin(pipelineStages, eq(deals.stageId, pipelineStages.id))
    .where(and(eq(deals.id, parseInt(id)), eq(deals.userId, parseInt(session.user.id))))
    .get();

  if (!deal) return NextResponse.json({ error: "Not found" }, { status: 404 });

  // Get activities for this deal
  const dealActivities = db
    .select()
    .from(activities)
    .where(eq(activities.dealId, parseInt(id)))
    .orderBy(desc(activities.createdAt))
    .all();

  return NextResponse.json({ ...deal, activities: dealActivities });
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await req.json();
  const parsed = dealSchema.partial().safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const updated = db
    .update(deals)
    .set({ ...parsed.data, updatedAt: new Date().toISOString() })
    .where(and(eq(deals.id, parseInt(id)), eq(deals.userId, parseInt(session.user.id))))
    .returning()
    .get();

  if (!updated) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(updated);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  // Delete associated activities first
  db.delete(activities).where(eq(activities.dealId, parseInt(id))).run();

  const deleted = db
    .delete(deals)
    .where(and(eq(deals.id, parseInt(id)), eq(deals.userId, parseInt(session.user.id))))
    .returning()
    .all();

  if (!deleted.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ success: true });
}
