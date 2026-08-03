import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 3000);
const baseUrl = process.env.VIBE_API_BASE_URL || "https://vibecode.bitrix24.tech";
const appKey = process.env.VIBE_APP_KEY;
const personalKey = process.env.VIBE_API_KEY;

function requestIdentity(request) {
  return {
    userId: request.headers["x-vibe-user-id"] || null,
    portalId: request.headers["x-vibe-portal-id"] || null,
    role: request.headers["x-vibe-user-role"] || null,
    session: request.headers["x-vibe-authorization"] || null,
  };
}

function credentials(request) {
  const identity = requestIdentity(request);
  if (appKey && identity.session?.startsWith("Bearer vibe_session_")) {
    return {key: appKey, session: identity.session, authMode: "EMBEDDED_USER"};
  }
  if (personalKey) return {key: personalKey, session: null, authMode: "OWNER_PREVIEW"};
  throw new Error("VibeCode credentials are not configured");
}

async function vibe(request, path, body) {
  const auth = credentials(request);
  const headers = {"X-Api-Key": auth.key, "Content-Type": "application/json"};
  if (auth.session) headers.Authorization = auth.session;
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || `VibeCode HTTP ${response.status}`);
  }
  return {data: payload.data, authMode: auth.authMode};
}

async function crmCheck(request) {
  const leadsResponse = await vibe(request, "/v1/leads/aggregate", {groupBy: ["stageId"]});
  return {
    checkedAt: new Date().toISOString(),
    mode: "DRY_RUN",
    authMode: leadsResponse.authMode,
    currentUser: requestIdentity(request).userId || "OWNER_PREVIEW",
    writesPerformed: 0,
    result: "CRM_READ_OK",
    leadCount: Number(leadsResponse.data.count || 0),
  };
}

function placementContext(url) {
  const placement = url.searchParams.get("placement");
  let options = {};
  try { options = JSON.parse(url.searchParams.get("placement_options") || "{}"); } catch { options = {}; }
  return {placement, entityId: String(options.ID || options.id || "").replace(/[^0-9]/g, "") || null};
}

function json(response, status, body) {
  response.writeHead(status, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"});
  response.end(JSON.stringify(body));
}

export function buildServer() {
  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://localhost");
      if (url.pathname === "/health") return json(response, 200, {status: "ok", version: "0.0.1", mode: "DRY_RUN", writesPerformed: 0});
      if (url.pathname === "/api/context") return json(response, 200, {currentUser: requestIdentity(request).userId, serverTime: new Date().toISOString(), ...placementContext(url)});
      if (url.pathname === "/api/crm-check") return json(response, 200, await crmCheck(request));
      if (url.pathname === "/api/placement") {
        const context = placementContext(url);
        return json(response, 200, {...context, mode: "DRY_RUN", status: context.entityId ? "REVIEW_REQUIRED" : "NO_CARD_CONTEXT", violations: [], nextStep: null});
      }
      if (url.pathname === "/" || url.pathname === "/index.html") {
        const page = await readFile(join(root, "public", "index.html"));
        response.writeHead(200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"});
        return response.end(page);
      }
      return json(response, 404, {error: "Not found"});
    } catch (error) {
      return json(response, 502, {error: "Bitrix24 data is temporarily unavailable", detail: error.message});
    }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  buildServer().listen(port, "0.0.0.0", () => console.log(`Cosmos Control Tower listening on ${port}`));
}
