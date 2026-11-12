import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { resetDatabase } from "@/lib/seed";

export async function POST() {
  await resetDatabase(prisma);
  return NextResponse.json({ ok: true });
}
