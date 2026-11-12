import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { prisma } from "./prisma";

export const SESSION_COOKIE = "webarena_session";
export const WORKSPACE_COOKIE = "webarena_workspace";

export function getSessionUserId() {
  return cookies().get(SESSION_COOKIE)?.value ?? null;
}

export function getSessionWorkspaceId() {
  return cookies().get(WORKSPACE_COOKIE)?.value ?? null;
}

export function isAuthed() {
  return Boolean(getSessionUserId());
}

export async function hasValidSession() {
  const userId = getSessionUserId();
  if (!userId) return false;

  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { id: true },
    });
    return Boolean(user);
  } catch {
    return false;
  }
}

export async function requireAuth() {
  if (!isAuthed()) {
    redirect("/login");
  }
}
