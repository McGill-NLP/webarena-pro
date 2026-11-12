import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { companies, contacts } from "@/lib/db/schema";
import { companySchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, and } from "drizzle-orm";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const company = db
    .select()
    .from(companies)
    .where(and(eq(companies.id, parseInt(id)), eq(companies.userId, parseInt(session.user.id))))
    .get();

  if (!company) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(company);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await req.json();
  const parsed = companySchema.partial().safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const updated = db
    .update(companies)
    .set({ ...parsed.data, updatedAt: new Date().toISOString() })
    .where(and(eq(companies.id, parseInt(id)), eq(companies.userId, parseInt(session.user.id))))
    .returning()
    .get();

  if (!updated) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(updated);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const companyId = parseInt(id);

  const linkedContacts = db
    .select({ id: contacts.id })
    .from(contacts)
    .where(eq(contacts.companyId, companyId))
    .all();

  if (linkedContacts.length > 0) {
    return NextResponse.json(
      { error: `Cannot delete this company because ${linkedContacts.length} contact${linkedContacts.length > 1 ? "s are" : " is"} still linked to it. Remove or reassign them first.` },
      { status: 409 }
    );
  }

  const deleted = db
    .delete(companies)
    .where(and(eq(companies.id, companyId), eq(companies.userId, parseInt(session.user.id))))
    .returning()
    .all();

  if (!deleted.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ success: true });
}
