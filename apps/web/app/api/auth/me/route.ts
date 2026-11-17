import { NextRequest } from "next/server";

import { apiFetch, upstreamToNext, withRefreshedCookies } from "@/lib/server/session";

export async function GET(request: NextRequest) {
  const { response, newTokens } = await apiFetch(request, "/api/v1/auth/me", {
    method: "GET",
  });
  const next = upstreamToNext(response);
  return withRefreshedCookies(next, newTokens);
}
