import { chromium } from 'playwright';
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const base = 'http://localhost:8772';
const slug = 'mm2-real-acceptance-teaching-methods';
const outDir = 'C:/Users/Lenovo/Documents/Codex/2026-08-06/mathmodelagent-main-zip-kimi-k3-ui/work';

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

await page.goto(base + '/#/projects/' + slug + '/overview', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.locator('input[type="text"]').first().fill('uitest');
await page.locator('input[type="password"]').fill('uitest123');
await page.locator('button[type="submit"]').click();
await page.waitForURL('**/#/projects/' + slug + '/overview');

async function shot(path, filename) {
  await page.goto(base + '/#' + path, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: outDir + '/' + filename, fullPage: false });
  const text = await page.evaluate(() => document.body.innerText);
  return text;
}

try {
  const overviewText = await shot('/projects/' + slug + '/overview', 'overview-v3.png');
  console.log('OVERVIEW_TEXT_START');
  console.log(overviewText.slice(0, 1500));
  console.log('OVERVIEW_TEXT_END');

  const researchText = await shot('/projects/' + slug + '/research', 'research-v3.png');
  console.log('RESEARCH_TEXT_START');
  console.log(researchText.slice(0, 1500));
  console.log('RESEARCH_TEXT_END');

  const idleText = await shot('/projects/idle-test-project/overview', 'idle-v3.png');
  console.log('IDLE_TEXT_START');
  console.log(idleText.slice(0, 1000));
  console.log('IDLE_TEXT_END');
} catch (e) {
  console.error('ERROR:', e.message);
} finally {
  await browser.close();
}

