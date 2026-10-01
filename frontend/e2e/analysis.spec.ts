import { test, expect } from '@playwright/test';

/**
 * Microbiome Analysis page (formerly "Analysis Species").
 * Rendering specs run anywhere; the run-analysis smoke needs the live
 * backend (E2E_BASE_URL) and a session with data.
 */
test.describe('Microbiome Analysis Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/microbiome');
  });

  test('should render page and tabs', async ({ page }) => {
    await expect(page.getByTestId('analysis-title')).toBeVisible();
    await expect(page.getByTestId('tab-community')).toBeVisible();
    await expect(page.getByTestId('tab-differential')).toBeVisible();
    await expect(page.getByTestId('tab-network')).toBeVisible();
    await expect(page.getByTestId('tab-advanced')).toBeVisible();
  });

  test('community tab shows analysis parameters', async ({ page }) => {
    await expect(page.getByText('Analysis Parameters')).toBeVisible();
    await expect(page.getByRole('radio', { name: /alpha diversity/i })).toBeChecked();
  });

  test('should switch to differential tab and show parameters', async ({ page }) => {
    await page.getByTestId('tab-differential').click();
    await expect(page.getByText('Differential Parameters')).toBeVisible();
    await expect(page.getByRole('combobox').first()).toBeVisible();
  });

  test('should switch to network tab and show parameters', async ({ page }) => {
    await page.getByTestId('tab-network').click();
    await expect(page.getByText('Network & Function Parameters')).toBeVisible();
    await expect(page.getByRole('radio', { name: /correlation network/i })).toBeChecked();
  });

  test('should switch to advanced tab and show parameters', async ({ page }) => {
    await page.getByTestId('tab-advanced').click();
    await expect(page.getByText('Advanced Parameters')).toBeVisible();
    await expect(page.getByRole('radio', { name: /dimensionality reduction/i })).toBeChecked();
  });

  test('run without a session shows an explanatory alert, not silence', async ({ page }) => {
    // Guests without uploaded data must get feedback when clicking Run.
    await page.getByRole('button', { name: /run analysis/i }).first().click();
    await expect(page.getByText(/no active session/i)).toBeVisible();
  });
});
