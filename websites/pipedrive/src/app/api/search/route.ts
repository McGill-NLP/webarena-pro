import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { deals, contacts, companies } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq } from "drizzle-orm";

type SearchResult = {
  id: number;
  type: "deal" | "contact" | "company";
  title: string;
  subtitle: string;
};

function normalize(value: unknown) {
  return String(value ?? "").toLowerCase();
}

function matches(query: string, ...values: unknown[]) {
  return values.some((value) => normalize(value).includes(query));
}

function contactName(firstName?: string | null, lastName?: string | null) {
  return [firstName, lastName].filter(Boolean).join(" ");
}

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const q = (req.nextUrl.searchParams.get("q") || "").trim().toLowerCase();
  if (q.length < 2) return NextResponse.json([]);

  const userId = parseInt(session.user.id);

  const allDeals = db
    .select({
      id: deals.id,
      title: deals.title,
      value: deals.value,
      status: deals.status,
      companyName: companies.name,
      contactFirstName: contacts.firstName,
      contactLastName: contacts.lastName,
    })
    .from(deals)
    .leftJoin(companies, eq(deals.companyId, companies.id))
    .leftJoin(contacts, eq(deals.contactId, contacts.id))
    .where(eq(deals.userId, userId))
    .all();
  const allContacts = db
    .select({
      id: contacts.id,
      firstName: contacts.firstName,
      lastName: contacts.lastName,
      email: contacts.email,
      phone: contacts.phone,
      jobTitle: contacts.jobTitle,
      companyName: companies.name,
    })
    .from(contacts)
    .leftJoin(companies, eq(contacts.companyId, companies.id))
    .where(eq(contacts.userId, userId))
    .all();
  const allCompanies = db.select().from(companies).where(eq(companies.userId, userId)).all();

  const results: SearchResult[] = [];

  allDeals
    .filter((d) =>
      matches(
        q,
        d.title,
        d.status,
        d.companyName,
        contactName(d.contactFirstName, d.contactLastName)
      )
    )
    .slice(0, 5)
    .forEach((d) => {
      const dealContactName = contactName(d.contactFirstName, d.contactLastName);
      const subtitle = [
        `$${d.value.toLocaleString()} - ${d.status}`,
        d.companyName,
        dealContactName,
      ]
        .filter(Boolean)
        .join(" | ");

      results.push({
        id: d.id,
        type: "deal",
        title: d.title,
        subtitle,
      });
    });

  allContacts
    .filter(
      (c) =>
        matches(
          q,
          c.firstName,
          c.lastName,
          contactName(c.firstName, c.lastName),
          c.email,
          c.phone,
          c.jobTitle,
          c.companyName
        )
    )
    .slice(0, 5)
    .forEach((c) =>
      results.push({
        id: c.id,
        type: "contact",
        title: `${c.firstName} ${c.lastName}`,
        subtitle: [c.jobTitle, c.companyName, c.email].filter(Boolean).join(" | "),
      })
    );

  allCompanies
    .filter(
      (c) =>
        matches(q, c.name, c.domain, c.industry, c.website, c.phone, c.address)
    )
    .slice(0, 5)
    .forEach((c) =>
      results.push({
        id: c.id,
        type: "company",
        title: c.name,
        subtitle: [c.domain, c.industry].filter(Boolean).join(" | "),
      })
    );

  return NextResponse.json(results.slice(0, 15));
}
