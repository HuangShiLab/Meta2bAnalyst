import { test, expect } from '@playwright/test';

test.describe('Home Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display title and description', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Meta2bAnalyst' })).toBeVisible();
    await expect(page.getByText('One-stop Statistical Analysis Platform for 2bRAD Toolkit')).toBeVisible();
  });

  test('should render all module cards', async ({ page }) => {
    await expect(page.locator('[data-testid="home-quick-actions"]')).toBeVisible();

    await expect(page.getByRole('heading', { name: 'Species-Level Analysis' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Functional Gene Analysis' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Strain-Level Analysis' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Multi-Omics Integration' })).toBeVisible();
  });

  test('quick start navigates to upload', async ({ page }) => {
    await page.getByTestId('btn-quick-start').click();
    await expect(page).toHaveURL(/.*\/upload/);
  });
});
