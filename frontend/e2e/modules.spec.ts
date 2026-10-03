import { test, expect, request, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * Full module regression against the live Docker stack.
 *
 * Covers every analysis module reachable from the four analysis pages:
 *   Microbiome (20) · Multi-omics (13) · Multi-site (4) · Strain (4)
 *
 * Each test drives the real UI: pick the module, click its Run button,
 * require a 2xx POST, wait for the spinner to clear, and require that no
 * error alert appears. Run with:
 *
 *   E2E_BASE_URL=http://localhost:8080 npx playwright test e2e/modules.spec.ts --workers=1
 *
 * Sessions are provisioned over the API in beforeAll with the repo's
 * example data (Huang mBio 261-sample set + strain2bscan 30-sample set).
 */

const LIVE = !!process.env.E2E_BASE_URL;
const BASE = process.env.E2E_BASE_URL || 'http://localhost:8080';
const API = `${BASE}/api/v1`;
// Playwright runs specs from the frontend/ directory; the repo root is one up.
const REPO = path.resolve(process.cwd(), '..');
const SAMPLE = {
  metadata: path.join(REPO, 'sample_data/microbiome/Matched_metadata_261.tsv'),
  featureTable: path.join(REPO, 'sample_data/microbiome/Matched_microbes_abd_261.tsv'),
  metabolome: path.join(REPO, 'sample_data/metabolome/Matched_metabolites_abd_261.txt'),
  strain: path.join(REPO, 'backend/examples/strain2bscan_output.csv'),
};

const RUN_TIMEOUT = 240_000;

let token = '';
let mainSession = '';
let strainSession = '';

async function upload(
  ctx: Awaited<ReturnType<typeof request.newContext>>,
  sid: string,
  fileType: string,
  name: string,
  buffer: Buffer,
) {
  const res = await ctx.post(`${API}/sessions/${sid}/upload`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: { file: { name, mimeType: 'application/octet-stream', buffer }, file_type: fileType },
  });
  expect(res.status(), `upload ${fileType}`).toBeLessThan(300);
}

/** Inject auth token + active session before the app boots. */
async function openPage(page: Page, sid: string, route: string) {
  await page.addInitScript(
    ([t, s]) => {
      localStorage.setItem('token', t);
      localStorage.setItem(
        'meta2banalyst-auth',
        JSON.stringify({ state: { token: t, user: null }, version: 0 }),
      );
      localStorage.setItem(
        'meta2banalyst-session',
        JSON.stringify({ state: { sessionId: s }, version: 0 }),
      );
    },
    [token, sid],
  );
  page.on('pageerror', (e) => {
    throw new Error(`pageerror on ${route}: ${e.message.slice(0, 200)}`);
  });
  await page.goto(route, { waitUntil: 'networkidle' });
}

/**
 * Click a Run button inside the active tab panel and assert the analysis
 * succeeds: 2xx POST, spinner clears, no error alert.
 */
async function runModule(page: Page, runLabel: RegExp, urlHint: string) {
  const panel = page.locator('[role="tabpanel"][data-state="active"]').first();
  const btn = panel.getByRole('button', { name: runLabel }).first();
  await expect(btn).toBeVisible({ timeout: 15_000 });
  await expect(btn).toBeEnabled();
  const respPromise = page.waitForResponse(
    (r) => r.url().includes(urlHint) && r.request().method() === 'POST',
    { timeout: RUN_TIMEOUT },
  );
  // Debug aid: log every API POST so failures show what actually fired.
  const dbg = (r: import('@playwright/test').Response) => {
    if (r.request().method() === 'POST' && r.url().includes('/api/')) {
      console.log(`[api-post] ${r.status()} ${r.url()}`);
    }
  };
  page.on('response', dbg);
  await btn.click();
  const resp = await respPromise.finally(() => page.off('response', dbg));
  expect(resp.status(), `POST ${resp.url()}`).toBeLessThan(300);
  await expect(page.locator('.animate-spin')).toHaveCount(0, { timeout: RUN_TIMEOUT });
  await page.waitForTimeout(500);
  const alerts = (await page.locator('[role="alert"]').allTextContents()).join(' ');
  expect(alerts, `error alert after ${String(runLabel)}`).not.toMatch(/fail|error/i);
}

test.describe('Module regression (live stack)', () => {
  test.skip(!LIVE, 'needs the live backend: set E2E_BASE_URL=http://localhost:8080');
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(Number(process.env.E2E_TEST_TIMEOUT || RUN_TIMEOUT + 60_000));

  test.beforeAll(async () => {
    const ctx = await request.newContext({ baseURL: BASE });
    const login = await ctx.post(`${API}/auth/login`, {
      data: { username: 'student01', password: 'Meta2b-2026' },
    });
    expect(login.status()).toBeLessThan(300);
    token = (await login.json()).token;
    const auth = { Authorization: `Bearer ${token}` };

    // Main session: microbiome + metabolome + metadata (Huang mBio set).
    const s1 = await ctx.post(`${API}/sessions`, { headers: auth, data: { name: 'e2e-modules' } });
    mainSession = (await s1.json()).id;
    await upload(ctx, mainSession, 'metadata', 'Matched_metadata_261.tsv', fs.readFileSync(SAMPLE.metadata));
    await upload(ctx, mainSession, 'feature_table', 'Matched_microbes_abd_261.tsv', fs.readFileSync(SAMPLE.featureTable));
    await upload(ctx, mainSession, 'metabolome', 'Matched_metabolites_abd_261.txt', fs.readFileSync(SAMPLE.metabolome));

    // Strain session: strain2bscan output + a synthetic two-group metadata.
    const s2 = await ctx.post(`${API}/sessions`, { headers: auth, data: { name: 'e2e-modules-strain' } });
    strainSession = (await s2.json()).id;
    const strainCsv = fs.readFileSync(SAMPLE.strain, 'utf8');
    const sampleIds = [...new Set(
      strainCsv.trim().split('\n').slice(1).map((line) => line.split(',')[0]),
    )];
    const metaCsv = 'sample_id,Group\n' +
      sampleIds.map((id, i) => `${id},${i % 2 === 0 ? 'Case' : 'Control'}`).join('\n') + '\n';
    await upload(ctx, strainSession, 'metadata', 'strain_metadata.csv', Buffer.from(metaCsv));
    await upload(ctx, strainSession, 'strain', 'strain2bscan_output.csv', fs.readFileSync(SAMPLE.strain));

    await ctx.dispose();
  });

  // ------------------------------------------------------------------
  // Microbiome page — 20 modules
  // ------------------------------------------------------------------
  test.describe('Microbiome page', () => {
    const community = [
      'Alpha Diversity', 'Beta Diversity', 'Composition', 'PERMANOVA',
      'Rarefaction', 'Taxonomy Bar', 'Core Microbiome',
    ];
    for (const label of community) {
      test(`community: ${label}`, async ({ page }) => {
        await openPage(page, mainSession, '/microbiome');
        await page.getByTestId('tab-community').click();
        await page.locator('[role="tabpanel"][data-state="active"] label', { hasText: label }).first().click();
        await runModule(page, /run analysis/i, '/analyze/');
      });
    }

    const diffMethods = [
      'Wilcoxon rank-sum', 'LEfSe (LDA Effect Size)',
      'ANCOM-BC (composition-aware)', 'MaAsLin3 (multivariate)',
    ];
    for (const method of diffMethods) {
      test(`differential: ${method}`, async ({ page }) => {
        await openPage(page, mainSession, '/microbiome');
        await page.getByTestId('tab-differential').click();
        const panel = page.locator('[role="tabpanel"][data-state="active"]').first();
        await panel.getByRole('combobox').first().click();
        await page.getByRole('option', { name: method }).click();
        // Pairwise methods on a >2-level column need an explicit contrast;
        // pick the first two levels when the selectors appear.
        const refSelect = page.getByTestId('select-diff-reference');
        if (await refSelect.isVisible().catch(() => false)) {
          await refSelect.click();
          await page.getByRole('option').first().click();
          await page.getByTestId('select-diff-comparison').click();
          await page.getByRole('option').first().click();
        }
        await runModule(page, /run analysis/i, '/analyze/');
      });
    }

    // PICRUSt2 functional prediction is intentionally rejected by the
    // backend (_guard_unvalidated: mock reference database) — not tested.
    for (const label of ['Correlation Network', 'KEGG Pathway Analysis']) {
      test(`network: ${label}`, async ({ page }) => {
        await openPage(page, mainSession, '/microbiome');
        await page.getByTestId('tab-network').click();
        await page.locator('[role="tabpanel"][data-state="active"] label', { hasText: label }).first().click();
        await runModule(page, /run analysis/i, '/analyze/');
      });
    }

    const advanced = [
      'Dimensionality Reduction', 'Hierarchical Clustering', 'Source Tracking (FEAST)',
      'ALDEx2', 'Songbird', 'WGCNA', 'Enterotype',
    ];
    for (const label of advanced) {
      test(`advanced: ${label}`, async ({ page }) => {
        await openPage(page, mainSession, '/microbiome');
        await page.getByTestId('tab-advanced').click();
        await page.locator('[role="tabpanel"][data-state="active"] label', { hasText: label }).first().click();
        await runModule(page, /run analysis/i, '/analyze/');
      });
    }
  });

  // ------------------------------------------------------------------
  // Multi-omics page — 13 modules (each has a dedicated run button)
  //
  // The page gates its tabs behind its own paired-upload flow (component
  // state `uploaded`), so each test loads the built-in Huang mBio example
  // set through the UI first — this also exercises that upload path.
  // ------------------------------------------------------------------
  test.describe('Multi-omics page', () => {
    async function prepareMultiOmics(page: Page) {
      await openPage(page, mainSession, '/multi-omics');
      await page.getByRole('button', { name: /load example data/i }).click();
      const start = page.getByRole('button', { name: /start multi-omics analysis/i });
      await expect(start).toBeEnabled({ timeout: 30_000 });
      await start.click();
      await expect(
        page.getByRole('tab', { name: /individual omics/i })
      ).toBeVisible({ timeout: 120_000 });
    }

    const tabs: Record<string, RegExp[]> = {
      'Individual Omics': [
        /^Run PCoA$/, /^Run PCA$/, /^Run PERMANOVA$/,
        /^Run Metabolome Markers$/, /^Run Microbiome Markers$/,
      ],
      Integration: [
        /^Run Procrustes$/, /^Run Mantel$/, /^Run Sparse CCA$/,
        /^Run RDA$/, /^Run O2PLS$/, /^Run MOFA\+$/, /^Run DIABLO$/,
      ],
      'Feature-level': [/^Run Heatmap$/],
    };
    for (const [tab, buttons] of Object.entries(tabs)) {
      for (const runLabel of buttons) {
        test(`${tab} / ${String(runLabel)}`, async ({ page }) => {
          await prepareMultiOmics(page);
          await page.getByRole('tab', { name: new RegExp(tab, 'i') }).click();
          await runModule(page, runLabel, '/analyze/');
        });
      }
    }
  });

  // ------------------------------------------------------------------
  // Multi-site page — 4 modules
  // ------------------------------------------------------------------
  test.describe('Multi-site page', () => {
    const tabs = ['tab-comparison', 'tab-markers', 'tab-temporal', 'tab-network'];
    for (const tabId of tabs) {
      test(`${tabId}`, async ({ page }) => {
        await openPage(page, mainSession, '/multi-site');
        await page.getByTestId(tabId).click();
        await runModule(page, /run analysis/i, '/api/');
      });
    }
  });

  // ------------------------------------------------------------------
  // Strain page — 4 modules (strain2bscan session)
  // ------------------------------------------------------------------
  test.describe('Strain page', () => {
    for (const tab of ['Composition', 'Diversity', 'Differential', 'Network']) {
      test(`${tab}`, async ({ page }) => {
        await openPage(page, strainSession, '/strain');
        await page.getByRole('tab', { name: new RegExp(`^${tab}$`, 'i') }).click();
        await runModule(page, /run analysis/i, '/strain');
      });
    }
  });
});
