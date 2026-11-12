import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { activities, contacts, deals, companies } from "@/lib/db/schema";
import { activitySchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, desc } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const type = req.nextUrl.searchParams.get("type");
  const isDone = req.nextUrl.searchParams.get("isDone");
  const dealId = req.nextUrl.searchParams.get("dealId");
  const contactId = req.nextUrl.searchParams.get("contactId");
  const companyId = req.nextUrl.searchParams.get("companyId");
  const userId = parseInt(session.user.id);

  let results = db
    .select({
      id: activities.id,
      type: activities.type,
      subject: activities.subject,
      description: activities.description,
      dueDate: activities.dueDate,
      isDone: activities.isDone,
      dealId: activities.dealId,
      dealTitle: deals.title,
      contactId: activities.contactId,
      contactFirstName: contacts.firstName,
      contactLastName: contacts.lastName,
      companyId: activities.companyId,
      companyName: companies.name,
      createdAt: activities.createdAt,
    })
    .from(activities)
    .leftJoin(deals, eq(activities.dealId, deals.id))
    .leftJoin(contacts, eq(activities.contactId, contacts.id))
    .leftJoin(companies, eq(activities.companyId, companies.id))
    .where(eq(activities.userId, userId))
    .orderBy(desc(activities.dueDate))
    .all();

  if (type) results = results.filter((a) => a.type === type);
  if (isDone !== null && isDone !== undefined && isDone !== "") {
    results = results.filter((a) => a.isDone === (isDone === "true"));
  }
  if (dealId) results = results.filter((a) => a.dealId === parseInt(dealId));
  if (contactId) results = results.filter((a) => a.contactId === parseInt(contactId));
  if (companyId) results = results.filter((a) => a.companyId === parseInt(companyId));

  return NextResponse.json(results);
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const parsed = activitySchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const now = new Date().toISOString();
  const activity = db
    .insert(activities)
    .values({
      ...parsed.data,
      userId: parseInt(session.user.id),
      createdAt: now,
      updatedAt: now,
    })
    .returning()
    .get();

  return NextResponse.json(activity, { status: 201 });
}
