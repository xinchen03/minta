import { chromium } from "playwright";

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const base = "http://localhost:8772";
const slug = "mm2-real-acceptance-teaching-methods";
const output = "C:/Users/Lenovo/Documents/Codex/2026-08-06/new-chat-4/work";

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

await page.goto(`${base}/#/projects/${slug}/overview`, { waitUntil: "networkidle" });
await page.locator('input[type="text"]').first().fill("uitest");
await page.locator('input[type="password"]').fill("uitest123");
await page.locator('button[type="submit"]').click();
await page.waitForURL(`**/#/projects/${slug}/overview`);
await page.waitForFunction(() => !document.querySelector('input[type="password"]'));

async function open(path) {
  await page.goto(`${base}/#${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
}

await open(`/projects/${slug}/overview`);
await page.screenshot({ path: `${output}/overview-1440x900.png` });

const overview = await page.evaluate(() => {
  const button = Array.from(document.querySelectorAll("button")).find((el) => el.textContent?.includes("Continue"));
  const card = document.querySelector('[aria-label="Expert status"] li > div');
  const title = document.querySelector("h1");
  const metadata = document.querySelector(".minta-metadata");
  if (!button || !card || !title || !metadata) throw new Error("Visual gate target missing");
  const buttonStyle = getComputedStyle(button);
  const cardStyle = getComputedStyle(card);
  const bodyStyle = getComputedStyle(document.body);
  const titleStyle = getComputedStyle(title);
  const metadataStyle = getComputedStyle(metadata);
  const rawText = document.body.innerText;
  const blackBorders = Array.from(document.querySelectorAll("*"))
    .filter((el) => {
      const style = getComputedStyle(el);
      return style.borderStyle !== "none" && style.borderWidth !== "0px" && style.borderColor === "rgb(0, 0, 0)";
    }).length;
  return {
    button: {
      backgroundColor: buttonStyle.backgroundColor,
      color: buttonStyle.color,
      borderRadius: buttonStyle.borderRadius,
      fontFamily: buttonStyle.fontFamily,
    },
    card: {
      borderColor: cardStyle.borderColor,
      borderRadius: cardStyle.borderRadius,
      backgroundColor: cardStyle.backgroundColor,
      boxShadow: cardStyle.boxShadow,
    },
    fonts: {
      body: bodyStyle.fontFamily,
      title: titleStyle.fontFamily,
      metadata: metadataStyle.fontFamily,
    },
    blackBorders,
    rawEnumVisible: rawText.includes("view_paper"),
    completedIdleContradiction: rawText.includes("运行完成") && rawText.includes(" idle"),
    authStorageKeys: Object.keys(localStorage).filter((key) => key.includes("token") || key.includes("api_key")),
  };
});

await open(`/projects/${slug}/research`);
await page.screenshot({ path: `${output}/research-1440x900.png` });

await page.setViewportSize({ width: 1024, height: 768 });
await open(`/projects/${slug}/overview`);
await page.screenshot({ path: `${output}/overview-1024x768.png` });

const layout = await page.evaluate(() => {
  const viewport = { width: innerWidth, height: innerHeight };
  const overflow = Array.from(document.querySelectorAll("main *"))
    .filter((el) => {
      const rect = el.getBoundingClientRect();
      return rect.right > viewport.width + 1 || rect.left < -1;
    })
    .slice(0, 10)
    .map((el) => ({ tag: el.tagName, className: el.className, text: el.textContent?.slice(0, 40) }));
  const cards = Array.from(document.querySelectorAll('[aria-label="Expert status"] li > div, [aria-label="Gate status"] li > div'));
  let overlaps = 0;
  for (let i = 0; i < cards.length; i += 1) {
    const a = cards[i].getBoundingClientRect();
    for (let j = i + 1; j < cards.length; j += 1) {
      const b = cards[j].getBoundingClientRect();
      if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) overlaps += 1;
    }
  }
  return { overflow, overlaps };
});

console.log(JSON.stringify({ overview, layout }, null, 2));
await browser.close();
