import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";


const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const runId = "MM2-REAL-02";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const outputRoot = "E:/Minta/Codex/2026-08-07/files-mentioned-by-the-user-min/outputs";
const runIndex = JSON.parse(readFileSync("E:/Minta/runs/index.json", "utf8"));
const protectedRunRoot = runIndex[slug].run_dir;

function fileSnapshot(root) {
  const hashes = {};
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile()) hashes[relative(root, path).replaceAll("\\", "/")] = createHash("sha256").update(readFileSync(path)).digest("hex");
    }
  };
  visit(root);
  return hashes;
}

async function login(page, target) {
  await page.goto(`${base}/#${target}`, { waitUntil: "domcontentloaded" });
  const password = page.locator('input[type="password"]');
  await Promise.race([
    password.waitFor({ timeout: 30_000 }).catch(() => undefined),
    page.locator("main h1").first().waitFor({ timeout: 30_000 }).catch(() => undefined),
  ]);
  if (await password.isVisible().catch(() => false)) {
    await page.locator('input[type="text"]').first().fill("uitest");
    await password.fill("uitest123");
    await page.locator('button[type="submit"]').click();
  }
}

async function api(page, path) {
  return page.evaluate(async (url) => {
    const response = await fetch(url, { credentials: "include" });
    return { status: response.status, body: await response.json() };
  }, path);
}

async function overflow(page) {
  return page.locator("main").evaluate((main) => main.scrollWidth > main.clientWidth + 1);
}

async function verifyViewport(browser, viewport, label) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const writeRequests = [];
  const consoleErrors = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/projects/") && request.method() !== "GET") {
      writeRequests.push({ method: request.method(), url: request.url() });
    }
  });
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await login(page, `/projects/${slug}/execution`);
  consoleErrors.length = 0;
  await page.waitForURL(`**/#/projects/${slug}/execution/${runId}`, { timeout: 30_000 });
  await page.getByRole("heading", { name: "执行记录", exact: true }).waitFor();
  const executionText = (await page.locator("main").innerText()).trim();
  const executionApi = await api(page, `/api/projects/${slug}/execution/${runId}`);
  const executionOverflow = await overflow(page);
  if (!executionText || executionOverflow) throw new Error(`${label} execution page blank or overflowing`);
  if (!executionText.includes("C2") || !executionText.includes("MM2-REAL-02-G2-V8")) throw new Error(`${label} authorization binding missing`);
  await page.locator("details").first().evaluate((element) => { element.open = true; });
  await page.screenshot({ path: `${outputRoot}/ui3a-execution-${label}.png` });

  await page.goto(`${base}/#/projects/${slug}/qa`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Scientific QA", exact: true }).waitFor({ timeout: 30_000 });
  await page.getByText("PASSED", { exact: true }).first().waitFor();
  const checksSection = page.locator('section[aria-labelledby="checks-title"]');
  const invalidCheck = checksSection.locator("details").filter({ hasText: "CHK-1" }).first();
  await invalidCheck.locator("summary").click();
  await invalidCheck.getByText("无法定位", { exact: true }).first().waitFor();
  const validCheck = checksSection.locator("details").filter({ hasText: "CHK-3" }).first();
  await validCheck.locator("summary").click();
  await validCheck.getByText("已定位", { exact: true }).first().waitFor();
  const qaText = (await page.locator("main").innerText()).trim();
  const qaApi = await api(page, `/api/projects/${slug}/qa`);
  const qaOverflow = await overflow(page);
  if (!qaText || qaOverflow) throw new Error(`${label} QA page blank or overflowing`);
  await checksSection.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${outputRoot}/ui3a-qa-${label}.png` });

  const sse = await page.evaluate(async (id) => {
    const controller = new AbortController();
    const response = await fetch(`/api/runs/${id}/events`, { credentials: "include", signal: controller.signal });
    const reader = response.body?.getReader();
    const first = reader ? await reader.read() : { value: undefined };
    controller.abort();
    return { status: response.status, first: first.value ? new TextDecoder().decode(first.value) : "" };
  }, runId);

  await context.close();
  return {
    viewport: label,
    execution: {
      routeRedirected: true,
      status: executionApi.body.status,
      bindingVisible: executionText.includes("C2") && executionText.includes("MM2-REAL-02-G2-V8"),
      artifactArrivals: executionApi.body.artifact_arrivals.length,
      logs: executionApi.body.logs.length,
      blank: false,
      overflow: executionOverflow,
    },
    qa: {
      verdict: qaApi.body.verdict,
      findings: qaApi.body.findings.length,
      checks: qaApi.body.checks.length,
      history: qaApi.body.check_history.length,
      evidenceValid: qaApi.body.checks.flatMap((check) => check.evidence).filter((item) => item.valid).length,
      evidenceInvalidFallback: qaApi.body.checks.flatMap((check) => check.evidence).filter((item) => !item.valid && item.fallback_reason).length,
      paperEligible: qaApi.body.paper_eligible,
      blank: false,
      overflow: qaOverflow,
    },
    sse: { status: sse.status, snapshot: sse.first.includes("event: snapshot") },
    writeRequests,
    consoleErrors,
  };
}

async function verifyStates(browser) {
  const context = await browser.newContext({ viewport: { width: 1024, height: 768 } });
  const page = await context.newPage();
  const executionUrl = `${base}/api/projects/${slug}/execution/${runId}`;
  const runtimeUrl = `${base}/api/projects/${slug}/runtime`;
  const qaUrl = `${base}/api/projects/${slug}/qa`;
  const eventsUrl = `${base}/api/runs/${runId}/events`;
  await login(page, `/projects/${slug}/execution/${runId}`);
  await page.getByRole("heading", { name: "执行记录", exact: true }).waitFor();
  const execution = (await api(page, `/api/projects/${slug}/execution/${runId}`)).body;
  const qa = (await api(page, `/api/projects/${slug}/qa`)).body;
  await page.close();

  const loadingPage = await context.newPage();
  await loadingPage.route(executionUrl, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 5_000));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(execution) });
  });
  const loadingNavigation = loadingPage.goto(`${base}/#/projects/${slug}/execution/${runId}`, { waitUntil: "domcontentloaded" });
  await loadingPage.locator('[aria-label="正在读取执行记录"]').waitFor({ timeout: 4_000 });
  await loadingNavigation;
  await loadingPage.close();

  const errorPage = await context.newPage();
  await errorPage.route(executionUrl, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "test unavailable" }) }));
  await errorPage.goto(`${base}/#/projects/${slug}/execution/${runId}`, { waitUntil: "domcontentloaded" });
  await errorPage.getByRole("heading", { name: "执行记录不可用" }).waitFor();
  await errorPage.close();

  const blocked = { ...execution, status: "blocked", raw_runtime_status: "pending_human_review_gate3", is_stale: true, stale_reason: "Recorded test snapshot is stale." };
  const blockedPage = await context.newPage();
  await blockedPage.route(executionUrl, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(blocked) }));
  await blockedPage.goto(`${base}/#/projects/${slug}/execution/${runId}`, { waitUntil: "domcontentloaded" });
  await blockedPage.getByText("Run 已被服务端阻塞", { exact: true }).waitFor();
  await blockedPage.getByText("执行快照可能已过期", { exact: true }).waitFor();
  await blockedPage.close();

  const pollingPage = await context.newPage();
  let pollingReads = 0;
  pollingPage.on("request", (request) => {
    if (request.url() === executionUrl && request.method() === "GET") pollingReads += 1;
  });
  await pollingPage.route(eventsUrl, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "test SSE unavailable" }) }));
  await pollingPage.goto(`${base}/#/projects/${slug}/execution/${runId}`, { waitUntil: "domcontentloaded" });
  await pollingPage.getByText("轮询回退", { exact: true }).waitFor({ timeout: 10_000 });
  await pollingPage.waitForTimeout(2_500);
  if (pollingReads < 2) throw new Error(`Polling fallback did not refresh execution data: ${pollingReads} reads`);
  await pollingPage.close();

  const idleRuntime = {
    project_slug: slug,
    active_run_id: null,
    status: "idle",
    revision: 0,
    updated_at: "",
    current_stage: null,
    next_action: { kind: "none", href: null, disabled_reason: "无活动 Run" },
    experts: [],
    gates: [],
    qa: { verdict: null, artifact_name: null },
    paper: { available: false, artifact_name: null },
    package: { eligible: false, package_id: null },
  };
  const emptyExecutionPage = await context.newPage();
  await emptyExecutionPage.route(runtimeUrl, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(idleRuntime) }));
  await emptyExecutionPage.goto(`${base}/#/projects/${slug}/execution`, { waitUntil: "domcontentloaded" });
  await emptyExecutionPage.getByRole("heading", { name: "尚无活动 Run" }).waitFor();
  await emptyExecutionPage.close();

  const emptyQa = { ...qa, verdict: null, findings: [], checks: [], check_history: [], paper_eligible: false, paper_eligibility_reason: "The server-recorded QA verdict is not PASSED." };
  const emptyQaPage = await context.newPage();
  await emptyQaPage.route(qaUrl, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(emptyQa) }));
  await emptyQaPage.goto(`${base}/#/projects/${slug}/qa`, { waitUntil: "domcontentloaded" });
  await emptyQaPage.getByRole("heading", { name: "尚无 QA verdict" }).waitFor();
  await emptyQaPage.close();
  await context.close();
  return { loading: true, empty: true, error: true, stale: true, blocked: true, pollingFallback: true };
}

mkdirSync(outputRoot, { recursive: true });
const protectedBefore = fileSnapshot(protectedRunRoot);
const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  const desktop = await verifyViewport(browser, { width: 1440, height: 900 }, "desktop");
  const mobile = await verifyViewport(browser, { width: 390, height: 844 }, "mobile");
  const states = await verifyStates(browser);
  const protectedAfter = fileSnapshot(protectedRunRoot);
  const fixtureResponse = await fetch(`${base}/api/runtime`).then((response) => response.json());
  const result = {
    desktop,
    mobile,
    states,
    protectedRun: {
      filesBefore: Object.keys(protectedBefore).length,
      filesAfter: Object.keys(protectedAfter).length,
      hashesIdentical: JSON.stringify(protectedBefore) === JSON.stringify(protectedAfter),
    },
    service: fixtureResponse,
  };
  writeFileSync(`${outputRoot}/UI-3A-acceptance.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
