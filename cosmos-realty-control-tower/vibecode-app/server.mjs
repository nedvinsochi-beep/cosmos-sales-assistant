import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 3000);
const baseUrl = process.env.VIBE_API_BASE_URL || "https://vibecode.bitrix24.tech";
const appKey = process.env.VIBE_APP_KEY;
const personalKey = process.env.VIBE_API_KEY;
const rulesPath = process.env.CONTROL_TOWER_RULES_PATH || resolve(root, "..", "config", "rules.example.json");

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

async function configuredRules() {
  const payload = JSON.parse(await readFile(rulesPath, "utf8"));
  return payload.rules.map((rule) => ({
    id: rule.rule_id,
    name: rule.name,
    description: rule.description,
    mode: rule.mode === "ACTIVE" ? "DRY_RUN" : rule.mode,
    schedule: rule.schedule,
    owner: rule.owner,
    actions: rule.actions.map((action) => action.type),
  }));
}

async function summary(request) {
  const [leadsResponse, tasksResponse, rules] = await Promise.all([
    vibe(request, "/v1/leads/aggregate", {groupBy: ["stageId", "assignedById"]}),
    vibe(request, "/v1/tasks/aggregate", {groupBy: ["status", "responsibleId"]}),
    configuredRules(),
  ]);
  const leads = leadsResponse.data;
  const tasks = tasksResponse.data;
  const leadGroups = leads.groups || [];
  const taskGroups = tasks.groups || [];
  const distribution = leadGroups.filter((item) => item.stageId === "NEW")
    .reduce((total, item) => total + Number(item.count || 0), 0);
  const activeTasks = taskGroups.filter((item) => ["2", "3", "4"].includes(String(item.status)))
    .reduce((total, item) => total + Number(item.count || 0), 0);
  return {
    generatedAt: new Date().toISOString(),
    mode: "DRY_RUN",
    authMode: leadsResponse.authMode,
    currentUser: requestIdentity(request).userId,
    writesPerformed: 0,
    metrics: {leads: Number(leads.count || 0), distributionStage: distribution, tasks: Number(tasks.count || 0), activeTasks},
    rules: rules.map((rule) => ({...rule, status: "DRY_RUN", candidates: rule.id === "MISSED_LEAD_ACCEPTANCE" ? distribution : null})),
    limitations: [
      "Расчёты правил остаются в существующем Cosmos Control Tower",
      "Клиентские ФИО, телефоны, email и комментарии интерфейс не сохраняет",
      "Write-операции, уведомления и изменения CRM заблокированы",
    ],
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
      if (url.pathname === "/health") return json(response, 200, {status: "ok", mode: "DRY_RUN", writesPerformed: 0});
      if (url.pathname === "/api/summary") return json(response, 200, await summary(request));
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
