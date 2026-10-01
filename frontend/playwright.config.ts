import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Meta2bAnalyst frontend E2E tests.
 *
 * Default: runs against `vite preview` (built app, no backend) for
 * render-only specs. Set E2E_BASE_URL=http://localhost:8080 to run the
 * full suite — including backend-dependent flows (login, upload, analysis)
 * — against the live Docker stack.
 */
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:4173';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  ...(process.env.E2E_BASE_URL
    ? {}
    : {
        webServer: {
          command: 'npm run preview',
          url: 'http://localhost:4173',
          reuseExistingServer: !process.env.CI,
        },
      }),
});
