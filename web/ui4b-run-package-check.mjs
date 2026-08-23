import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const runId = "MM2-REAL-02";
const fixtureSlug = "ui4b-browser-fixture";
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

function browserSignals(page) {
  const result = { authenticated: false, pre_auth: [], post_auth: [], network: [], requests: [] };
  page.on("console", (message) => {
    if (message.type() === "error") (result.authenticated ? result.post_auth : result.pre_auth).push(message.text());
  });
  page.on("response", (response) => {
    if (result.authenticated && response.status() >= 400) result.network.push({ status: response.status(), url: response.url() });
  });
  page.on("request", (request) => {
    if (result.authenticated && ["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) result.requests.push({ method: request.method(), url: request.url() });
  });
  return result;
}

async function login(page, target, signals) {
  await page.goto(`${base}/#${target}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  const password = page.locator('input[type="password"]');
  await Promise.race([
    password.waitFor({ timeout: 30_000 }).catch(() => undefined),
    page.getByRole("heading", { name: "Reproducible delivery package" }).waitFor({ timeout: 30_000 }).catch(() => undefined),
  ]);
  if (await password.isVisible().catch(() => false)) {
    await page.locator('input[type="text"]').first().fill("uitest");
    await password.fill("uitest123");
    await page.locator('button[type="submit"]').click();
  }
  await page.getByRole("heading", { name: "Reproducible delivery package" }).waitFor({ timeout: 30_000 });
  signals.authenticated = true;
}

async function verifyRealPage(browser, viewport, label) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const signals = browserSignals(page);
  await login(page, `/projects/${slug}/package`, signals);
  const api = await page.evaluate(async (projectSlug) => {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectSlug)}/package`, { credentials: "include", headers: { Accept: "application/json" } });
    return { status: response.status, body: await response.json() };
  }, slug);
  assert(api.status === 200, "package API did not return 200");
  assert(api.body.run_id === runId, "package API is not bound to MM2-REAL-02");
  assert(api.body.package_status === "not_built", "MM2 must not be presented as a finalized package");
  assert(api.body.package_eligible === true, "MM2 should remain eligible for package build");
  assert(api.body.verify_available === false, "verify must be disabled without a manifest");
  assert(api.body.download_available === false, "download must be disabled without verification");
  await page.getByRole("heading", { name: "Package not built" }).waitFor();
  assert(await page.getByRole("button", { name: "Verify" }).isDisabled(), "Verify is enabled for an unbuilt package");
  assert(await page.getByRole("button", { name: "Download" }).isDisabled(), "Download is enabled for an unbuilt package");
  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    blank: !document.body.innerText.trim(),
  }));
  await page.screenshot({ path: `${outputRoot}/ui4b-package-not-built-${label}.png`, fullPage: true });

  await page.getByRole("link", { name: "Back to Knowledge Base" }).first().click();
  await page.waitForURL(`${base}/#/`, { timeout: 30_000 });
  await page.locator('[aria-label="打开 Minta Research 项目列表"]').waitFor({ state: "attached", timeout: 30_000 });
  const returnedHome = await page.evaluate(() => window.location.hash === "#/" || window.location.hash === "");
  const homeMounted = (await page.locator('[aria-label="打开 Minta Research 项目列表"]').count()) === 1;
  assert(returnedHome, "Back to Knowledge Base did not return to the root application");
  assert(homeMounted, "Knowledge Base did not mount after returning to the root application");
  await context.close();
  return { api: api.body, signals, layout, returned_home: returnedHome, home_mounted: homeMounted };
}

const basePackage = {
  project_slug: fixtureSlug,
  run_id: "UI4B-BROWSER-01",
  package_status: "available",
  package_id: "ERP-UI4B-BROWSER-01",
  schema_version: "1.0.0",
  runtime_status: "completed",
  package_eligible: true,
  eligibility_reason: "The run is completed, QA is PASSED, and Gate 4 is accepted.",
  required_fields: [
    { field: "schema_version", present: true, value_preview: "1.0.0" },
    { field: "run_id", present: true, value_preview: "UI4B-BROWSER-01" },
    { field: "artifact_index", present: true, value_preview: "4 entries" },
    { field: "evidence_map", present: true, value_preview: "1 entries" },
  ],
  files: [
    { path: "results/normalized-results.json", role: "result", sha256: "a".repeat(64), size_bytes: 128, exists: true, listed_in_manifest: true, listed_in_hashes: true, hash_matches: null },
    { path: "report/paper-draft.md", role: "report", sha256: "b".repeat(64), size_bytes: 256, exists: true, listed_in_manifest: true, listed_in_hashes: true, hash_matches: null },
  ],
  evidence: [
    { evidence_id: "EVD-BROWSER-01", artifact: "results/normalized-results.json", artifact_sha256: "a".repeat(64), field_path: "/metrics/score", qa_status: "passed", artifact_present: true, hash_matches: null, pointer_valid: null },
  ],
  qa_binding: { verdict: "PASSED", artifact: "report/scientific-qa-report.json", artifact_sha256: "c".repeat(64), artifact_present: true, hash_matches: null, verdict_matches: null },
  gate4_binding: { decision: "ACCEPT", decision_id: "UI4B-G4", artifact: "run/gates/human-gate-4.json", artifact_sha256: "d".repeat(64), paper_artifact: "report/paper-draft.md", paper_artifact_sha256: "b".repeat(64), artifact_present: true, hash_matches: null, decision_matches: null, paper_hash_matches: null, recorded_paper_hash_matches: null },
  determinism_hash: "e".repeat(64),
  execution_mode: "controlled_subprocess",
  sandboxed: false,
  integrity: { status: "not_verified", manifest_valid: true, required_fields_complete: true, hash_closure_valid: null, artifact_index_valid: null, evidence_closure_valid: null, qa_binding_valid: null, gate4_binding_valid: null, files_checked: 0, verified_at: null, issues: [] },
  verify_available: true,
  download_available: false,
  download_href: null,
  download_reason: "Verify the package hash closure before download.",
  data_gaps: [],
};

function verification(status) {
  const pass = status === "verified";
  return {
    project_slug: fixtureSlug,
    run_id: "UI4B-BROWSER-01",
    package_id: "ERP-UI4B-BROWSER-01",
    integrity: { status, manifest_valid: true, required_fields_complete: true, hash_closure_valid: pass, artifact_index_valid: pass, evidence_closure_valid: pass, qa_binding_valid: pass, gate4_binding_valid: pass, files_checked: 6, verified_at: "2026-08-07T05:00:00+00:00", issues: pass ? [] : ["HASH_MISMATCH:results/normalized-results.json"] },
    files: basePackage.files.map((file) => ({ ...file, hash_matches: pass })),
    evidence: basePackage.evidence.map((item) => ({ ...item, hash_matches: pass, pointer_valid: true })),
    qa_binding: { ...basePackage.qa_binding, hash_matches: pass, verdict_matches: true },
    gate4_binding: { ...basePackage.gate4_binding, hash_matches: pass, decision_matches: pass, paper_hash_matches: pass, recorded_paper_hash_matches: pass },
    download_available: pass,
    download_href: pass ? `/api/projects/${fixtureSlug}/package/download` : null,
    download_reason: pass ? "Package verification passed." : "Download is disabled because package integrity verification did not pass.",
  };
}

async function verifyFixture(browser, outcome) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  const signals = browserSignals(page);
  let packageRequestHit = false;
  let verifyRequestHit = false;
  await page.route(`**/api/projects/${fixtureSlug}/package/verify`, async (route) => {
    verifyRequestHit = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(verification(outcome)) });
  });
  await page.route(`**/api/projects/${fixtureSlug}/package`, async (route) => {
    packageRequestHit = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(basePackage) });
  });
  await login(page, `/projects/${fixtureSlug}/package`, signals);
  await page.getByRole("button", { name: "Verify" }).click();
  await page.getByText(outcome, { exact: true }).first().waitFor();
  if (outcome === "verified") {
    await page.getByRole("link", { name: "Download" }).waitFor();
  } else {
    await page.getByText("HASH_MISMATCH:results/normalized-results.json", { exact: true }).waitFor();
    assert(await page.getByRole("button", { name: "Download" }).isDisabled(), "tampered package download is enabled");
  }
  await page.screenshot({ path: `${outputRoot}/ui4b-package-${outcome}-fixture.png`, fullPage: true });
  const result = { package_request_hit: packageRequestHit, verify_request_hit: verifyRequestHit, post_auth_errors: signals.post_auth, network_errors: signals.network, requests: signals.requests };
  await context.close();
  return result;
}

const before = snapshot(runRoot);
const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  const desktop = await verifyRealPage(browser, { width: 1440, height: 950 }, "desktop");
  const mobile = await verifyRealPage(browser, { width: 390, height: 844 }, "mobile-390");
  const validFixture = await verifyFixture(browser, "verified");
  const tamperedFixture = await verifyFixture(browser, "tampered");
  const after = snapshot(runRoot);
  const result = {
    slice: "UI-4B-RUN-PACKAGE-INSPECTOR",
    status: "IMPLEMENTATION_VERIFIED",
    real_MM2: {
      run_id: desktop.api.run_id,
      package_status: desktop.api.package_status,
      package_eligible: desktop.api.package_eligible,
      integrity: desktop.api.integrity.status,
      verify_available: desktop.api.verify_available,
      download_available: desktop.api.download_available,
      honest_not_built_state: desktop.api.package_status === "not_built",
    },
    fixture: { verified: validFixture, tampered: tamperedFixture },
    navigation: { desktop_returned_home: desktop.returned_home, mobile_returned_home: mobile.returned_home },
    browser: {
      desktop_blank: desktop.layout.blank,
      mobile_blank: mobile.layout.blank,
      mobile_horizontal_overflow: mobile.layout.scrollWidth - mobile.layout.clientWidth,
      post_auth_console_errors: [...desktop.signals.post_auth, ...mobile.signals.post_auth, ...validFixture.post_auth_errors, ...tamperedFixture.post_auth_errors],
      unexpected_network_errors: [...desktop.signals.network, ...mobile.signals.network, ...validFixture.network_errors, ...tamperedFixture.network_errors],
      real_MM2_write_requests: [...desktop.signals.requests, ...mobile.signals.requests],
      fixture_verify_requests: [...validFixture.requests, ...tamperedFixture.requests],
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
  assert(result.browser.real_MM2_write_requests.length === 0, "real MM2 package inspection issued a write request");
  assert(validFixture.package_request_hit && validFixture.verify_request_hit, "verified fixture did not exercise both endpoints");
  assert(tamperedFixture.package_request_hit && tamperedFixture.verify_request_hit, "tampered fixture did not exercise both endpoints");
  assert(result.protected_run.hashes_identical, "MM2-REAL-02 changed during package acceptance");
  writeFileSync(`${outputRoot}/UI-4B-run-package-inspector.json`, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
