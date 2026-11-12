import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, WORKSPACE_COOKIE } from "./auth";

export type ApiSession = {
  userId: string;
  workspaceId: string | null;
};

type ApiAuthSuccess = {
  ok: true;
  session: ApiSession;
};

type ApiAuthFailure = {
  ok: false;
  response: NextResponse;
};

export type ApiAuthResult = ApiAuthSuccess | ApiAuthFailure;

export function requireApiAuth(): ApiAuthResult {
  const userId = cookies().get(SESSION_COOKIE)?.value ?? null;
  if (!userId) {
    return {
      ok: false,
      response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    };
  }

  return {
    ok: true,
    session: {
      userId,
      workspaceId: cookies().get(WORKSPACE_COOKIE)?.value ?? null,
    },
  };
}

export function forbidden(message = "Forbidden") {
  return NextResponse.json({ error: message }, { status: 403 });
}
