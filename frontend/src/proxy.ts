import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { applicationRoutes } from "@/utils/applicationRoutes";

const PUBLIC_PATHS: string[] = [
  applicationRoutes.login,
  applicationRoutes.register,
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has("kg_session");

  if (!hasSession && !PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.redirect(new URL(applicationRoutes.login, request.url));
  }

  if (hasSession && pathname === applicationRoutes.login) {
    return NextResponse.redirect(
      new URL(applicationRoutes.documents, request.url)
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
