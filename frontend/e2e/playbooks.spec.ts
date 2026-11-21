import { test, expect } from '@playwright/test';

/**
 * Playbook picker UI chain: Agent page -> "Playbooks" button -> study-type
 * cards -> column-mapping view (auto-attach) -> Generate plan -> review plan
 * card -> Confirm & Run -> streamed execution finishes with zero failures.
 *
 * Runs against the live Docker stack with the Multi-omics demo dataset
 * (Huang mBio 261-sample set), which both bundled playbooks were validated on.
 * No LLM key is needed: playbook instantiation is deterministic.
 *
 *   E2E_BASE_URL=http://localhost:8080 npx playwright test e2e/playbooks.spec.ts --workers=1
 */

/** Sign in through the UI with the built-in classroom account. */
async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.locator('#username').fill('student01');
  await page.locator('#password').fill('Meta2b-2026');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
}

/** Load the multi-omics demo dataset and wait for the ready message. */
async function loadDemoMultiOmics(page: import('@playwright/test').Page) {
  await page.getByTestId('select-demo-dataset').click();
  await page.getByRole('option', { name: /^Multi-omics/ }).click();
  await expect(
    page.getByText(/Demo dataset "Multi-omics" is ready/)
  ).toBeVisible({ timeout: 120_000 });
}

test.describe('Playbook picker (live stack)', () => {
  test.describe.configure({ mode: 'serial' });

  test('cards -> mapping -> plan -> confirm -> execution completes', async ({ page }) => {
    test.setTimeout(600_000);
    await login(page);
    await page.goto('/agent');
    await loadDemoMultiOmics(page);

    // 1. Open the playbook dialog; both bundled study-type cards appear.
    await page.getByTestId('button-playbooks').click();
    await expect(page.getByTestId('playbook-card-case_control_16s')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('playbook-card-longitudinal_multiomics')).toBeVisible();

    // 2. Pick the 16S case-control playbook -> column-mapping view.
    await page.getByTestId('playbook-card-case_control_16s').click();
    await expect(page.getByTestId('button-instantiate-playbook')).toBeVisible({ timeout: 15_000 });
    // The demo session has metadata, so the no-metadata warning must not show.
    await expect(page.getByText(/no readable metadata yet/)).toHaveCount(0);

    // 3. Leave every role on auto-attach and generate the plan.
    const instantiateResp = page.waitForResponse(
      (r) => r.url().includes('/instantiate') && r.request().method() === 'POST',
      { timeout: 60_000 },
    );
    await page.getByTestId('button-instantiate-playbook').click();
    expect((await instantiateResp).status()).toBeLessThan(300);

    // 4. Plan card appears with the auto-attached column resolution note.
    await expect(
      page.getByText('Review the steps below, then confirm to run:')
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Column resolution:/)).toBeVisible();
    // Markdown renders the backticked names as code spans; assert the pieces.
    await expect(page.getByText('group_column').first()).toBeVisible();
    await expect(page.getByText('Group').first()).toBeVisible();

    // 5. Confirm & Run -> streamed execution finishes, zero failed steps.
    await page.getByRole('button', { name: /Confirm & Run/i }).click();
    const summary = page.getByText(/✅ \*\*Completed\*\*: \d+ steps \| ❌ \*\*Failed\*\*: \d+ steps/);
    await expect(summary).toBeVisible({ timeout: 480_000 });
    await expect(page.getByText(/\*\*Failed\*\*: 0 steps/)).toBeVisible();

    // 6. Chat input is usable again after the run.
    await expect(
      page.getByPlaceholder(/Describe your analysis goal/i)
    ).toBeEnabled();
  });

  test('explicit column mapping overrides auto-attach', async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);
    await page.goto('/agent');
    await loadDemoMultiOmics(page);

    await page.getByTestId('button-playbooks').click();
    await page.getByTestId('playbook-card-case_control_16s').click();
    await expect(page.getByTestId('map-group_column')).toBeVisible({ timeout: 15_000 });

    // Pick "Group" explicitly for the group_column role.
    await page.getByTestId('map-group_column').click();
    await page.getByRole('option', { name: 'Group', exact: true }).click();

    const instantiateResp = page.waitForResponse(
      (r) => r.url().includes('/instantiate') && r.request().method() === 'POST',
      { timeout: 60_000 },
    );
    await page.getByTestId('button-instantiate-playbook').click();
    const resp = await instantiateResp;
    expect(resp.status()).toBeLessThan(300);
    const body = await resp.json();
    // Response is flat: {plan, explanation, corrections}. The user-mapped
    // role must resolve to the chosen column inside the plan's params.
    const planText = JSON.stringify(body.plan ?? {});
    expect(planText).toContain('Group');

    await expect(
      page.getByText('Review the steps below, then confirm to run:')
    ).toBeVisible({ timeout: 30_000 });
  });
});
