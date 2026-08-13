import { test, expect } from '@playwright/test';

test.describe('Home Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display title and description', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Meta2bAnalyst' })).toBeVisible();
    await expect(page.getByText('2bRAD 工具群一站式统计分析平台')).toBeVisible();
  });

  test('should render all module cards', async ({ page }) => {
    await expect(page.locator('[data-testid="home-quick-actions"]')).toBeVisible();

    await expect(page.getByRole('heading', { name: '物种水平分析' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '功能基因分析' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '株水平分析' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '多组学整合' })).toBeVisible();
  });

  test('should navigate to upload via quick start button', async ({ page }) => {
    await page.getByTestId('btn-quick-start').click();
    await expect(page).toHaveURL(/.*\/upload/);
    await expect(page.getByTestId('upload-title')).toBeVisible();
  });

  test('should navigate to upload via sidebar', async ({ page }) => {
    await page.getByRole('link', { name: 'Upload' }).click();
    await expect(page).toHaveURL(/.*\/upload/);
  });

  test('should show supported format badges', async ({ page }) => {
    await expect(page.getByText('2bRAD-M', { exact: true })).toBeVisible();
    await expect(page.getByText('QIIME/BIOM', { exact: true })).toBeVisible();
    await expect(page.getByText('Mothur', { exact: true })).toBeVisible();
    await expect(page.getByText('TSV/CSV', { exact: true })).toBeVisible();
  });
});
