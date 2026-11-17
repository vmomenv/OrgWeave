import { NextRequest, NextResponse } from "next/server";

import { ACCESS_COOKIE } from "@/lib/server/session";

export async function GET(request: NextRequest) {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json(
      { error: { code: "not_authenticated", message: "请先登录" } },
      { status: 401 },
    );
  }
  return NextResponse.json({ token });
}
