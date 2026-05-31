import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const CONTROL_DASHBOARD = "/dashboard/control";
const PROTECTED_PATHS = [CONTROL_DASHBOARD];
const AUTH_PAGES = ["/signin", "/signup"];

function hasReadableToken(token: string) {
  try {
    JSON.parse(Buffer.from(token.split(".")[1], "base64").toString());
    return true;
  } catch {
    return false;
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("auth-token")?.value;
  const isProtectedPath = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  if (pathname.startsWith("/dashboard") && !pathname.startsWith(CONTROL_DASHBOARD)) {
    return NextResponse.redirect(new URL(CONTROL_DASHBOARD, request.url));
  }

  if (isProtectedPath) {
    if (!token || !hasReadableToken(token)) {
      const response = NextResponse.redirect(new URL("/signin", request.url));
      response.cookies.delete("auth-token");
      return response;
    }
  }

  if (isAuthPage && token && hasReadableToken(token)) {
    return NextResponse.redirect(new URL(CONTROL_DASHBOARD, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/signin", "/signup"],
};
