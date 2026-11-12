import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { contacts, companies } from "@/lib/db/schema";
import { contactSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, and } from "drizzle-orm";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const contact = db
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
    .where(and(eq(contacts.id, parseInt(id)), eq(contacts.userId, parseInt(session.user.id))))
    .get();

  if (!contact) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(contact);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await req.json();
  const parsed = contactSchema.partial().safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const updated = db
    .update(contacts)
    .set({ ...parsed.data, email: parsed.data.email || null, updatedAt: new Date().toISOString() })
    .where(and(eq(contacts.id, parseInt(id)), eq(contacts.userId, parseInt(session.user.id))))
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
    .delete(contacts)
    .where(and(eq(contacts.id, parseInt(id)), eq(contacts.userId, parseInt(session.user.id))))
    .returning()
    .all();

  if (!deleted.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ success: true });
}
