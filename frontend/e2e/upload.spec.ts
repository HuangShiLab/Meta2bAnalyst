import { test, expect } from '@playwright/test';

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
    await page.getByRole('radio', { name: 'TSV/CSV' }).check();
    await expect(page.getByRole('radio', { name: 'TSV/CSV' })).toBeChecked();
  });

  test('should use example data and show files', async ({ page }) => {
    await page.getByTestId('btn-use-example').click();
    await expect(page.getByText('feature_table.csv', { exact: true })).toBeVisible();
    await expect(page.getByText('metadata.csv', { exact: true })).toBeVisible();
  });

  test('should validate uploaded files', async ({ page }) => {
    await page.getByTestId('btn-use-example').click();
    const validateBtn = page.getByTestId('btn-validate');
    await expect(validateBtn).toBeEnabled();
    await validateBtn.click();
    await expect(validateBtn).toBeDisabled();
    await expect(page.getByText('数据验证通过！')).toBeVisible({ timeout: 5000 });
  });

  test('should proceed to inspection after upload', async ({ page }) => {
    await page.getByTestId('btn-use-example').click();
    await expect(page.getByTestId('btn-proceed-inspection')).toBeEnabled();
    await page.getByTestId('btn-proceed-inspection').click();
    await expect(page).toHaveURL(/.*\/inspection/);
  });
});
