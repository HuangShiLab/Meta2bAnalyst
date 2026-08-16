// Local E2E: upload a paper PDF through the real UI, wait for the proposed
// plan, screenshot the confirmation card. Requires backend (:8000, with LLM
// key) and frontend dev server (:5173) running. Not part of CI.
import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const SID = '7ada3f06-f4c3-429a-8416-d87204934f03';
const PDF = process.env.PAPER_PDF || new URL('../../../tmp/test_paper.pdf', import.meta.url).pathname;
const OUT = new URL('../screenshots/', import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const persisted = JSON.stringify({
  state: {
    sessionId: SID,
    analysisHistory: [],
    currentStep: 'agent',
    uploadedFiles: [], analysisResults: null, selectedSpecies: null,
    dataFormat: null, uploadFormat: 'tsv',
  },
  version: 0,
});

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript((p) => localStorage.setItem('meta2banalyst-session', p), persisted);
const page = await ctx.newPage();

await page.goto('http://localhost:5173/agent', { waitUntil: 'networkidle', timeout: 20000 });
await page.waitForTimeout(600);

// Upload via the hidden file input behind "Plan from paper"
await page.setInputFiles('input[type="file"][accept=".pdf"]', PDF);
console.log('uploaded paper, waiting for proposed plan (LLM latency)...');

// The confirmation card appears with a Confirm / execute action
await page.waitForSelector('text=/Proposed plan|确认|Confirm/i', { timeout: 240000 });
await page.waitForTimeout(1200);
await page.screenshot({ path: `${OUT}paper_plan_confirmation.png`, fullPage: true });
console.log('plan card rendered');

const body = await page.textContent('body');
console.log('shows unmatched analyses:', /not available|unmatched|cannot run/i.test(body || ''));

await browser.close();
console.log('E2E done ->', OUT);
