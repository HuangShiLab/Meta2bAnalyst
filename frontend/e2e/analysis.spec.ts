import { test, expect } from '@playwright/test';

test.describe('Analysis Species Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/analysis-species');
  });

  test('should render page and tabs', async ({ page }) => {
    await expect(page.getByTestId('analysis-title')).toBeVisible();
    await expect(page.getByTestId('tab-community')).toBeVisible();
    await expect(page.getByTestId('tab-differential')).toBeVisible();
    await expect(page.getByTestId('tab-cluster')).toBeVisible();
    await expect(page.getByTestId('tab-ml')).toBeVisible();
    await expect(page.getByTestId('tab-function')).toBeVisible();
  });

  test('should switch to differential tab and show parameters', async ({ page }) => {
    await page.getByTestId('tab-differential').click();
    await expect(page.getByText('Differential Parameters')).toBeVisible();
    await expect(page.getByRole('combobox').first()).toBeVisible();
  });

  test('should switch to cluster tab and toggle heatmap/network', async ({ page }) => {
    await page.getByTestId('tab-cluster').click();
    await expect(page.getByText('Clustering Parameters')).toBeVisible();

    await page.getByRole('radio', { name: 'Network' }).check();
    await expect(page.getByRole('radio', { name: 'Network' })).toBeChecked();
  });

  test('should switch to ml tab and show parameters', async ({ page }) => {
    await page.getByTestId('tab-ml').click();
    await expect(page.getByText('Machine Learning Parameters')).toBeVisible();
  });

  test('should show function prediction placeholder', async ({ page }) => {
    await page.getByTestId('tab-function').click();
    await expect(page.getByText('Function prediction analysis is coming soon')).toBeVisible();
  });
});