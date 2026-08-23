import { chromium } from 'playwright';
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const base = 'http://localhost:3290';
const slug = 'mm2-real-acceptance-teaching-methods';

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const loginRes = await page.evaluate(async () => {
  const res = await fetch('http://127.0.0.1:8772/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'uitest', password: 'uitest123' }),
  });
  return res.json();
});
const token = loginRes.accessToken;

await page.goto(base + '/#/login', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.evaluate((t) => {
  localStorage.setItem('minta_token', t);
  localStorage.setItem('minta_user', 'uitest');
}, token);
await page.reload({ waitUntil: 'domcontentloaded' });
await page.goto(base + '/#/projects/' + slug + '/overview', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(3000);

const styles = await page.evaluate(() => {
  const el = document.querySelector('[aria-label="Expert status"] li > div');
  if (!el) return null;
  const cs = getComputedStyle(el);
  return {
    borderColor: cs.borderColor,
    borderWidth: cs.borderWidth,
    borderStyle: cs.borderStyle,
    backgroundColor: cs.backgroundColor,
    boxShadow: cs.boxShadow,
  };
});
console.log('Expert card styles:', styles);

const rootStyles = await page.evaluate(() => {
  return {
    mintaBorder: getComputedStyle(document.documentElement).getPropertyValue('--minta-border'),
    mintaCanvas: getComputedStyle(document.documentElement).getPropertyValue('--minta-canvas'),
  };
});
console.log('Root vars:', rootStyles);

await browser.close();
