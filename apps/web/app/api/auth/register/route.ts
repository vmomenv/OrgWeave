import { NextRequest, NextResponse } from "next/server";

import { API_BASE, isSameOrigin, setSessionCookies } from "@/lib/server/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: { code: "csrf", message: "非法来源" } }, { status: 403 });
  }
  const body = await request.text();
  const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    cache: "no-store",
  });
  if (!response.ok) {
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  }
  const data = await response.json();
  const next = NextResponse.json({ user: data.user, expires_in: data.expires_in }, { status: 201 });
  setSessionCookies(next, data);
  return next;
}
