import { defineConfig, devices } from "@playwright/test";

// 백엔드·워커는 AI_PROVIDER=fake로 띄운다. 이미 떠 있는 서버는 재사용하므로 그 서버도 fake여야 한다.
const env = { ...process.env, AI_PROVIDER: "fake" } as Record<string, string>;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  globalSetup: "./e2e/global-setup.ts",
  use: { baseURL: "http://localhost:3100", ...devices["Pixel 7"] },
  webServer: [
    {
      command: "uv run uvicorn app.main:app --port 8001",
      cwd: "../backend",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: true,
      env,
    },
    { command: "pnpm dev", url: "http://localhost:3100", reuseExistingServer: true, timeout: 120_000 },
  ],
});
