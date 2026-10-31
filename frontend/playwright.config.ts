import { defineConfig, devices } from "@playwright/test";

// Smoke test against the Vite dev server (which proxies /api to the backend; set DEMOBOT_API).
// Start the backend first: `make api` (port 8000), or set DEMOBOT_API for another port.
const PORT = Number(process.env.E2E_PORT ?? 5174);

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  outputDir: "./test-results/artifacts",
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    // Playwright's bundled Chromium cannot decode H.264 (display.mp4 stays black). Set PW_CHROME
    // to a Chrome / Chrome-for-Testing binary to see the video.
    launchOptions: { executablePath: process.env.PW_CHROME || undefined, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
  projects: [{ name: "chromium", use: { viewport: { width: 1920, height: 1080 } } }],
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
