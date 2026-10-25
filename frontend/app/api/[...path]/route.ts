import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
const base = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const headers = new Headers();
  headers.set("Content-Type", "application/json");
  const token = request.headers.get("x-edit-token");
  if (token) headers.set("x-edit-token", token);
  try {
    const response = await fetch(`${base}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, {
      method: request.method, headers, cache: "no-store",
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
      signal: AbortSignal.timeout(210000),
    });
    return new Response(response.status === 204 ? null : await response.text(), { status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: { code: "BACKEND_UNAVAILABLE", message: "The planning service is unavailable. Check backend startup and migrations." } }, { status: 503 });
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
