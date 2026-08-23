import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const base = "http://localhost:8772";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const outputRoot = "E:/Minta/Codex/2026-08-07/files-mentioned-by-the-user-min/outputs";
const protectedSlug = "mm2-real-acceptance-teaching-methods";
const protectedRunId = "MM2-REAL-02";

function snapshot(root) {
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
  await page.getByRole("heading", { name: "执行记录", exact: true }).waitFor({ timeout: 30_000 });
}

async function api(page, path) {
  return page.evaluate(async (url) => {
    const response = await fetch(url, { credentials: "include" });
    return { status: response.status, body: await response.json() };
  }, path);
}

async function controlFlow(page, slug, runId, action, buttonName, confirmName) {
  await page.goto(`${base}/#/projects/${slug}/execution/${runId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "执行记录", exact: true }).waitFor();
  await page.getByRole("button", { name: buttonName, exact: true }).click();
  await page.getByRole("dialog").waitFor();
  const effects = await page.getByRole("dialog").innerText();
  await page.getByRole("button", { name: confirmName, exact: true }).click();
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await page.waitForTimeout(500);
  const detail = await api(page, `/api/projects/${slug}/execution/${runId}`);
  return { action, confirmationVisible: effects.includes("Server Effects Diff"), status: detail.body.status, rawStatus: detail.body.raw_runtime_status };
}

mkdirSync(outputRoot, { recursive: true });
const runIndex = JSON.parse(readFileSync("E:/Minta/runs/index.json", "utf8"));
const protectedRoot = runIndex[protectedSlug].run_dir;
const protectedBefore = snapshot(protectedRoot);
const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const writeRequests = [];
const consoleErrors = [];
page.on("request", (request) => {
  if (request.url().includes("/api/projects/") && request.method() !== "GET") writeRequests.push({ method: request.method(), url: request.url() });
});
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });

try {
  await login(page, "/projects/ui3b-execution-blocked/execution/UI3B-BLOCKED-01");
  consoleErrors.length = 0;
  const blocked = await controlFlow(page, "ui3b-execution-blocked", "UI3B-BLOCKED-01", "resume", "恢复执行", "确认恢复");
  const failed = await controlFlow(page, "ui3b-execution-failed", "UI3B-FAILED-01", "resume", "恢复执行", "确认恢复");
  const running = await controlFlow(page, "ui3b-execution-running", "UI3B-RUNNING-01", "cancel", "取消执行", "确认取消");

  await page.goto(`${base}/#/projects/ui3b-execution-blocked/execution/UI3B-BLOCKED-01`, { waitUntil: "domcontentloaded" });
  const blockedText = await page.locator("main").innerText();
  const desktopOverflow = await page.locator("main").evaluate((main) => main.scrollWidth > main.clientWidth + 1);
  await page.screenshot({ path: `${outputRoot}/ui3b-execution-control-desktop.png`, fullPage: true });

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mobilePage = await mobileContext.newPage();
  await login(mobilePage, "/projects/ui3b-execution-blocked/execution/UI3B-BLOCKED-01");
  const mobileText = await mobilePage.locator("main").innerText();
  const mobileOverflow = await mobilePage.locator("main").evaluate((main) => main.scrollWidth > main.clientWidth + 1);
  await mobilePage.screenshot({ path: `${outputRoot}/ui3b-execution-control-mobile.png`, fullPage: true });
  await mobileContext.close();

  const protectedControl = await api(page, `/api/projects/${protectedSlug}/execution/${protectedRunId}/control`);
  const runtime = await api(page, `/api/projects/${protectedSlug}/runtime`);
  const protectedAfter = snapshot(protectedRoot);
  const result = {
    authenticated_browser: true,
    control_flows: { blocked_resume: blocked, failed_resume: failed, running_cancel: running },
    visible_states: { blockedText: blockedText.includes("执行控制"), mobileText: mobileText.includes("执行控制"), desktopOverflow, mobileOverflow },
    protected_run: { control_status: protectedControl.status, controls_enabled: protectedControl.body.controls_enabled, protected: protectedControl.body.protected, files_before: Object.keys(protectedBefore).length, files_after: Object.keys(protectedAfter).length, hashes_identical: JSON.stringify(protectedBefore) === JSON.stringify(protectedAfter) },
    runtime: { status: runtime.status, body: runtime.body.status, run_id: runtime.body.active_run_id, experts: runtime.body.experts.length, gates: runtime.body.gates.length, qa: runtime.body.qa.verdict, paper: runtime.body.paper.available },
    write_requests: writeRequests,
    console_errors: consoleErrors,
  };
  writeFileSync(`${outputRoot}/UI-3B-execution-control-browser.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await browser.close();
}
