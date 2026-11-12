import { NextResponse } from "next/server";
import { SESSION_COOKIE, WORKSPACE_COOKIE } from "@/lib/auth";

function clearAuthCookies(response: NextResponse) {
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  response.cookies.set(WORKSPACE_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

export async function POST() {
  const response = NextResponse.json({ ok: true });
  clearAuthCookies(response);
  return response;
}

export async function GET(request: Request) {
  const loginUrl = new URL("/login", request.url);
  const response = NextResponse.redirect(loginUrl);
  clearAuthCookies(response);
  return response;
}
