import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.MINTA_E2E_BASE_URL ?? "http://localhost:8772";
const username = process.env.MINTA_E2E_USERNAME;
const password = process.env.MINTA_E2E_PASSWORD;
const outputDir = process.env.MINTA_E2E_OUTPUT_DIR;

if (!username || !password) {
  throw new Error("Set MINTA_E2E_USERNAME and MINTA_E2E_PASSWORD for the real browser login flow.");
}
if (!outputDir) {
  throw new Error("Set MINTA_E2E_OUTPUT_DIR to the E-drive acceptance output directory.");
}

await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const postAuthErrors = [];
let authenticated = false;

page.on("console", (message) => {
  if (authenticated && message.type() === "error") {
    postAuthErrors.push({ kind: "console", message: message.text() });
  }
});
page.on("pageerror", (error) => {
  if (authenticated) postAuthErrors.push({ kind: "page", message: error.message });
});
page.on("response", (response) => {
  if (authenticated && response.status() >= 400) {
    postAuthErrors.push({ kind: "http", status: response.status(), url: response.url() });
  }
});

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function matchesAppHref(actual, apiHref) {
  return actual === apiHref || actual === `#${apiHref}`;
}

async function login() {
  await page.goto(`${baseUrl}/#/projects`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  const passwordInput = page.locator('input[type="password"]');
  if (await passwordInput.count()) {
    await page.locator('input[type="text"]').first().fill(username);
    await passwordInput.fill(password);
    await page.locator('button[type="submit"]').click();
    await page.waitForFunction(() => !document.querySelector('input[type="password"]'), null, { timeout: 30_000 });
  }
  authenticated = true;
}

async function apiGet(urlPath) {
  return page.evaluate(async (target) => {
    const response = await fetch(target, { credentials: "include" });
    return { status: response.status, body: await response.json() };
  }, urlPath);
}

async function loadSummary(slug, label, viewport = { width: 1440, height: 900 }) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseUrl}/#/projects/${encodeURIComponent(slug)}/overview`, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  const summary = page.getByLabel("研究状态摘要");
  await summary.waitFor({ state: "visible", timeout: 30_000 });
  await page.waitForTimeout(500);
  const result = await summary.evaluate((element) => {
    const decisionLink = element.querySelector("a");
    return {
      text: element.textContent?.replace(/\s+/g, " ").trim() ?? "",
      decisionHref: decisionLink?.getAttribute("href") ?? null,
      decisionLabel: decisionLink?.textContent?.replace(/\s+/g, " ").trim() ?? null,
    };
  });
  const layout = await page.evaluate(() => {
    const overflowing = Array.from(document.querySelectorAll("body *"))
      .filter((element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.position !== "fixed" && (rect.right > innerWidth + 1 || rect.left < -1);
      })
      .slice(0, 10)
      .map((element) => ({
        tag: element.tagName,
        text: element.textContent?.replace(/\s+/g, " ").slice(0, 80),
      }));
    return {
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      overflowing,
    };
  });
  await page.screenshot({ path: path.join(outputDir, `${label}-${viewport.width}x${viewport.height}.png`), fullPage: true });
  return { ...result, layout };
}

function idleRuntime(slug) {
  return {
    project_slug: slug,
    active_run_id: null,
    status: "idle",
    revision: 0,
    updated_at: new Date(0).toISOString(),
    current_stage: null,
    next_action: { kind: "none", href: null, disabled_reason: null },
    experts: [],
    gates: [],
    qa: { verdict: null, artifact_name: null },
    paper: { available: false, artifact_name: null },
    package: { eligible: false, package_id: null },
  };
}

try {
  await login();

  const projectsResponse = await apiGet("/api/projects");
  assert(projectsResponse.status === 200, `Project list returned ${projectsResponse.status}`);
  const runtimes = [];
  for (const project of projectsResponse.body.projects ?? []) {
    const response = await apiGet(`/api/projects/${encodeURIComponent(project.slug)}/runtime`);
    if (response.status === 200) runtimes.push({ slug: project.slug, runtime: response.body });
  }

  const blocked = runtimes.find(({ runtime }) =>
    ["BLOCKED", "FAILED"].includes(runtime.qa?.verdict),
  );
  assert(blocked, "No real project exposes blocked QA.");

  const blockedResult = await loadSummary(blocked.slug, "blocked-gate-desktop");
  const blockedGate = blocked.runtime.gates.find((gate) => gate.status === "pending");
  assert(blockedResult.text.includes("刚刚发生"), "Blocked summary does not explain the current stage.");
  assert(blockedResult.text.includes("为什么停"), "Blocked summary does not explain the blocker.");
  assert(blockedResult.text.includes("下一步"), "Blocked summary does not explain the next action.");
  assert(
    blockedResult.text.includes("科学验证未通过") || blockedResult.text.includes("验证结果阻止流程继续"),
    "Blocked QA is not translated into research language.",
  );
  if (blockedGate) {
    assert(matchesAppHref(blockedResult.decisionHref, blockedGate.href), "Gate link does not use the href returned by the Runtime API.");
  } else {
    assert(blockedResult.decisionHref === null, "Blocked QA without a pending Gate exposes a fake Gate link.");
  }
  assert(blockedResult.layout.overflowing.length === 0, "Desktop blocked summary overflows horizontally.");

  const noQa = runtimes.find(({ runtime }) =>
    runtime.qa?.verdict == null && runtime.project_slug !== blocked.runtime.project_slug,
  );
  assert(noQa, "No real project without QA is available for acceptance.");
  const noQaResult = await loadSummary(noQa.slug, "no-qa-desktop");
  assert(!noQaResult.text.includes("科学验证未通过"), "A project without QA is falsely described as a QA failure.");

  const emptySlug = "overview-contract-empty-project";
  await page.route(`**/api/projects/${emptySlug}/runtime`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(idleRuntime(emptySlug)),
  }));
  await page.route(`**/api/projects/${emptySlug}/artifacts`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ artifacts: [] }),
  }));
  const emptyResult = await loadSummary(emptySlug, "no-active-run-desktop");
  assert(emptyResult.text.includes("等待运行"), "No-run project does not show the generic idle state.");
  assert(emptyResult.decisionHref === null, "No-run project exposes a fake Gate link.");

  const otherGate = runtimes.find(({ runtime }) => {
    const gate = runtime.gates?.find((item) => item.status === "pending");
    return gate && (!blockedGate || gate.gate_number !== blockedGate.gate_number) && gate.href;
  });
  assert(otherGate, "No real project with a different pending Gate is available for link verification.");
  const otherGateStatus = otherGate.runtime.gates.find((gate) => gate.status === "pending");
  const otherGateResult = await loadSummary(otherGate.slug, "different-gate-desktop");
  assert(matchesAppHref(otherGateResult.decisionHref, otherGateStatus.href), "Different-Gate link is not projected from the Runtime API.");

  const mobileResult = await loadSummary(blocked.slug, "blocked-gate-mobile", { width: 390, height: 844 });
  assert(mobileResult.layout.documentWidth <= 391, "Mobile page has horizontal document overflow.");
  assert(mobileResult.layout.overflowing.length === 0, "Mobile blocked summary contains overflowing elements.");

  const technicalTextVisible = await page.locator("body").innerText();
  assert(!/ed274198|fa331f67|289899de/.test(technicalTextVisible), "Run-specific hashes are visible in the Overview summary.");

  const report = {
    status: "PASS",
    baseUrl,
    generatedAt: new Date().toISOString(),
    discoveredProjects: runtimes.length,
    scenarios: {
      blockedGate: { slug: blocked.slug, gate: blockedGate?.gate_number ?? null, ...blockedResult },
      noQa: { slug: noQa.slug, ...noQaResult },
      noActiveRun: { slug: emptySlug, ...emptyResult },
      differentGate: { slug: otherGate.slug, gate: otherGateStatus.gate_number, ...otherGateResult },
      mobile: { slug: blocked.slug, ...mobileResult },
    },
    postAuthErrors,
  };
  assert(postAuthErrors.length === 0, `Post-auth browser errors detected: ${JSON.stringify(postAuthErrors)}`);
  await fs.writeFile(path.join(outputDir, "research-overview-acceptance.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  const failure = {
    status: "FAIL",
    baseUrl,
    generatedAt: new Date().toISOString(),
    error: error instanceof Error ? error.stack ?? error.message : String(error),
    postAuthErrors,
  };
  await fs.writeFile(path.join(outputDir, "research-overview-acceptance.json"), `${JSON.stringify(failure, null, 2)}\n`, "utf8");
  console.error(JSON.stringify(failure, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
