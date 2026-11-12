import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  deals,
  contacts,
  companies,
  pipelineStages,
  activities,
} from "@/lib/db/schema";
import { eq } from "drizzle-orm";

// Read-only evaluation API for the WebArena-Pro evaluator.
//
// Exposes backend state as JSON so tasks can be graded deterministically.
// Strictly read-only and gated by a secret token (WP_EVAL_TOKEN) the agent
// under test never sees; disabled (403) when WP_EVAL_TOKEN is unset. This
// bypasses the NextAuth session flow, which verifiers cannot drive. The
// emitted rows inline deal/company/stage names so regex joins stay simple.
export async function GET(req: NextRequest) {
  const token = process.env.WP_EVAL_TOKEN;
  if (!token || req.headers.get("x-eval-token") !== token) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const dealRows = db
    .select({
      id: deals.id,
      title: deals.title,
      value: deals.value,
      status: deals.status,
      expected_close_date: deals.expectedCloseDate,
      stage: pipelineStages.name,
      company: companies.name,
      contact_first: contacts.firstName,
      contact_last: contacts.lastName,
    })
    .from(deals)
    .leftJoin(pipelineStages, eq(deals.stageId, pipelineStages.id))
    .leftJoin(companies, eq(deals.companyId, companies.id))
    .leftJoin(contacts, eq(deals.contactId, contacts.id))
    .all();

  const activityRows = db
    .select({
      id: activities.id,
      type: activities.type,
      subject: activities.subject,
      due_date: activities.dueDate,
      done: activities.isDone,
      deal_title: deals.title,
      deal_status: deals.status,
    })
    .from(activities)
    .leftJoin(deals, eq(activities.dealId, deals.id))
    .all();

  return NextResponse.json({ deals: dealRows, activities: activityRows });
}
