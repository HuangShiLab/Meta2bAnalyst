// CI smoke-screenshot script: renders every route against a built app
// (vite preview, no backend) and fails on uncaught page errors.
// Console errors (e.g. failed backend fetches) are logged but non-fatal,
// since CI runs without the API server.
//
// Usage:
//   npm run build && npm run preview &   # or let CI do it
//   SCREENSHOT_BASE_URL=http://localhost:4173 npm run screenshots:ci
import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const BASE = process.env.SCREENSHOT_BASE_URL || 'http://localhost:4173';
const OUT = new URL('../screenshots/ci/', import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const ROUTES = [
  ['home', '/'],
  ['upload', '/upload'],
  ['microbiome', '/microbiome'],
  ['multi-omics', '/multi-omics'],
  ['multi-site', '/multi-site'],
  ['agent', '/agent'],
  ['results', '/results'],
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 300)));
page.on('console', (m) => {
  if (m.type() === 'error') console.log('[console.error]', m.text().slice(0, 200));
});

let failed = false;
for (const [name, route] of ROUTES) {
  pageErrors.length = 0;
  try {
    await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
    const bodyLen = ((await page.textContent('body')) || '').trim().length;
    if (bodyLen < 20) {
      console.error(`FAIL ${route}: page body looks empty (${bodyLen} chars)`);
      failed = true;
    } else if (pageErrors.length) {
      console.error(`FAIL ${route}: uncaught page errors:\n  ${pageErrors.join('\n  ')}`);
      failed = true;
    } else {
      console.log(`OK   ${route} -> ${name}.png`);
    }
  } catch (e) {
    console.error(`FAIL ${route}: ${String(e).slice(0, 300)}`);
    failed = true;
  }
}

await browser.close();
console.log('screenshots ->', OUT);
if (failed) {
  console.error('SMOKE SCREENSHOTS FAILED');
  process.exit(1);
}
console.log('SMOKE SCREENSHOTS PASSED');
