import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const BASE = 'http://localhost:5173';
const OUT = new URL('./screenshots/', import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const pages = [
  ['/', 'home'],
  ['/upload', 'upload'],
  ['/microbiome', 'microbiome'],
  ['/multi-omics', 'multi-omics'],
  ['/multi-site', 'multi-site'],
  ['/agent', 'agent'],
  ['/results', 'results'],
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console] ${page.url()} :: ${m.text().slice(0, 200)}`); });
page.on('pageerror', (e) => errors.push(`[pageerror] ${page.url()} :: ${String(e).slice(0, 200)}`));

for (const [route, name] of pages) {
  try {
    await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
    console.log(`OK  ${name}  <- ${route}`);
  } catch (e) {
    console.log(`FAIL ${name} <- ${route}: ${e.message.split('\n')[0]}`);
  }
}
if (errors.length) {
  console.log('\n--- console/page errors ---');
  for (const e of errors) console.log(e);
}
await browser.close();
