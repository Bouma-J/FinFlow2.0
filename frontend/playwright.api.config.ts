import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

const localEdge = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const edgeExecutable =
  process.env.PLAYWRIGHT_EXECUTABLE_PATH ||
  (process.platform === "win32" && existsSync(localEdge)
    ? localEdge
    : undefined);

export default defineConfig({
  testDir: "./e2e-api",
  outputDir: process.env.FINFLOW_API_TEST_OUTPUT_DIR || "./test-results-api",
  fullyParallel: false,
  reporter: "list",
  timeout: 180_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.FINFLOW_API_BASE_URL || "http://127.0.0.1:5174",
    browserName: "chromium",
    headless: true,
    launchOptions: edgeExecutable ? { executablePath: edgeExecutable } : {},
    trace: "retain-on-failure",
  },
});
