import { NextResponse } from "next/server";

export default function middleware() {
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Skip Next internals and static assets unless a query string is present.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
