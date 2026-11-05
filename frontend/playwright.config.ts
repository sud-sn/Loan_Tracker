import { defineConfig, devices } from "@playwright/test";

// End-to-end tests in English and Tamil on a laptop screen (the main way the app is used), a large
// monitor, a tablet and a phone (360 px).
// Expects the API on :8000 and `vite preview` on :4173 (see the e2e job in .github/workflows/ci.yml).
export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
    viewport: { width: 360, height: 780 },
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "laptop", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 820, height: 1180 } } },
    { name: "phone", use: { ...devices["Desktop Chrome"], viewport: { width: 360, height: 780 } } },
  ],
});
