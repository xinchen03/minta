import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const runId = "MM2-REAL-02";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const runRoot = "E:/Minta/Codex/2026-08-05/70-70-mm-4a-status-note/outputs/mm2-real-acceptance/run-MM2-REAL-02";
const outputRoot = "E:/Minta/Codex/2026-08-07/files-mentioned-by-the-user-min/outputs";

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

async function login(page, target, errors) {
  await page.goto(`${base}/#${target}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  const password = page.locator('input[type="password"]');
  await Promise.race([
    password.waitFor({ timeout: 30_000 }).catch(() => undefined),
    page.getByText("Paper Studio", { exact: true }).first().waitFor({ timeout: 30_000 }).catch(() => undefined),
  ]);
  if (await password.isVisible().catch(() => false)) {
    await page.locator('input[type="text"]').first().fill("uitest");
    await password.fill("uitest123");
    await page.locator('button[type="submit"]').click();
  }
  await page.getByText("Paper Studio", { exact: true }).first().waitFor({ timeout: 30_000 });
  errors.authenticated = true;
}

async function verifyPage(browser, viewport, label) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = { authenticated: false, pre_auth: [], post_auth: [], network: [], writes: [] };
  page.on("console", (message) => {
    if (message.type() === "error") (errors.authenticated ? errors.post_auth : errors.pre_auth).push(message.text());
  });
  page.on("response", (response) => {
    const status = response.status();
    if (errors.authenticated && status >= 400) errors.network.push({ status, url: response.url() });
  });
  page.on("request", (request) => {
    if (errors.authenticated && ["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
      errors.writes.push({ method: request.method(), url: request.url() });
    }
  });

  await login(page, `/projects/${slug}/paper`, errors);
  const api = await page.evaluate(async (projectSlug) => {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectSlug)}/paper`, { credentials: "include", headers: { Accept: "application/json" } });
    return { status: response.status, body: await response.json() };
  }, slug);
  assert(api.status === 200, "paper API did not return 200");
  assert(api.body.run_id === runId, "paper API is not bound to MM2-REAL-02");
  assert(api.body.status === "completed", "runtime status is not completed");
  assert(api.body.content.includes("MM2-REAL-02"), "paper content is missing the real run id");
  assert(api.body.evidence.length === 40, "expected 40 real paper evidence records");
  assert(api.body.qa_verdict === "PASSED", "paper QA verdict is not PASSED");
  assert(api.body.gate4.status === "accepted", "Gate 4 is not accepted");
  assert(api.body.diff.available === false, "MM2 should not invent a prior paper version");

  await page.getByRole("tab", { name: "Paper Reader" }).click();
  await page.getByRole("heading", { name: /教学方法 A 与 B/ }).first().waitFor();
  await page.locator("#main").evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: `${outputRoot}/ui4a-paper-reader-${label}.png`, fullPage: true });

  await page.getByRole("tab", { name: "Claim / Evidence" }).click();
  await page.getByRole("heading", { name: "Evidence index", exact: true }).waitFor();
  assert((await page.locator("tbody tr").count()) === 40, "evidence table did not render 40 records");
  if (label === "desktop") await page.screenshot({ path: `${outputRoot}/ui4a-claim-evidence-desktop.png`, fullPage: true });

  await page.getByRole("tab", { name: "Version Diff" }).click();
  await page.getByText(/No versioned paper-draft/).waitFor();
  if (label === "desktop") await page.screenshot({ path: `${outputRoot}/ui4a-version-diff-desktop.png`, fullPage: true });

  await page.getByRole("tab", { name: "Gate 4" }).click();
  await page.getByRole("heading", { name: "accepted", exact: true }).waitFor();
  if (label === "desktop") await page.screenshot({ path: `${outputRoot}/ui4a-gate4-desktop.png`, fullPage: true });

  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    blank: !document.body.innerText.trim(),
  }));
  await context.close();
  return { api: api.body, errors, layout };
}

const before = snapshot(runRoot);
const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  const desktop = await verifyPage(browser, { width: 1440, height: 950 }, "desktop");
  const mobile = await verifyPage(browser, { width: 390, height: 844 }, "mobile-390");
  const after = snapshot(runRoot);
  const result = {
    slice: "UI-4A-PAPER-STUDIO",
    status: "IMPLEMENTATION_VERIFIED",
    paper: {
      run_id: desktop.api.run_id,
      runtime_status: desktop.api.status,
      real_artifact: Boolean(desktop.api.content),
      sections: desktop.api.sections.length,
      evidence_records: desktop.api.evidence.length,
      claim_traces: desktop.api.claims.length,
      qa_verdict: desktop.api.qa_verdict,
      paper_eligible: desktop.api.paper_eligible,
      current_sha256: desktop.api.sha256,
      export_file_sha256: desktop.api.file_sha256,
      hash_source: desktop.api.hash_source,
      recorded_evidence_map_sha256: desktop.api.gate4.paper_artifact_hash,
      hash_alignment: desktop.api.sha256 === desktop.api.gate4.paper_artifact_hash,
      data_gaps: desktop.api.data_gaps,
    },
    version_diff: { available: desktop.api.diff.available, reason: desktop.api.diff.reason, versions: desktop.api.versions.map((item) => item.version) },
    gate4: desktop.api.gate4,
    browser: {
      desktop_blank: desktop.layout.blank,
      mobile_blank: mobile.layout.blank,
      mobile_horizontal_overflow: mobile.layout.scrollWidth - mobile.layout.clientWidth,
      post_auth_console_errors: [...desktop.errors.post_auth, ...mobile.errors.post_auth],
      unexpected_network_errors: [...desktop.errors.network, ...mobile.errors.network],
      write_requests: [...desktop.errors.writes, ...mobile.errors.writes],
      pre_auth_console_errors: [...desktop.errors.pre_auth, ...mobile.errors.pre_auth],
    },
    protected_run: {
      files_before: Object.keys(before).length,
      files_after: Object.keys(after).length,
      hashes_identical: JSON.stringify(before) === JSON.stringify(after),
    },
  };
  assert(result.browser.desktop_blank === false, "desktop page is blank");
  assert(result.browser.mobile_blank === false, "mobile page is blank");
  assert(result.browser.mobile_horizontal_overflow === 0, "mobile page has horizontal overflow");
  assert(result.browser.post_auth_console_errors.length === 0, "post-auth console errors observed");
  assert(result.browser.unexpected_network_errors.length === 0, "post-auth network errors observed");
  assert(result.browser.write_requests.length === 0, "Paper acceptance issued a write request");
  assert(result.protected_run.hashes_identical, "MM2-REAL-02 changed during Paper acceptance");
  writeFileSync(`${outputRoot}/UI-4A-paper-studio.json`, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
