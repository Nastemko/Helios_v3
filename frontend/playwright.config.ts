import { defineConfig, devices } from '@playwright/test';

/**
 * Every API call in the suite is stubbed with page.route, so these tests need
 * neither the backend nor the Ithaca/Aeneas checkpoints. Only the Vite dev
 * server has to be up, and Playwright starts it here.
 */
// Read through globalThis so the config typechecks without @types/node, which
// the app is otherwise free of.
const isCI = Boolean((globalThis as { process?: { env: Record<string, string | undefined> } })
  .process?.env.CI);

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  reporter: isCI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !isCI,
    timeout: 120_000,
  },
});
