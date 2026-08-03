import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {buildServer} from "../server.mjs";

test("dashboard declares dry-run and gateway icon", async () => {
  const html = await readFile(new URL("../public/index.html", import.meta.url), "utf8");
  assert.match(html, /DRY_RUN/);
  assert.match(html, /\/_gw\/icon/);
});

test("server contains no Bitrix write methods", async () => {
  const source = await readFile(new URL("../server.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\/v1\/(leads|tasks)\/["'`]/);
  assert.match(source, /writesPerformed: 0/);
  assert.match(source, /X-Api-Key/);
  assert.match(source, /x-vibe-authorization/);
  assert.doesNotMatch(source, /vibe_(api|app)_[A-Za-z0-9_-]{10,}/);
});

test("health proves write actions are disabled", async () => {
  const server = buildServer().listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  const address = server.address();
  const response = await fetch(`http://127.0.0.1:${address.port}/health`);
  assert.deepEqual(await response.json(), {status: "ok", mode: "DRY_RUN", writesPerformed: 0});
  await new Promise((resolve) => server.close(resolve));
});

test("lead placement context is sanitized", async () => {
  const server = buildServer().listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  const address = server.address();
  const options = encodeURIComponent(JSON.stringify({ID: "42<script>"}));
  const response = await fetch(`http://127.0.0.1:${address.port}/api/placement?placement=CRM_LEAD_DETAIL_TAB&placement_options=${options}`);
  const body = await response.json();
  assert.equal(body.entityId, "42");
  assert.equal(body.mode, "DRY_RUN");
  await new Promise((resolve) => server.close(resolve));
});
