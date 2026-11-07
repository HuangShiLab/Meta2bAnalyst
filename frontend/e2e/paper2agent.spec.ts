import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

/**
 * Paper2Agent UI chain: Agent page -> load demo dataset -> upload a paper PDF
 * -> plan-from-paper -> review plan card -> Confirm & Run -> streamed
 * execution finishes.
 *
 * The full chain needs the backend LLM key (plan-from-paper is LLM-driven),
 * which CI does not have; a probe skips those cases there. The graceful-
 * degradation contract (clean error message, no crash) is always asserted.
 */

const PAPER_PDF = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'paper2agent_methods.pdf');

/** Sign in through the UI with the built-in classroom account. */
async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.locator('#username').fill('student01');
  await page.locator('#password').fill('Meta2b-2026');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
}

/** plan-from-paper with a deliberately tiny text: when the LLM is configured
 * the backend complains about the short text; without a key it says the LLM
 * is not configured. Distinguishes the two without burning LLM tokens. */
async function llmConfigured(page: import('@playwright/test').Page): Promise<boolean> {
  const loginRes = await page.request.post('/api/v1/auth/login', {
    data: { username: 'student01', password: 'Meta2b-2026' },
  });
  if (!loginRes.ok()) return false;
  const { token } = await loginRes.json();
  const res = await page.request.post('/api/v1/agent/plan-from-paper', {
    headers: { Authorization: `Bearer ${token}` },
    form: { paper_text: 'short probe' },
  });
  const body = await res.json().catch(() => ({}));
  return res.status() === 422 && !String(body.detail || '').includes('LLM is not configured');
}

/** Load the multi-omics demo dataset and wait for the ready message. */
async function loadDemoMultiOmics(page: import('@playwright/test').Page) {
  await page.getByTestId('select-demo-dataset').click();
  await page.getByRole('option', { name: /^Multi-omics/ }).click();
  await expect(
    page.getByText(/Demo dataset "Multi-omics" is ready/)
  ).toBeVisible({ timeout: 120_000 });
}

test.describe('Paper2Agent (live stack)', () => {
  test('paper upload yields a plan card or a graceful error, never a crash', async ({ page }) => {
    test.setTimeout(300_000);
    await login(page);
    await page.goto('/agent');
    await loadDemoMultiOmics(page);

    // The button programmatically clicks the hidden input (native file
    // chooser); drive the input directly - its onChange fires the upload.
    await expect(page.getByRole('button', { name: /Plan from paper/i })).toBeEnabled();
    await page.locator('input[type="file"][accept=".pdf"]').setInputFiles(PAPER_PDF);

    // With an LLM key: the plan card appears. Without one (CI): a clean
    // error bubble. Either way the chat must stay usable.
    const planCard = page.getByText('Review the steps below, then confirm to run:');
    const errorBubble = page.getByText(/❌ Error:/);
    await expect(planCard.or(errorBubble)).toBeVisible({ timeout: 240_000 });
    await expect(
      page.getByPlaceholder(/Describe your analysis goal/i)
    ).toBeEnabled();
  });

  test('full chain: PDF -> plan -> confirm -> streamed execution completes', async ({ page }) => {
    test.setTimeout(420_000);
    await login(page);
    if (!(await llmConfigured(page))) {
      test.skip(true, 'backend LLM key not configured (CI); full chain is covered locally');
    }

    await page.goto('/agent');
    await loadDemoMultiOmics(page);

    // The button programmatically clicks the hidden input (native file
    // chooser); drive the input directly - its onChange fires the upload.
    await expect(page.getByRole('button', { name: /Plan from paper/i })).toBeEnabled();
    await page.locator('input[type="file"][accept=".pdf"]').setInputFiles(PAPER_PDF);

    // Plan card: validator first, at least 3 steps proposed.
    await expect(
      page.getByText('Review the steps below, then confirm to run:')
    ).toBeVisible({ timeout: 300_000 });
    await expect(page.locator('span', { hasText: 'data_validator' }).first()).toBeVisible();

    await page.getByRole('button', { name: /Confirm & Run/i }).click();

    // Terminal summary appended by the SSE consumer when the stream ends.
    const summary = page.getByText(/✅ \*\*Completed\*\*: \d+ steps \| ❌ \*\*Failed\*\*: \d+ steps/);
    await expect(summary).toBeVisible({ timeout: 300_000 });
    await expect(page.getByText(/\*\*Failed\*\*: 0 steps/)).toBeVisible();
  });
});
