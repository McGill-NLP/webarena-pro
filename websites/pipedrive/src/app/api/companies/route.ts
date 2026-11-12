import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { companies } from "@/lib/db/schema";
import { companySchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, desc, like, or } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const search = req.nextUrl.searchParams.get("search") || "";
  const page = parseInt(req.nextUrl.searchParams.get("page") || "1");
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "20");
  const offset = (page - 1) * limit;

  const userId = parseInt(session.user.id);
  const conditions = [eq(companies.userId, userId)];
  if (search) {
    conditions.push(
      or(
        like(companies.name, `%${search}%`),
        like(companies.domain, `%${search}%`)
      )!
    );
  }

  const where = conditions.length > 1
    ? (() => {
        const [userCond, searchCond] = conditions;
        return (t: any, { and }: any) => and(userCond, searchCond);
      })()
    : eq(companies.userId, userId);

  const data = db
    .select()
    .from(companies)
    .where(typeof where === "function" ? undefined : where)
    .orderBy(desc(companies.createdAt))
    .limit(limit)
    .offset(offset)
    .all();

  // Re-do query with proper filtering
  let results;
  if (search) {
    results = db
      .select()
      .from(companies)
      .where(eq(companies.userId, userId))
      .orderBy(desc(companies.createdAt))
      .all()
      .filter(
        (c) =>
          c.name.toLowerCase().includes(search.toLowerCase()) ||
          (c.domain && c.domain.toLowerCase().includes(search.toLowerCase()))
      );
  } else {
    results = db
      .select()
      .from(companies)
      .where(eq(companies.userId, userId))
      .orderBy(desc(companies.createdAt))
      .all();
  }

  const total = results.length;
  const paged = results.slice(offset, offset + limit);

  return NextResponse.json({ data: paged, total, page, limit });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const parsed = companySchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const now = new Date().toISOString();
  const company = db
    .insert(companies)
    .values({
      ...parsed.data,
      userId: parseInt(session.user.id),
      createdAt: now,
      updatedAt: now,
    })
    .returning()
    .get();

  return NextResponse.json(company, { status: 201 });
}
