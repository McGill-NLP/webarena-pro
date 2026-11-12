import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { deals, contacts, companies, pipelineStages } from "@/lib/db/schema";
import { dealSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, desc } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const pipelineId = req.nextUrl.searchParams.get("pipelineId");
  const status = req.nextUrl.searchParams.get("status");
  const userId = parseInt(session.user.id);

  let results = db
    .select({
      id: deals.id,
      title: deals.title,
      value: deals.value,
      status: deals.status,
      position: deals.position,
      expectedCloseDate: deals.expectedCloseDate,
      stageId: deals.stageId,
      stageName: pipelineStages.name,
      contactId: deals.contactId,
      contactFirstName: contacts.firstName,
      contactLastName: contacts.lastName,
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
    .where(eq(deals.userId, userId))
    .orderBy(deals.position)
    .all();

  if (pipelineId) {
    results = results.filter((d) => d.pipelineId === parseInt(pipelineId));
  }
  if (status) {
    results = results.filter((d) => d.status === status);
  }

  return NextResponse.json(results);
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const parsed = dealSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  // Get max position in the target stage
  const existing = db
    .select({ position: deals.position })
    .from(deals)
    .where(eq(deals.stageId, parsed.data.stageId))
    .all();
  const maxPos = existing.length > 0 ? Math.max(...existing.map((d) => d.position)) + 1 : 0;

  const now = new Date().toISOString();
  const deal = db
    .insert(deals)
    .values({
      ...parsed.data,
      position: maxPos,
      userId: parseInt(session.user.id),
      createdAt: now,
      updatedAt: now,
    })
    .returning()
    .get();

  return NextResponse.json(deal, { status: 201 });
}
