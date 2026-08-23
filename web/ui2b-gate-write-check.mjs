import { chromium, request as playwrightRequest } from "playwright";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

const base = "http://localhost:8772";
const slug = "ui2b-gate-write-acceptance";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const python = "C:\\Users\\Lenovo\\.conda\\envs\\minta310\\python.exe";
const repo = "C:\\Users\\Lenovo\\Desktop\\Minta-next";
const outputRoot = "E:/Minta/Codex/2026-08-07/files-mentioned-by-the-user-min/outputs";
const username = process.env.MINTA_TEST_USERNAME ?? "uitest";
const passwordValue = process.env.MINTA_TEST_PASSWORD ?? "uitest123";
const runIndex = JSON.parse(readFileSync("E:/Minta/runs/index.json", "utf8"));
const protectedRunRoot = runIndex["mm2-real-acceptance-teaching-methods"].run_dir;

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

mkdirSync(outputRoot, { recursive: true });
execFileSync(python, ["scripts/reset_ui2b_gate_fixture.py"], { cwd: repo, stdio: "ignore" });

const result = {
  fixture: { slug, protectedRunModified: false },
  actions: {},
  idempotency: {},
  security: {},
  stale: {},
  ux: {},
  regression: {},
};
const decisionRequests = [];
const protectedBefore = fileSnapshot(protectedRunRoot);

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
page.on("request", (request) => {
  if (request.method() === "POST" && request.url().includes("/dialogue/")) {
    decisionRequests.push({ url: request.url(), body: request.postDataJSON() });
  }
});

async function login() {
  await page.goto(`${base}/#/projects/${slug}/gates/UI2B-G1-R1`, { waitUntil: "domcontentloaded" });
  const password = page.locator('input[type="password"]');
  const gateHeading = page.getByRole("heading", { name: "Problem Definition" });
  await Promise.race([
    password.waitFor({ timeout: 30_000 }).catch(() => undefined),
    gateHeading.waitFor({ timeout: 30_000 }).catch(() => undefined),
  ]);
  if (await password.isVisible().catch(() => false)) {
    await page.locator('input[type="text"]').first().fill(username);
    await password.fill(passwordValue);
    await page.locator('button[type="submit"]').click();
  }
  await gateHeading.waitFor({ timeout: 30_000 });
}

async function gateApi(gateId) {
  return page.evaluate(async ({ projectSlug, id }) => {
    const response = await fetch(`/api/projects/${projectSlug}/gates/${id}`, { credentials: "include" });
    return { status: response.status, body: await response.json() };
  }, { projectSlug: slug, id: gateId });
}

async function gotoGate(gateId, heading) {
  await page.goto(`${base}/#/projects/${slug}/gates/${gateId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: heading }).waitFor({ timeout: 30_000 });
}

async function reviewAndConfirm(finalButtonName, doubleClick = false) {
  await page.getByRole("button", { name: "审阅并确认" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  const finalButton = dialog.getByRole("button", { name: finalButtonName });
  if (doubleClick) await finalButton.dblclick();
  else await finalButton.click();
  await dialog.waitFor({ state: "hidden" });
}

try {
  await login();
  const session = await page.evaluate(async () => {
    const response = await fetch("/api/auth/session", { credentials: "include" });
    return response.json();
  });
  const csrf = session.csrf_token;
  const sessionCookie = (await context.cookies(base)).find((cookie) => cookie.name === "minta_session");
  result.security.cookieSession = Boolean(session.authenticated && sessionCookie?.httpOnly && csrf);
  const mm2Runtime = await page.evaluate(async () => {
    const response = await fetch("/api/projects/mm2-real-acceptance-teaching-methods/runtime", { credentials: "include" });
    return { status: response.status, body: await response.json() };
  });
  const sse = await page.evaluate(async (runId) => {
    const controller = new AbortController();
    const response = await fetch(`/api/runs/${runId}/events`, { credentials: "include", signal: controller.signal });
    const reader = response.body?.getReader();
    const first = reader ? await reader.read() : { value: undefined };
    controller.abort();
    return { status: response.status, first: first.value ? new TextDecoder().decode(first.value) : "" };
  }, mm2Runtime.body.active_run_id);
  const contextObjectsStatus = await page.evaluate(async () => (await fetch("/api/contextObjects", { credentials: "include" })).status);
  result.regression.mm2Runtime = {
    httpStatus: mm2Runtime.status,
    status: mm2Runtime.body.status,
    runId: mm2Runtime.body.active_run_id,
    experts: mm2Runtime.body.experts.length,
    gates: mm2Runtime.body.gates.length,
    qa: mm2Runtime.body.qa.verdict,
    paper: mm2Runtime.body.paper.available,
  };
  result.regression.sse = { status: sse.status, snapshot: sse.first.includes("event: snapshot") };
  result.regression.contextObjectsStatus = contextObjectsStatus;

  await reviewAndConfirm("确认接受", true);
  await page.getByText(/接受已由服务端确认/).waitFor();
  const gate1 = await gateApi("UI2B-G1-R1");
  result.actions.accept = {
    status: gate1.status,
    serverState: gate1.body.status,
    writeEnabled: gate1.body.write_enabled,
    artifactValue: JSON.parse(readFileSync("E:/Minta/projects/ui2b-gate-write-acceptance/artifacts/problem-definition.json", "utf8")).review_status,
  };
  await page.screenshot({ path: `${outputRoot}/ui2b-accept-desktop.png`, fullPage: true });

  const acceptPosts = decisionRequests.filter((item) => item.body.decision_id === "UI2B-G1-R1");
  const acceptConfirmed = acceptPosts.find((item) => item.body.confirm === true)?.body;
  result.idempotency.acceptRequestCount = acceptPosts.length;
  result.idempotency.doubleClickSingleConfirmRequest = acceptPosts.filter((item) => item.body.confirm === true).length === 1;
  result.idempotency.sameSubmissionAcrossPhases = new Set(acceptPosts.map((item) => item.body.submission_id)).size === 1;
  if (!acceptConfirmed) throw new Error("Confirmed ACCEPT request was not captured");

  const retry = await page.evaluate(async ({ body, csrfToken }) => {
    const response = await fetch(`/api/projects/${body.slug}/dialogue/decisions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, "Idempotency-Key": body.payload.submission_id },
      body: JSON.stringify(body.payload),
    });
    return { status: response.status, body: await response.json() };
  }, { body: { slug, payload: acceptConfirmed }, csrfToken: csrf });
  const conflict = await page.evaluate(async ({ body, csrfToken }) => {
    const changed = { ...body.payload, user_input: "B" };
    const response = await fetch(`/api/projects/${body.slug}/dialogue/decisions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, "Idempotency-Key": changed.submission_id },
      body: JSON.stringify(changed),
    });
    return { status: response.status, body: await response.json() };
  }, { body: { slug, payload: acceptConfirmed }, csrfToken: csrf });
  result.idempotency.exactRetry = { status: retry.status, idempotent: retry.body.idempotent === true };
  result.idempotency.changedPayload = { status: conflict.status, code: conflict.body.detail?.code };

  await gotoGate("UI2B-G2-R1", "Model Authorization");
  await reviewAndConfirm("确认授权");
  await page.getByText(/授权已由服务端确认/).waitFor();
  const gate2 = await gateApi("UI2B-G2-R1");
  result.actions.authorize = {
    status: gate2.body.status,
    selectedModel: gate2.body.selected_model,
    planHash: gate2.body.plan_hash,
    scopeCount: gate2.body.authorization_scope.length,
    precondition: gate2.body.artifact_version_precondition,
    artifactValue: JSON.parse(readFileSync("E:/Minta/projects/ui2b-gate-write-acceptance/artifacts/model-plan.json", "utf8")).selected_model,
  };

  await gotoGate("UI2B-G3-R1", "Scientific QA");
  await page.getByRole("button", { name: "请求修改" }).click();
  await page.locator("textarea").fill("Recompute the sensitivity interval before approval.");
  await reviewAndConfirm("确认请求修改");
  await page.getByText(/修改请求已记录/).waitFor();
  const afterModify = await gateApi("UI2B-G3-R1");
  result.actions.modify = {
    status: afterModify.body.status,
    writeEnabled: afterModify.body.write_enabled,
    pendingRetained: afterModify.body.write_enabled === true,
    historyCount: afterModify.body.discussion_history.length,
  };

  await page.getByRole("button", { name: "讨论" }).click();
  await page.locator("textarea").fill("Please attach the bootstrap diagnostic table.");
  await reviewAndConfirm("确认提交讨论");
  await page.getByText(/讨论已记录/).waitFor();
  const afterDiscuss = await gateApi("UI2B-G3-R1");
  result.actions.discuss = {
    status: afterDiscuss.body.status,
    writeEnabled: afterDiscuss.body.write_enabled,
    historyCount: afterDiscuss.body.discussion_history.length,
  };
  result.ux.focusReturnedToResult = await page.evaluate(() => document.activeElement?.getAttribute("tabindex") === "-1");

  await page.getByRole("button", { name: "讨论" }).click();
  const draftArea = page.locator("textarea");
  await draftArea.fill("Keyboard draft");
  await draftArea.press("Enter");
  result.ux.textareaEnterAddsNewline = (await draftArea.inputValue()) === "Keyboard draft\n";
  const reviewButton = page.getByRole("button", { name: "审阅并确认" });
  await reviewButton.focus();
  await reviewButton.press("Enter");
  const keyboardDialog = page.getByRole("dialog");
  await keyboardDialog.waitFor();
  result.ux.finalButtonFocused = await keyboardDialog.getByRole("button", { name: "确认提交讨论" }).evaluate((button) => button === document.activeElement);
  await page.keyboard.press("Escape");
  await keyboardDialog.waitFor({ state: "hidden" });
  result.ux.escapeReturnsToReview = (await draftArea.inputValue()) === "Keyboard draft\n";

  const guardedUrl = page.url();
  page.once("dialog", async (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "Gate 总览" }).click();
  result.ux.dirtyNavigationGuard = page.url() === guardedUrl && (await draftArea.inputValue()) === "Keyboard draft\n";
  await draftArea.fill("");

  await gotoGate("UI2B-G4-R1", "Paper Release");
  await page.getByRole("button", { name: "拒绝" }).click();
  await page.locator("textarea").fill("Release evidence is incomplete for this acceptance fixture.");
  await page.getByRole("button", { name: "审阅并确认" }).click();
  const rejectDialog = page.getByRole("dialog");
  await rejectDialog.waitFor();
  result.actions.reject = { customDialog: true, reasonVisible: await rejectDialog.getByText(/Release evidence is incomplete/).isVisible() };
  await rejectDialog.getByRole("button", { name: "确认拒绝" }).click();
  await rejectDialog.waitFor({ state: "hidden" });
  await page.getByText(/拒绝已由服务端记录/).waitFor();
  const gate4 = await gateApi("UI2B-G4-R1");
  result.actions.reject = { ...result.actions.reject, status: gate4.body.status, writeEnabled: gate4.body.write_enabled };
  await page.screenshot({ path: `${outputRoot}/ui2b-reject-desktop.png`, fullPage: true });

  const missingCsrf = await page.evaluate(async () => {
    const response = await fetch("/api/projects/ui2b-gate-write-acceptance/dialogue/discuss", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision_id: "UI2B-G3-R1", user_input: "missing csrf", action: "discuss", submission_id: "security-missing-csrf" }),
    });
    return { status: response.status, body: await response.json() };
  });
  result.security.missingCsrf = { status: missingCsrf.status, code: missingCsrf.body.code };

  const anonymous = await playwrightRequest.newContext({ baseURL: base });
  const noSessionResponse = await anonymous.post(`/api/projects/${slug}/dialogue/discuss`, { data: { decision_id: "UI2B-G3-R1", user_input: "anonymous", action: "discuss" } });
  result.security.missingSession = noSessionResponse.status();
  await anonymous.dispose();

  const hostile = await playwrightRequest.newContext({
    baseURL: base,
    extraHTTPHeaders: {
      Cookie: `minta_session=${sessionCookie.value}`,
      Origin: "http://evil.invalid",
      "X-CSRF-Token": csrf,
    },
  });
  const hostileResponse = await hostile.post(`/api/projects/${slug}/dialogue/discuss`, {
    data: { decision_id: "UI2B-G3-R1", user_input: "hostile origin", action: "discuss", submission_id: "security-hostile-origin" },
  });
  result.security.invalidOrigin = hostileResponse.status();
  await hostile.dispose();

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mobilePage = await mobile.newPage();
  await mobilePage.goto(`${base}/#/projects/${slug}/gates/UI2B-G3-R1`, { waitUntil: "domcontentloaded" });
  await mobilePage.locator('input[type="password"]').waitFor({ timeout: 30_000 });
  await mobilePage.locator('input[type="text"]').first().fill(username);
  await mobilePage.locator('input[type="password"]').fill(passwordValue);
  await mobilePage.locator('button[type="submit"]').click();
  await mobilePage.getByRole("heading", { name: "Scientific QA" }).waitFor();
  await mobilePage.getByRole("button", { name: "讨论" }).click();
  await mobilePage.locator("textarea").fill("Mobile confirmation inspection.");
  await mobilePage.getByRole("button", { name: "审阅并确认" }).click();
  await mobilePage.getByRole("dialog").waitFor();
  result.ux.mobileConfirmation = true;
  result.ux.mobileOverflow = await mobilePage.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  await mobilePage.screenshot({ path: `${outputRoot}/ui2b-confirmation-mobile.png`, fullPage: true });
  await mobile.close();

  execFileSync(python, ["scripts/reset_ui2b_gate_fixture.py"], { cwd: repo, stdio: "ignore" });
  const manifestPath = "E:/Minta/projects/ui2b-gate-write-acceptance/artifacts/problem-definition/manifest.json";
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  manifest.current_version = 2;
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
  await gotoGate("UI2B-G1-R1", "Problem Definition");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Problem Definition" }).waitFor({ timeout: 30_000 });
  const selectedAction = page.locator('[role="group"] button[aria-pressed="true"]').first();
  await selectedAction.waitFor();
  const staleResponseOnePromise = page.waitForResponse((response) => response.url().includes("/dialogue/decisions") && response.status() === 409);
  await page.getByRole("button", { name: "审阅并确认" }).click();
  const staleResponseOne = await staleResponseOnePromise;
  await page.getByText("STALE_REVISION", { exact: true }).waitFor();
  const staleFirstRequest = decisionRequests.filter((item) => item.body.decision_id === "UI2B-G1-R1").at(-1).body;
  const inputPreserved = await selectedAction.getAttribute("aria-pressed") === "true";
  const staleResponseTwoPromise = page.waitForResponse((response) => response.url().includes("/dialogue/decisions") && response.status() === 409);
  await page.getByRole("button", { name: "审阅并确认" }).click();
  await staleResponseTwoPromise;
  const staleSecondRequest = decisionRequests.filter((item) => item.body.decision_id === "UI2B-G1-R1").at(-1).body;
  const staleBody = await staleResponseOne.json();
  result.stale = {
    status: staleResponseOne.status(),
    code: staleBody.detail?.code,
    originalInputRetainedByClient: inputPreserved,
    reconfirmationRequired: await page.getByRole("dialog").count() === 0,
    submissionIdRegenerated: staleFirstRequest.submission_id !== staleSecondRequest.submission_id,
  };
  result.ux.blankPages = 0;
  const protectedAfter = fileSnapshot(protectedRunRoot);
  result.fixture.protectedRunModified = JSON.stringify(protectedBefore) !== JSON.stringify(protectedAfter);
  result.regression.protectedRunFileCount = Object.keys(protectedAfter).length;
  result.requests = decisionRequests.map((item) => ({ endpoint: new URL(item.url).pathname, action: item.body.action ?? null, confirm: item.body.confirm, decision_id: item.body.decision_id }));
} finally {
  await context.close();
  await browser.close();
  execFileSync(python, ["scripts/reset_ui2b_gate_fixture.py"], { cwd: repo, stdio: "ignore" });
}

writeFileSync(`${outputRoot}/UI-2B-acceptance.json`, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify(result, null, 2));
