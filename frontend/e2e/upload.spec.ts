import { test, expect } from '@playwright/test';

const LIVE = !!process.env.E2E_BASE_URL;

/** Sign in through the UI with the built-in classroom account. */
async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.locator('#username').fill('student01');
  await page.locator('#password').fill('Meta2b-2026');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
}

test.describe('Upload Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('should render upload page elements', async ({ page }) => {
    await expect(page.getByTestId('upload-title')).toBeVisible();
    await expect(page.getByTestId('upload-desc')).toBeVisible();
    await expect(page.getByTestId('upload-dropzone')).toBeVisible();
  });

  test('should select format from radio group', async ({ page }) => {
    // The radio input is sr-only; the visible card label forwards the click.
    await page.locator('label', { hasText: 'QIIME/BIOM' }).click();
    await expect(page.getByRole('radio', { name: 'QIIME/BIOM' })).toBeChecked();
  });

  test('should use example data and show files', async ({ page }) => {
    await page.getByTestId('btn-use-example').click();
    // Default format is TSV/CSV; its example set ships with the frontend.
    await expect(page.getByText('qiime_feature_table.tsv', { exact: true })).toBeVisible();
    await expect(page.getByText('qiime_metadata.csv', { exact: true })).toBeVisible();
    await expect(page.getByText('taxonomy.csv', { exact: true })).toBeVisible();
  });

  test('guest validation is rejected with a sign-in prompt', async ({ page }) => {
    test.skip(LIVE, 'guest case only runs against the backend-less preview');
  });

  test('should validate uploaded files (live stack, signed in)', async ({ page }) => {
    test.skip(!LIVE, 'needs the live backend: set E2E_BASE_URL=http://localhost:8080');
    await login(page);
    await page.goto('/upload');
    await page.getByTestId('btn-use-example').click();
    const validateBtn = page.getByTestId('btn-validate');
    await expect(validateBtn).toBeEnabled();
    await validateBtn.click();
    await expect(page.getByText(/Validation Success/i)).toBeVisible({ timeout: 30000 });
    await expect(page.getByText(/Session ID/i)).toBeVisible();
  });

  test('should proceed to inspection after upload (live stack)', async ({ page }) => {
    test.skip(!LIVE, 'needs the live backend: set E2E_BASE_URL=http://localhost:8080');
    await login(page);
    await page.goto('/upload');
    await page.getByTestId('btn-use-example').click();
    await page.getByTestId('btn-validate').click();
    await expect(page.getByText(/Validation Success/i)).toBeVisible({ timeout: 30000 });
    const proceed = page.getByTestId('btn-proceed-inspection');
    await expect(proceed).toBeEnabled();
    await proceed.click();
    await expect(page).toHaveURL(/.*\/inspection/);
  });
});
