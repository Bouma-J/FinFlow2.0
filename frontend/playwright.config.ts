import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

const localEdge = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const edgeExecutable =
  process.env.PLAYWRIGHT_EXECUTABLE_PATH ||
  (process.platform === "win32" && existsSync(localEdge)
    ? localEdge
    : undefined);

export default defineConfig({
  testDir: "./e2e",
  // FinFlow pages make several concurrent API calls; a serial browser run is
  // more reliable on the Windows Edge fallback used by the local recipe setup.
  fullyParallel: false,
  timeout: 60_000,
  reporter: "list",
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    headless: true,
    launchOptions: edgeExecutable ? { executablePath: edgeExecutable } : {},
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173/login",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
