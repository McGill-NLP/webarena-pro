import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { contacts, companies } from "@/lib/db/schema";
import { contactSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, desc } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const search = req.nextUrl.searchParams.get("search") || "";
  const companyId = req.nextUrl.searchParams.get("companyId");
  const page = parseInt(req.nextUrl.searchParams.get("page") || "1");
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "20");
  const offset = (page - 1) * limit;
  const userId = parseInt(session.user.id);

  let results = db
    .select({
      id: contacts.id,
      firstName: contacts.firstName,
      lastName: contacts.lastName,
      email: contacts.email,
      phone: contacts.phone,
      jobTitle: contacts.jobTitle,
      companyId: contacts.companyId,
      companyName: companies.name,
      createdAt: contacts.createdAt,
      updatedAt: contacts.updatedAt,
    })
    .from(contacts)
    .leftJoin(companies, eq(contacts.companyId, companies.id))
    .where(eq(contacts.userId, userId))
    .orderBy(desc(contacts.createdAt))
    .all();

  if (companyId) {
    results = results.filter((c) => c.companyId === parseInt(companyId));
  }
  if (search) {
    const s = search.toLowerCase();
    results = results.filter(
      (c) =>
        c.firstName.toLowerCase().includes(s) ||
        c.lastName.toLowerCase().includes(s) ||
        (c.email && c.email.toLowerCase().includes(s)) ||
        (c.companyName && c.companyName.toLowerCase().includes(s))
    );
  }

  const total = results.length;
  const paged = results.slice(offset, offset + limit);

  return NextResponse.json({ data: paged, total, page, limit });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const parsed = contactSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const now = new Date().toISOString();
  const contact = db
    .insert(contacts)
    .values({
      ...parsed.data,
      email: parsed.data.email || null,
      userId: parseInt(session.user.id),
      createdAt: now,
      updatedAt: now,
    })
    .returning()
    .get();

  return NextResponse.json(contact, { status: 201 });
}
