import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { deals } from "@/lib/db/schema";
import { dealReorderSchema } from "@/lib/validators";
import { auth } from "@/lib/auth";
import { eq, and } from "drizzle-orm";
import Database from "better-sqlite3";
import path from "path";

export async function PATCH(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const parsed = dealReorderSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const { dealId, newStageId, newPosition } = parsed.data;
  const userId = parseInt(session.user.id);

  // Use raw sqlite for transaction
  const dbPath = path.join(process.cwd(), "data", "crm.db");
  const sqlite = new Database(dbPath);
  sqlite.pragma("foreign_keys = ON");

  const txn = sqlite.transaction(() => {
    const now = new Date().toISOString();

    // Get the deal's current stage
    const deal = sqlite
      .prepare("SELECT stage_id FROM deals WHERE id = ? AND user_id = ?")
      .get(dealId, userId) as { stage_id: number } | undefined;

    if (!deal) throw new Error("Deal not found");

    const oldStageId = deal.stage_id;

    // Update the deal's stage and position
    sqlite
      .prepare("UPDATE deals SET stage_id = ?, position = ?, updated_at = ? WHERE id = ?")
      .run(newStageId, newPosition, now, dealId);

    // Re-index positions in the new stage
    const newStageDeals = sqlite
      .prepare("SELECT id FROM deals WHERE stage_id = ? AND user_id = ? AND id != ? ORDER BY position")
      .all(newStageId, userId, dealId) as { id: number }[];

    // Insert the moved deal at the right position
    const reordered = [...newStageDeals];
    reordered.splice(newPosition, 0, { id: dealId });

    reordered.forEach((d, idx) => {
      sqlite.prepare("UPDATE deals SET position = ? WHERE id = ?").run(idx, d.id);
    });

    // Re-index positions in the old stage (if different)
    if (oldStageId !== newStageId) {
      const oldStageDeals = sqlite
        .prepare("SELECT id FROM deals WHERE stage_id = ? AND user_id = ? ORDER BY position")
        .all(oldStageId, userId) as { id: number }[];

      oldStageDeals.forEach((d, idx) => {
        sqlite.prepare("UPDATE deals SET position = ? WHERE id = ?").run(idx, d.id);
      });
    }
  });

  try {
    txn();
    sqlite.close();
    return NextResponse.json({ success: true });
  } catch (e: any) {
    sqlite.close();
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
