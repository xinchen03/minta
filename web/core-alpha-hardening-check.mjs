import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const base = "http://localhost:8772";
const protectedRunRoot = "E:/Minta/Codex/2026-08-05/70-70-mm-4a-status-note/outputs/mm2-real-acceptance/run-MM2-REAL-02";
const outputRoot = "E:/Minta/Codex/2026-08-08/core-alpha-hardening/outputs";
const webSourceRoot = "C:/Users/Lenovo/Desktop/Minta-next/web/src";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const candidateSlugs = [
  "cumcm-2025-c-planning-pilot",
  "streaming-neuro-symbolic-aqa-for-sports",
  "mm1-canonical-planning-smoke",
];

mkdirSync(outputRoot, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function snapshot(root) {
  const hashes = {};
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile()) hashes[relative(root, path).replace(/\\/g, "/")] = createHash("sha256").update(readFileSync(path)).digest("hex");
    }
  };
  visit(root);
  return hashes;
}

function scanSourceForFixtureData(root) {
  const matches = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile() && /\.(ts|tsx|js|jsx)$/.test(entry.name)) {
        const text = readFileSync(path, "utf8");
        if (/ui4b-browser-fixture|ERP-UI4B-BROWSER|HASH_MISMATCH:results/.test(text)) matches.push(path);
      }
    }
  };
  visit(root);
  return matches;
}

function attachSignals(page) {
  const signals = { authenticated: false, pre_auth_console: [], post_auth_console: [], network: [], unsafe_requests: [] };
  page.on("console", (message) => {
    if (message.type() === "error") (signals.authenticated ? signals.post_auth_console : signals.pre_auth_console).push(message.text());
  });
  page.on("response", (response) => {
    if (signals.authenticated && response.status() >= 400) signals.network.push({ status: response.status(), url: response.url() });
  });
  page.on("request", (request) => {
    if (signals.authenticated && ["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) signals.unsafe_requests.push({ method: request.method(), url: request.url() });
  });
  return signals;
}

async function login(page, signals) {
  await page.goto(`${base}/#/projects`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  const password = page.locator('input[type="password"]');
  if (await password.isVisible().catch(() => false)) {
    await page.locator('input[type="text"]').first().fill("uitest");
    await password.fill("uitest123");
    await page.locator('button[type="submit"]').click();
  }
  await page.waitForURL(`${base}/#/projects`, { timeout: 30_000 });
  await page.locator("main").waitFor({ timeout: 30_000 });
  signals.authenticated = true;
}

async function pageHealth(page) {
  return page.evaluate(() => ({
    blank: !document.body.innerText.trim(),
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

async function inspectCandidate(browser, slug, viewport, label) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const signals = attachSignals(page);
  await login(page, signals);
  const runtime = await page.evaluate(async (projectSlug) => {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectSlug)}/runtime`, { credentials: "include", headers: { Accept: "application/json" } });
    return { status: response.status, body: await response.json() };
  }, slug);
  const artifacts = await page.evaluate(async (projectSlug) => {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectSlug)}/artifacts`, { credentials: "include", headers: { Accept: "application/json" } });
    return { status: response.status, body: await response.json() };
  }, slug);
  assert(runtime.status === 200, `${slug}: runtime endpoint failed`);
  assert(runtime.body.status === "idle", `${slug}: non-runtime project was not projected as idle`);
  assert(runtime.body.active_run_id === null, `${slug}: planning-only project has an active run`);
  assert(artifacts.status === 200 && artifacts.body.artifacts.length > 0, `${slug}: real artifacts are not visible`);

  const routes = ["overview", "research"];
  if (label === "desktop") routes.push("paper", "package");
  const routeResults = [];
  for (const route of routes) {
    await page.goto(`${base}/#/projects/${slug}/${route}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.locator("#main, main").first().waitFor({ timeout: 30_000 });
    const health = await pageHealth(page);
    assert(!health.blank, `${slug}/${route}: blank page`);
    assert(health.scrollWidth - health.clientWidth === 0, `${slug}/${route}: horizontal overflow`);
    if (route === "overview") await page.getByText("Next action", { exact: true }).waitFor({ timeout: 30_000 });
    if (route === "research") await page.getByRole("heading", { name: "Research Cockpit" }).waitFor({ timeout: 30_000 });
    if (route === "paper") await page.getByRole("heading", { name: "No active paper Run" }).waitFor({ timeout: 30_000 });
    if (route === "package") await page.getByRole("heading", { name: "No active package Run" }).waitFor({ timeout: 30_000 });
    routeResults.push({ route, health });
    if (slug === candidateSlugs[0] && route === (label === "desktop" ? "overview" : "research")) {
      await page.screenshot({ path: `${outputRoot}/${slug}-${label}-${route}.png`, fullPage: true, timeout: 60_000 }).catch(() => undefined);
    }
  }
  await context.close();
  return { slug, viewport: label, runtime, artifact_count: artifacts.body.artifacts.length, routes: routeResults, signals };
}

async function inspectUnknownRoute(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  const signals = attachSignals(page);
  await login(page, signals);
  await page.goto(`${base}/#/unknown-hardening-route`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.locator('[aria-labelledby="not-found-title"]').waitFor({ timeout: 30_000 });
  const health = await pageHealth(page);
  assert(!health.blank && health.scrollWidth - health.clientWidth === 0, "unknown route health failed");
  await context.close();
  return { health, signals };
}

const before = snapshot(protectedRunRoot);
const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  const desktop = [];
  const mobile = [];
  for (const slug of candidateSlugs) desktop.push(await inspectCandidate(browser, slug, { width: 1440, height: 950 }, "desktop"));
  for (const slug of candidateSlugs) mobile.push(await inspectCandidate(browser, slug, { width: 390, height: 844 }, "mobile-390"));
  const unknown = await inspectUnknownRoute(browser);
  const after = snapshot(protectedRunRoot);
  const productionFixtureHits = scanSourceForFixtureData(webSourceRoot);
  const expectedUnavailable404s = [...desktop, ...mobile].flatMap((item) => item.signals.network).filter((item) => item.status === 404 && /\/api\/projects\/(cumcm-2025-c-planning-pilot|streaming-neuro-symbolic-aqa-for-sports|mm1-canonical-planning-smoke)\/(research\/experts|paper|package)/.test(item.url));
  const unexpectedNetwork = [...desktop, ...mobile].flatMap((item) => item.signals.network).filter((item) => !expectedUnavailable404s.includes(item));
  const result = {
    slice: "CORE-ALPHA-CROSS-PROJECT-HARDENING",
    status: "IMPLEMENTATION_VERIFIED",
    candidates: {
      desktop: desktop.map((item) => ({ slug: item.slug, runtime_status: item.runtime.body.status, active_run_id: item.runtime.body.active_run_id, artifact_count: item.artifact_count, routes: item.routes.map((route) => route.route) })),
      mobile: mobile.map((item) => ({ slug: item.slug, runtime_status: item.runtime.body.status, active_run_id: item.runtime.body.active_run_id, artifact_count: item.artifact_count, routes: item.routes.map((route) => route.route) })),
    },
    honest_state: {
      all_candidates_idle: [...desktop, ...mobile].every((item) => item.runtime.body.status === "idle"),
      all_candidates_have_artifacts: [...desktop, ...mobile].every((item) => item.artifact_count > 0),
      no_candidate_claimed_completed_run: [...desktop, ...mobile].every((item) => item.runtime.body.active_run_id === null),
    },
    unknown_route_404: true,
    expected_unavailable_api_404_count: expectedUnavailable404s.length,
    production_fixture_hits: productionFixtureHits,
    browser: {
      post_auth_console_errors: [...desktop, ...mobile].flatMap((item) => item.signals.post_auth_console).concat(unknown.signals.post_auth_console),
      unexpected_network_errors: unexpectedNetwork,
      horizontal_overflow: [...desktop, ...mobile].flatMap((item) => item.routes).map((route) => route.health.scrollWidth - route.health.clientWidth),
      blank_pages: [...desktop, ...mobile].flatMap((item) => item.routes).map((route) => route.health.blank).filter(Boolean).length,
      unsafe_requests: [...desktop, ...mobile].flatMap((item) => item.signals.unsafe_requests).concat(unknown.signals.unsafe_requests),
    },
    protected_run: {
      run_id: "MM2-REAL-02",
      files_before: Object.keys(before).length,
      files_after: Object.keys(after).length,
      hashes_identical: JSON.stringify(before) === JSON.stringify(after),
    },
    external_gap: "No second project currently has a completed five-expert Runtime/Gate/QA/Paper chain; candidates are planning-only or idle and must not be promoted by this check.",
  };
  assert(result.honest_state.all_candidates_idle, "a planning-only candidate was not idle");
  assert(result.honest_state.all_candidates_have_artifacts, "a candidate lost its real artifact projection");
  assert(result.honest_state.no_candidate_claimed_completed_run, "a candidate claimed an active run without evidence");
  assert(result.browser.post_auth_console_errors.length === 0, `post-auth console errors observed: ${JSON.stringify(result.browser.post_auth_console_errors)}`);
  assert(result.browser.unexpected_network_errors.length === 0, `unexpected post-auth network errors observed: ${JSON.stringify(result.browser.unexpected_network_errors)}`);
  assert(result.browser.horizontal_overflow.every((value) => value === 0), "horizontal overflow observed");
  assert(result.browser.blank_pages === 0, "blank page observed");
  assert(result.browser.unsafe_requests.length === 0, "hardening check issued unsafe requests");
  assert(result.production_fixture_hits.length === 0, "production source contains fixture data");
  assert(result.protected_run.hashes_identical, "MM2-REAL-02 changed during hardening");
  writeFileSync(`${outputRoot}/core-alpha-hardening.json`, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
