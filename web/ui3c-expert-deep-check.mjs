import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { basename, join, relative } from "node:path";

const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const runId = "MM2-REAL-02";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const outputRoot = "E:/Minta/Codex/2026-08-07/files-mentioned-by-the-user-min/outputs";
const notebookFixturePath = "C:/Users/Lenovo/Desktop/Minta-next/tests/fixtures/ui3c/notebook-rendering.ipynb";

const expectedExperts = [
  ["math.problem_reframer", "Problem Reframer"],
  ["math.model_designer", "Model Designer"],
  ["math.execution_engineer", "Execution Engineer"],
  ["math.scientific_validator", "Scientific Validator"],
  ["math.paper_synthesizer", "Paper Synthesizer"],
];

function fileSnapshot(root) {
  const hashes = {};
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile()) {
        hashes[relative(root, path).replace(/\\/g, "/")] = createHash("sha256").update(readFileSync(path)).digest("hex");
      }
    }
  };
  visit(root);
  return hashes;
}

function parseNotebookFixture() {
  const raw = JSON.parse(readFileSync(notebookFixturePath, "utf8"));
  const language = raw.metadata?.language_info?.name ?? raw.metadata?.kernelspec?.language ?? "python";
  const joinSource = (value) => Array.isArray(value) ? value.join("") : String(value ?? "");
  return {
    project_slug: slug,
    run_id: runId,
    expert_id: "math.model_designer",
    artifact: basename(notebookFixturePath),
    nbformat: raw.nbformat,
    nbformat_minor: raw.nbformat_minor,
    language,
    cells: raw.cells.map((cell) => ({
      cell_type: cell.cell_type,
      source: joinSource(cell.source),
      execution_count: cell.execution_count ?? null,
      outputs: (cell.outputs ?? []).map((output) => ({
        output_type: output.output_type,
        name: output.name ?? null,
        text: output.text ? joinSource(output.text) : null,
        data: Object.fromEntries(Object.entries(output.data ?? {}).map(([key, value]) => [key, joinSource(value)])),
        error_name: output.ename ?? output.error_name ?? null,
        error_value: output.evalue ?? output.error_value ?? null,
        traceback: (output.traceback ?? []).map(String),
      })),
    })),
  };
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
    const response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
    return { status: response.status, body: await response.json() };
  }, path);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function byId(items, key) {
  return Object.fromEntries(items.map((item) => [item[key], item]));
}

function lineageHas(detail, artifact, sha256 = null) {
  return [...detail.inputs, ...detail.outputs].some((item) =>
    item.artifact === artifact && (sha256 === null || item.sha256 === sha256),
  );
}

async function verifyRealCockpit(page) {
  await login(page, `/projects/${slug}/research`);
  await page.getByRole("heading", { name: "Research Cockpit", exact: true }).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(250);

  const expertList = await api(page, `/api/projects/${slug}/research/experts`);
  assert(expertList.status === 200, "expert list did not return 200");
  assert(expertList.body.run_id === runId, "expert list is not bound to MM2-REAL-02");
  assert(expertList.body.experts.length === 5, "expected five expert summaries");
  assert(expertList.body.experts.every((expert) => expert.status === "completed"), "all five experts must be completed");
  assert(expertList.body.source_conflicts.length === 0, "MM2 expert list should not expose source conflicts");

  const details = {};
  for (const [expertId, role] of expectedExperts) {
    await page.getByText(role, { exact: true }).first().click();
    await page.getByRole("button", { name: "Artifacts", exact: true }).click();
    await page.getByText("Inputs", { exact: true }).first().waitFor();
    await page.getByText("Outputs", { exact: true }).first().waitFor();
    await page.getByRole("button", { name: "Evidence", exact: true }).click();
    await page.getByText("Provider details", { exact: true }).first().waitFor();
    await page.getByText("claude-code-cli", { exact: true }).first().waitFor();
    await page.getByText("deepseek-v4-flash[1M]", { exact: true }).first().waitFor();
    await page.getByRole("button", { name: "Notebook", exact: true }).click();
    await page.getByText("Notebook not recorded", { exact: true }).first().waitFor();
    const detail = await api(page, `/api/projects/${slug}/research/experts/${expertId}`);
    assert(detail.status === 200, `${expertId} detail did not return 200`);
    assert(detail.body.role === role, `${expertId} role mismatch`);
    assert(detail.body.status === "completed", `${expertId} not completed`);
    assert(detail.body.duration_ms > 0, `${expertId} missing duration`);
    assert(detail.body.provider.provider === "claude-code-cli", `${expertId} missing provider`);
    assert(detail.body.provider.model === "deepseek-v4-flash[1M]", `${expertId} missing model`);
    assert(detail.body.provider.usage !== null, `${expertId} missing provider usage object`);
    assert(detail.body.evidence.length > 0, `${expertId} missing provider evidence`);
    assert(detail.body.notebook.available === false, `${expertId} should report notebook unavailable`);
    assert(detail.body.notebook.reason === "NOT_RECORDED", `${expertId} notebook reason should be NOT_RECORDED`);
    details[expertId] = detail.body;
  }

  await page.screenshot({ path: `${outputRoot}/ui3c-research-cockpit-desktop.png`, fullPage: true });
  return { expertList: expertList.body, details };
}

async function verifyFixtureBranches(browser, realDetail) {
  const notebookFixture = parseNotebookFixture();
  const context = await browser.newContext({ viewport: { width: 1280, height: 820 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  let fixtureRequestHit = false;

  await page.route(`**/api/projects/${slug}/research/experts/math.model_designer`, (route) => {
    fixtureRequestHit = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...realDetail,
        notebook: { available: true, artifact: "notebook-rendering.ipynb", reason: null },
        failure: {
          code: "PROVIDER_OUTPUT_INVALID",
          layer: "provider",
          message: "Fixture failure branch for StageFailurePanel.",
          retryable: true,
          request_id: "fixture-request-id",
          occurred_at: "2026-08-07T00:00:00Z",
        },
      }),
    });
  });
  await page.route(`**/api/projects/${slug}/research/experts/math.model_designer/notebook`, (route) => {
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(notebookFixture) });
  });

  await login(page, `/projects/${slug}/research`);
  await page.getByRole("heading", { name: "Research Cockpit", exact: true }).waitFor({ timeout: 30_000 });
  consoleErrors.length = 0;
  const modelDesignerCard = page.locator('ol[aria-label="Expert timeline"] > li:nth-child(2) > div');
  await modelDesignerCard.evaluate((element) => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
  });
  await page.getByText("Model Designer", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  const evidenceTabActive = await page.getByRole("button", { name: "Evidence", exact: true }).evaluate((button) =>
    button.getAttribute("class")?.includes("border-primary") ?? false,
  );
  const selectedExpertIsModelDesigner = await page.getByRole("heading", { name: "Model Designer", exact: true }).count() > 0;
  await page.locator('section[aria-labelledby="stage-failure-title"]').waitFor();
  const stageFailureCount = await page.locator('section[aria-labelledby="stage-failure-title"]').count();
  const stageFailureText = await page.locator('section[aria-labelledby="stage-failure-title"]').innerText();
  assert(stageFailureCount > 0, "fixture failure panel not rendered");
  assert(stageFailureText.includes("PROVIDER_OUTPUT_INVALID"), "fixture failure code not rendered");
  assert(stageFailureText.includes("fixture-request-id"), "fixture failure request id not rendered");
  await page.getByText("Open Execution Control").first().waitFor();
  await page.getByRole("button", { name: "Notebook", exact: true }).click();
  await page.getByText("UI-3C Notebook Fixture", { exact: true }).waitFor();
  await page.getByText("stream output from expert notebook").first().waitFor();
  await page.getByText("ValueError: fixture failure").first().waitFor();
  await page.locator('iframe[title="Sanitized notebook HTML output"]').waitFor();
  const scriptExecuted = await page.evaluate(() => Boolean(window.__minta_bad));
  const imageOutput = await page.locator('img[alt="Notebook output"]').count();
  await page.screenshot({ path: `${outputRoot}/ui3c-notebook-fixture.png`, fullPage: true });
  const text = await page.locator("main").innerText();
  await context.close();
  return {
    model_designer_fixture_request_hit: fixtureRequestHit,
    selected_expert_is_model_designer: selectedExpertIsModelDesigner,
    evidence_tab_active: evidenceTabActive,
    stage_failure_section_count: stageFailureCount,
    notebook_cells: notebookFixture.cells.length,
    markdown_katex_fixture: text.includes("UI-3C Notebook Fixture"),
    stream_output: text.includes("stream output from expert notebook"),
    execute_result: text.includes("selected_model"),
    image_output: imageOutput > 0,
    error_output: text.includes("ValueError: fixture failure"),
    html_sanitized: scriptExecuted === false,
    stage_failure_panel: stageFailureCount > 0,
    console_errors: consoleErrors,
  };
}

async function verifyMobile(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await login(page, `/projects/${slug}/research`);
  await page.getByRole("heading", { name: "Research Cockpit", exact: true }).waitFor({ timeout: 30_000 });
  consoleErrors.length = 0;
  const overflow = await page.locator("main").evaluate((main) => main.scrollWidth > main.clientWidth + 1);
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await page.getByText("Provider details", { exact: true }).first().waitFor();
  await page.screenshot({ path: `${outputRoot}/ui3c-research-cockpit-mobile.png`, fullPage: true });
  await context.close();
  return { overflow, console_errors: consoleErrors };
}

async function verifyCrossPageTrace(page, details) {
  const gates = (await api(page, `/api/projects/${slug}/gates`)).body.gates;
  const execution = (await api(page, `/api/projects/${slug}/execution/${runId}`)).body;
  const qa = (await api(page, `/api/projects/${slug}/qa`)).body;
  const runtime = (await api(page, `/api/projects/${slug}/runtime`)).body;
  const gatesByNumber = byId(gates, "gate_number");
  const arrivals = execution.artifact_arrivals;
  const gate1Hashes = new Set(gatesByNumber[1].references.map((reference) => reference.sha256).filter(Boolean));
  const gate2Options = gatesByNumber[2].options.map((option) => option.option_id).sort().join(",");
  const executionPlan = details["math.execution_engineer"].outputs.find((item) => item.artifact === "execution-plan");
  const qaOutput = details["math.scientific_validator"].outputs.find((item) => item.artifact === "validator-report");
  const paperInputQA = details["math.paper_synthesizer"].inputs.some((item) => item.artifact === "validator-report" || item.artifact === "scientific-qa-report");
  const paperOutput = details["math.paper_synthesizer"].outputs.find((item) => item.artifact === "paper-draft");

  return {
    problem_reframer_output_hash_matches_gate1:
      lineageHas(details["math.problem_reframer"], "assumptions", "2cefa95382c5b896fa6bf9e42e169ca91d818dca28794668c4c7cfbce5339f2d") &&
      gate1Hashes.has("2cefa95382c5b896fa6bf9e42e169ca91d818dca28794668c4c7cfbce5339f2d"),
    model_designer_candidates_match_gate2: gate2Options === "C1,C2,C3",
    human_selected_c2_visible: gatesByNumber[2].selected_model === "C2" && execution.authorization_binding.selected_model === "C2",
    execution_engineer_plan_hash_matches_execution:
      Boolean(executionPlan) && gatesByNumber[2].plan_hash === execution.authorization_binding.plan_hash,
    execution_engineer_script_hash_visible: Boolean(execution.authorization_binding.script_hash),
    scientific_validator_qa_artifact_matches_qa_page:
      Boolean(qaOutput) && qa.verdict === "PASSED" && qa.artifact === "scientific-qa-report.json",
    verdict_matches_server: runtime.qa.verdict === qa.verdict,
    paper_synthesizer_consumes_passed_qa: paperInputQA && qa.paper_eligible === true,
    paper_artifact_traceable:
      Boolean(paperOutput) && runtime.paper.available === true && arrivals.some((item) => item.name === "paper-draft.md"),
  };
}

mkdirSync(outputRoot, { recursive: true });
const runIndex = JSON.parse(readFileSync("E:/Minta/runs/index.json", "utf8"));
const protectedRunRoot = runIndex[slug].run_dir;
const protectedBefore = fileSnapshot(protectedRunRoot);
const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const writeRequests = [];
const consoleErrors = [];
page.on("request", (request) => {
  if (request.url().includes("/api/projects/") && request.method() !== "GET") {
    writeRequests.push({ method: request.method(), url: request.url() });
  }
});
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });

try {
  const realCockpit = await verifyRealCockpit(page);
  consoleErrors.length = 0;
  const crossPageTrace = await verifyCrossPageTrace(page, realCockpit.details);
  const fixtureBranches = await verifyFixtureBranches(browser, realCockpit.details["math.model_designer"]);
  const mobile = await verifyMobile(browser);
  const sse = await page.evaluate(async (id) => {
    const controller = new AbortController();
    const response = await fetch(`/api/runs/${id}/events`, { credentials: "include", signal: controller.signal });
    const reader = response.body?.getReader();
    const first = reader ? await reader.read() : { value: undefined };
    controller.abort();
    return { status: response.status, first: first.value ? new TextDecoder().decode(first.value) : "" };
  }, runId);
  const protectedAfter = fileSnapshot(protectedRunRoot);
  const authority = {
    frontend_sets_execution_status: writeRequests.some((request) => /execution/.test(request.url)),
    frontend_sets_qa_verdict: writeRequests.some((request) => /qa/.test(request.url)),
    frontend_advances_runtime: writeRequests.some((request) => /runtime/.test(request.url)),
  };
  const result = {
    implementation_scope: "UI-3C Expert Deep Integration",
    real_run: {
      slug,
      run_id: runId,
      experts: realCockpit.expertList.experts.length,
      completed_experts: realCockpit.expertList.experts.filter((expert) => expert.status === "completed").length,
      provider: "claude-code-cli",
      model: "deepseek-v4-flash[1M]",
      source_conflicts: realCockpit.expertList.source_conflicts.length,
      notebook: "NOT_RECORDED",
    },
    expert_details: Object.fromEntries(Object.entries(realCockpit.details).map(([expertId, detail]) => [expertId, {
      status: detail.status,
      duration_ms: detail.duration_ms,
      input_count: detail.inputs.length,
      output_count: detail.outputs.length,
      evidence_count: detail.evidence.length,
      usage_recorded: detail.provider.usage !== null,
      notebook_available: detail.notebook.available,
      notebook_reason: detail.notebook.reason,
      data_gaps: detail.data_gaps.map((gap) => gap.code),
      source_conflicts: detail.source_conflicts.length,
    }])),
    cross_page_trace: crossPageTrace,
    notebook_fixture: fixtureBranches,
    browser: {
      desktop_blank: false,
      mobile_overflow: mobile.overflow,
      console_errors: [...consoleErrors, ...mobile.console_errors, ...fixtureBranches.console_errors],
      sse_snapshot: sse.status === 200 && sse.first.includes("event: snapshot"),
    },
    authority,
    write_requests: writeRequests,
    protected_run: {
      files_before: Object.keys(protectedBefore).length,
      files_after: Object.keys(protectedAfter).length,
      hashes_identical: JSON.stringify(protectedBefore) === JSON.stringify(protectedAfter),
    },
  };
  writeFileSync(`${outputRoot}/UI-3C-expert-deep-integration.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await browser.close();
}
