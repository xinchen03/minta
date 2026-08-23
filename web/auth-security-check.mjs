import { chromium, request as playwrightRequest } from "playwright";

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const output = "E:/Minta/Codex/2026-08-06/mathmodelagent-main-zip-kimi-k3-ui/outputs";

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const result = {};

try {
  const deepLink = `${base}/#/projects/${slug}/overview`;
  await page.goto(deepLink, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.evaluate(() => {
    localStorage.setItem("minta_token", "legacy-placeholder");
    localStorage.setItem("minta_api_key", "legacy-placeholder");
    sessionStorage.setItem("minta_token", "legacy-placeholder");
    sessionStorage.setItem("minta_api_key", "legacy-placeholder");
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator('input[type="text"]').first().fill("uitest");
  await page.locator('input[type="password"]').fill("uitest123");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(`**/#/projects/${slug}/overview`, { timeout: 30_000 });
  await page.locator("h1").waitFor({ timeout: 30_000 });

  const authState = await page.evaluate(() => ({
    hash: window.location.hash,
    documentCookie: document.cookie,
    localSensitive: ["minta_token", "minta_api_key"].filter((key) => localStorage.getItem(key) !== null),
    sessionSensitive: ["minta_token", "minta_api_key"].filter((key) => sessionStorage.getItem(key) !== null),
  }));
  const sessionCookie = (await context.cookies(base)).find((cookie) => cookie.name === "minta_session");
  result.authentication = {
    deepLinkPreserved: authState.hash === `#/projects/${slug}/overview`,
    documentCookieCannotReadSession: !authState.documentCookie.includes("minta_session"),
    localSensitive: authState.localSensitive,
    sessionSensitive: authState.sessionSensitive,
    cookie: sessionCookie ? {
      httpOnly: sessionCookie.httpOnly,
      secure: sessionCookie.secure,
      sameSite: sessionCookie.sameSite,
      domain: sessionCookie.domain,
      path: sessionCookie.path,
    } : null,
  };

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("h1").waitFor({ timeout: 30_000 });
  result.authentication.reloadRestored = await page.locator('input[type="password"]').count() === 0;

  const runtime = await page.evaluate(async (projectSlug) => {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectSlug)}/runtime`, { credentials: "include" });
    return { status: response.status, body: await response.json() };
  }, slug);
  const sse = await page.evaluate(async (runId) => {
    const controller = new AbortController();
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/events`, {
      credentials: "include",
      headers: { Accept: "text/event-stream" },
      signal: controller.signal,
    });
    const reader = response.body?.getReader();
    const first = reader ? await reader.read() : { done: true, value: undefined };
    controller.abort();
    return {
      status: response.status,
      firstEvent: first.value ? new TextDecoder().decode(first.value).slice(0, 120) : "",
    };
  }, runtime.body.active_run_id);
  result.researchRuntime = {
    apiStatus: runtime.status,
    projectStatus: runtime.body.status,
    runId: runtime.body.active_run_id,
    sseStatus: sse.status,
    sseSnapshotReceived: sse.firstEvent.includes("event: snapshot"),
  };

  await page.screenshot({ path: `${output}/AUTH-SECURITY-overview-1440x900.png` });
  await page.goto(`${base}/#/projects/${slug}/research`, { waitUntil: "domcontentloaded" });
  await page.locator("h1").waitFor({ timeout: 30_000 });
  result.researchCockpitVisible = (await page.locator("body").innerText()).includes("Research Cockpit");
  await page.screenshot({ path: `${output}/AUTH-SECURITY-research-1440x900.png` });

  await page.goto(`${base}/#/`, { waitUntil: "domcontentloaded" });
  await page.getByRole("link", { name: "打开 Minta Research 项目列表" }).waitFor({ timeout: 30_000 });
  const rootText = await page.locator("body").innerText();
  result.originalMinta = {
    rootKnowledgeBase: /个人上下文层|Personal Context Layer/.test(rootText),
    researchEntryVisible: rootText.includes("Minta Research"),
  };
  await page.screenshot({ path: `${output}/AUTH-SECURITY-root-entry-1440x900.png` });

  const contexts = await page.evaluate(async () => {
    const response = await fetch("/api/contextObjects", { credentials: "include" });
    return response.json();
  });
  if (contexts[0]?.title) {
    const card = page.locator("article").filter({ hasText: contexts[0].title }).first();
    await card.scrollIntoViewIfNeeded();
    await card.click();
    const detailTitle = page.locator("h2").filter({ hasText: contexts[0].title });
    await detailTitle.waitFor({ timeout: 10_000 });
    result.originalMinta.contextDetail = await detailTitle.isVisible();
    await page.locator("div.fixed.inset-0").click({ position: { x: 5, y: 5 } });
  } else {
    result.originalMinta.contextDetail = false;
  }

  await page.getByRole("button", { name: /技能库|Skills Library/ }).first().click();
  result.originalMinta.skillsPage = /技能|Skills/.test(await page.locator("body").innerText());
  await page.getByRole("button", { name: /收件箱|Inbox/ }).first().click();
  result.originalMinta.inboxPage = /收件箱|Inbox/.test(await page.locator("body").innerText());

  await page.getByRole("link", { name: "打开 Minta Research 项目列表" }).click();
  await page.waitForURL("**/#/projects");
  await page.locator("h1").filter({ hasText: "研究项目" }).waitFor({ timeout: 30_000 });
  const projectCard = page.locator("article").filter({ hasText: slug });
  result.projectDiscovery = {
    projectListRoute: page.url().endsWith("/#/projects"),
    realProjectListed: await projectCard.count() >= 1,
  };
  await page.screenshot({ path: `${output}/AUTH-SECURITY-projects-1440x900.png` });

  const oldCookieValue = sessionCookie?.value;
  await page.goto(`${base}/#/`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /退出|Exit/ }).click();
  await page.locator('input[type="password"]').waitFor({ timeout: 30_000 });
  result.authentication.logoutShowsLogin = true;
  result.authentication.cookieCleared = !(await context.cookies(base)).some((cookie) => cookie.name === "minta_session");

  if (oldCookieValue) {
    const rawContext = await playwrightRequest.newContext({
      baseURL: base,
      extraHTTPHeaders: { Cookie: `minta_session=${oldCookieValue}` },
    });
    const invalidated = await rawContext.get("/api/auth/session");
    result.authentication.oldCookieStatus = invalidated.status();
    await rawContext.dispose();
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify(result, null, 2));
