import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { deals, activities, pipelineStages, pipelines } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq, desc, asc } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const userId = parseInt(session.user.id);
  const period = req.nextUrl.searchParams.get("period") || "all";
  const stageIdParam = req.nextUrl.searchParams.get("stageId");

  // Compute period start date
  let periodStart: string | null = null;
  const now = new Date();
  if (period === "30d") { const d = new Date(now); d.setDate(d.getDate() - 30); periodStart = d.toISOString(); }
  else if (period === "90d") { const d = new Date(now); d.setDate(d.getDate() - 90); periodStart = d.toISOString(); }
  else if (period === "6m") { const d = new Date(now); d.setMonth(d.getMonth() - 6); periodStart = d.toISOString(); }
  else if (period === "1y") { const d = new Date(now); d.setFullYear(d.getFullYear() - 1); periodStart = d.toISOString(); }

  let allDeals = db.select().from(deals).where(eq(deals.userId, userId)).all();
  const allStages = db
    .select()
    .from(pipelineStages)
    .orderBy(asc(pipelineStages.position))
    .all();
  let allActivities = db
    .select()
    .from(activities)
    .where(eq(activities.userId, userId))
    .orderBy(desc(activities.createdAt))
    .all();

  // Apply period filter (based on creation date)
  if (periodStart) {
    allDeals = allDeals.filter((d) => d.createdAt >= periodStart!);
    allActivities = allActivities.filter((a) => a.createdAt >= periodStart!);
  }

  // Apply stage filter to open deals only
  const openDeals = allDeals.filter((d) => d.status === "open");
  const filteredOpenDeals = stageIdParam
    ? openDeals.filter((d) => d.stageId === parseInt(stageIdParam))
    : openDeals;

  const wonDeals = allDeals.filter((d) => d.status === "won");
  const lostDeals = allDeals.filter((d) => d.status === "lost");

  // Summary cards
  const totalOpenValue = filteredOpenDeals.reduce((sum, d) => sum + d.value, 0);
  const totalWonValue = wonDeals.reduce((sum, d) => sum + d.value, 0);
  const winRate =
    wonDeals.length + lostDeals.length > 0
      ? Math.round((wonDeals.length / (wonDeals.length + lostDeals.length)) * 100)
      : 0;

  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);
  const weekStr = weekAgo.toISOString().split("T")[0];
  const activitiesThisWeek = allActivities.filter(
    (a) => a.dueDate && a.dueDate >= weekStr
  ).length;

  // Deals by stage (uses filtered open deals if stage selected, else all open)
  const stageMap = new Map(allStages.map((s) => [s.id, s]));
  const dealsByStage = allStages.map((stage) => {
    const stageDeals = (stageIdParam
      ? filteredOpenDeals
      : openDeals
    ).filter((d) => d.stageId === stage.id);
    return {
      stage: stage.name,
      stageId: stage.id,
      count: stageDeals.length,
      value: stageDeals.reduce((sum, d) => sum + d.value, 0),
    };
  });

  // Revenue forecast (next 6 months, always uses all open deals regardless of period)
  const allOpenDeals = db
    .select()
    .from(deals)
    .where(eq(deals.userId, userId))
    .all()
    .filter((d) => d.status === "open" && (!stageIdParam || d.stageId === parseInt(stageIdParam)));

  const forecast: { month: string; weighted: number; total: number }[] = [];
  for (let i = 0; i < 6; i++) {
    const date = new Date();
    date.setMonth(date.getMonth() + i);
    const monthStr = date.toISOString().slice(0, 7);
    const monthLabel = date.toLocaleDateString("en-US", { month: "short", year: "numeric" });

    const monthDeals = allOpenDeals.filter(
      (d) => d.expectedCloseDate && d.expectedCloseDate.slice(0, 7) === monthStr
    );

    const total = monthDeals.reduce((sum, d) => sum + d.value, 0);
    const weighted = monthDeals.reduce((sum, d) => {
      const stage = stageMap.get(d.stageId);
      const prob = stage ? stage.probability / 100 : 0;
      return sum + d.value * prob;
    }, 0);

    forecast.push({ month: monthLabel, weighted: Math.round(weighted), total: Math.round(total) });
  }

  // Won/Lost breakdown
  const wonLost = [
    { name: "Won", value: wonDeals.length },
    { name: "Lost", value: lostDeals.length },
  ];

  // Recent activities
  const recentActivities = allActivities.slice(0, 10).map((a) => ({
    id: a.id,
    type: a.type,
    subject: a.subject,
    dueDate: a.dueDate,
    isDone: a.isDone,
    createdAt: a.createdAt,
  }));

  // Stages for filter dropdown
  const stagesForFilter = allStages.map((s) => ({ id: s.id, name: s.name }));

  return NextResponse.json({
    summary: {
      openDeals: filteredOpenDeals.length,
      totalOpenValue,
      totalWonValue,
      winRate,
      activitiesThisWeek,
    },
    dealsByStage,
    forecast,
    wonLost,
    recentActivities,
    stages: stagesForFilter,
  });
}
