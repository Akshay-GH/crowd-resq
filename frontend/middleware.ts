import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { jwtVerify } from "jose";

const CONTROL_DASHBOARD = "/dashboard/control";
const PROTECTED_PATHS = [CONTROL_DASHBOARD];
const AUTH_PAGES = ["/signin", "/signup"];
const COOKIE_NAME = "auth-token";

const JWT_SECRET_KEY = new TextEncoder().encode(
  process.env.JWT_SECRET || "fallback-secret-change-me"
);

async function isValidToken(token: string): Promise<boolean> {
  try {
    await jwtVerify(token, JWT_SECRET_KEY);
    return true;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(COOKIE_NAME)?.value;
  const isProtectedPath = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  if (pathname.startsWith("/dashboard") && !pathname.startsWith(CONTROL_DASHBOARD)) {
    return NextResponse.redirect(new URL(CONTROL_DASHBOARD, request.url));
  }

  const validToken = token ? await isValidToken(token) : false;

  if (isProtectedPath && !validToken) {
    const response = NextResponse.redirect(new URL("/signin", request.url));
    response.cookies.delete(COOKIE_NAME);
    return response;
  }

  if (isAuthPage && validToken) {
    return NextResponse.redirect(new URL(CONTROL_DASHBOARD, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/signin", "/signup"],
};

