import { chromium } from "playwright";

const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const outputRoot = "C:/Users/Lenovo/Documents/Codex/2026-08-07/files-mentioned-by-the-user-min/work";
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

async function login(page, target) {
  await page.goto(`${base}/#${target}`, { waitUntil: "domcontentloaded" });
  const password = page.locator('input[type="password"]');
  if (await password.count()) {
    await page.locator('input[type="text"]').first().fill("uitest");
    await password.fill("uitest123");
    await page.locator('button[type="submit"]').click();
  }
  await page.waitForURL(`**/#${target}`, { timeout: 30_000 });
}

async function verifyViewport(browser, viewport, label) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const writeRequests = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/api/projects/")) {
      writeRequests.push({ method: request.method(), url: request.url() });
    }
  });

  const gatesPath = `/projects/${slug}/gates`;
  await login(page, gatesPath);
  await page.getByRole("heading", { name: "Gate 审阅" }).waitFor();
  const overviewText = (await page.locator("body").innerText()).trim();
  const gateLinks = page.locator(`a[href^="#/projects/${slug}/gates/"]`);
  const hrefs = await gateLinks.evaluateAll((links) => [...new Set(links.map((link) => link.getAttribute("href")))].filter(Boolean));
  if (hrefs.length !== 4) throw new Error(`Expected 4 unique Gate detail links, got ${hrefs.length}`);

  const overflowOverview = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (!overviewText || overflowOverview) throw new Error(`${label} Gate overview blank or overflowing`);
  await page.screenshot({ path: `${outputRoot}/ui2a-gates-${label}.png`, fullPage: true });

  const details = [];
  for (const href of hrefs) {
    await page.goto(`${base}/${href}`, { waitUntil: "domcontentloaded" });
    await page.locator("h1").waitFor();
    const text = (await page.locator("body").innerText()).trim();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    if (!text || overflow || text.includes("Gate 详情不可用")) {
      throw new Error(`${label} failed Gate detail ${href}`);
    }
    details.push({ href, title: await page.locator("h1").innerText(), blank: false, overflow });
  }

  await page.goto(`${base}/#/projects/${slug}/gates/MM2-REAL-02-G2-V8`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Model Authorization" }).waitFor();
  const disabledActions = await page.locator('button:disabled').filter({ hasText: /接受|授权|修改|讨论|拒绝/ }).count();
  const sourceGapVisible = await page.getByText("源 Gate 快照未记录 Effects Diff。").count();
  const selectedModelVisible = await page.getByText("C2", { exact: true }).count();
  if (disabledActions !== 5 || !sourceGapVisible || !selectedModelVisible) {
    throw new Error(`${label} Gate 2 read-only contract was not visible`);
  }
  await page.screenshot({ path: `${outputRoot}/ui2a-gate2-${label}.png`, fullPage: true });

  await page.goto(`${base}/#/projects/${slug}/gates/not-a-gate`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Gate 详情不可用" }).waitFor();
  const invalidRouteBlank = !(await page.locator("body").innerText()).trim();
  if (invalidRouteBlank) throw new Error(`${label} invalid Gate route rendered blank`);

  await context.close();
  return {
    label,
    overview: { gateLinks: hrefs.length, blank: false, overflow: overflowOverview },
    details,
    gate2: { disabledActions, sourceGapVisible: Boolean(sourceGapVisible), selectedModelVisible: Boolean(selectedModelVisible) },
    invalidGateRoute: "explicit_error",
    writeRequests,
  };
}

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  const desktop = await verifyViewport(browser, { width: 1440, height: 900 }, "desktop");
  const mobile = await verifyViewport(browser, { width: 390, height: 844 }, "mobile");
  console.log(JSON.stringify({ desktop, mobile }, null, 2));
} finally {
  await browser.close();
}
