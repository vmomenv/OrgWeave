import { NextRequest } from "next/server";

import { apiFetch, upstreamToNext, withRefreshedCookies } from "@/lib/server/session";

const ALLOWED_SEGMENT = /^[A-Za-z0-9._~-]+$/;

async function proxy(request: NextRequest, segments: string[]) {
  if (!segments.length || segments.some((segment) => !ALLOWED_SEGMENT.test(segment))) {
    return new Response(
      JSON.stringify({ error: { code: "invalid_path", message: "非法路径" } }),
      { status: 400, headers: { "content-type": "application/json" } },
    );
  }
  const url = new URL(request.url);
  const target = `/api/v1/${segments.join("/")}${url.search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const tenant = request.headers.get("x-tenant-id");
  if (tenant) headers.set("x-tenant-id", tenant);

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.text();
  const { response, newTokens } = await apiFetch(request, target, {
    method,
    headers,
    body,
  });
  const next = upstreamToNext(response);
  return withRefreshedCookies(next, newTokens);
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
export async function POST(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
export async function PUT(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
export async function PATCH(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
export async function DELETE(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
