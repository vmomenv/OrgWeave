import { NextRequest, NextResponse } from "next/server";

import { API_BASE, REFRESH_COOKIE, clearSessionCookies } from "@/lib/server/session";

export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (refreshToken) {
    await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    }).catch(() => undefined);
  }
  const response = NextResponse.json({ status: "logged_out" });
  clearSessionCookies(response);
  return response;
}
