import { db } from "@/lib/db";
import { deals, pipelineStages, pipelines, contacts, companies } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq, asc, and, ne } from "drizzle-orm";
import { redirect } from "next/navigation";
import { KanbanBoard } from "@/components/deals/kanban-board";

export default async function DealsPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/login");

  const userId = parseInt(session.user.id);

  const allPipelines = db.select().from(pipelines).where(eq(pipelines.userId, userId)).all();
  const pipeline = allPipelines[0];
  if (!pipeline) return <div>No pipeline found. Go to Settings to create one.</div>;

  const stages = db
    .select()
    .from(pipelineStages)
    .where(eq(pipelineStages.pipelineId, pipeline.id))
    .orderBy(asc(pipelineStages.position))
    .all();

  const allDeals = db
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
    })
    .from(deals)
    .leftJoin(contacts, eq(deals.contactId, contacts.id))
    .leftJoin(companies, eq(deals.companyId, companies.id))
    .leftJoin(pipelineStages, eq(deals.stageId, pipelineStages.id))
    .where(and(eq(deals.userId, userId), ne(deals.status, "lost")))
    .all();

  const allContacts = db
    .select({
      id: contacts.id,
      firstName: contacts.firstName,
      lastName: contacts.lastName,
      companyId: contacts.companyId,
    })
    .from(contacts)
    .where(eq(contacts.userId, userId))
    .all();

  const allCompanies = db
    .select({ id: companies.id, name: companies.name })
    .from(companies)
    .where(eq(companies.userId, userId))
    .all();

  return (
    <KanbanBoard
      initialDeals={allDeals}
      stages={stages}
      pipelineId={pipeline.id}
      contacts={allContacts}
      companies={allCompanies}
    />
  );
}
