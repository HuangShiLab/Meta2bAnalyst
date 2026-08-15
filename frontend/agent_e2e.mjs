import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';

const API = 'http://localhost:8000/api/v1';
const SID = '7ada3f06-f4c3-429a-8416-d87204934f03';
const OUT = new URL('./screenshots/', import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

// Pull real job results to build a realistic analysisHistory.
async function jobResult(id) {
  const r = await fetch(`${API}/sessions/${SID}/jobs/${id}/result`);
  if (!r.ok) throw new Error(`job ${id}: ${r.status}`);
  return (await r.json()).result_data;
}

const alpha = await jobResult(588);
const permanova = await jobResult(592);

const history = [
  { id: 'j588', type: 'alpha', label: 'Alpha Diversity', timestamp: new Date().toISOString(), status: 'success', statistics: alpha },
  { id: 'j592', type: 'permanova', label: 'PERMANOVA', timestamp: new Date().toISOString(), status: 'success', statistics: permanova },
];

const persisted = JSON.stringify({
  state: {
    sessionId: SID,
    analysisHistory: history,
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

page.on('console', (m) => { if (m.type() === 'error') console.log('[console.error]', m.text().slice(0, 200)); });

// 1. AgentChat (interpret tab) with real session + results
await page.goto('http://localhost:5173/agent', { waitUntil: 'networkidle', timeout: 20000 });
await page.waitForTimeout(600);
await page.screenshot({ path: `${OUT}agent_e2e_loaded.png` });

// Find the interpret-mode chat input (AgentChat) and ask a disease question
const interpretBtn = page.getByRole('button', { name: /interpret/i });
if (await interpretBtn.count()) await interpretBtn.first().click();
await page.waitForTimeout(400);

const chatInput = page.getByPlaceholder(/Ask about your data/i);
const usable = await chatInput.count();
console.log('chat input visible:', usable);

if (usable) {
  await chatInput.fill('What diseases are these species related to?');
  await chatInput.press('Enter');
  // interpret-full + render can take a few seconds
  await page.waitForTimeout(12000);
  await page.screenshot({ path: `${OUT}agent_chat_disease_answer.png`, fullPage: true });
  const body = await page.textContent('body');
  const hasDisease = /disease|DISEASE|CROHN|COLORECTAL|IBD/i.test(body || '');
  console.log('disease answer rendered:', hasDisease);
}

await browser.close();
console.log('E2E done ->', OUT);
