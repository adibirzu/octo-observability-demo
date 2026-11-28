/**
 * Dedicated Playwright configuration for deterministic checkout receipt visual regression tests.
 *
 * Runs offline against local shop template assets with intercepted routes, fixed viewports,
 * zero external/provider requests, single worker, and zero retries.
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/visual',
  testMatch: 'checkout-receipt.visual.spec.ts',
  snapshotPathTemplate: '{testDir}/{testFileName}-snapshots/{arg}-{projectName}-{platform}{ext}',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  outputDir: 'test-results/visual',
  preserveOutput: 'failures-only',

  expect: {
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
      maxDiffPixels: 0,
      threshold: 0.1,
    },
  },

  use: {
    baseURL: 'http://shop.example.test',
    colorScheme: 'dark',
    deviceScaleFactor: 1,
    locale: 'en-US',
    timezoneId: 'UTC',
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'off',
    actionTimeout: 15_000,
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        deviceScaleFactor: 1,
      },
    },
  ],
});
