import { defineConfig, devices } from "@playwright/test";

// 백엔드·워커는 AI_PROVIDER=fake로 띄운다. 이미 떠 있는 서버는 재사용하므로 그 서버도 fake여야 한다.
// 테스트마다 같은 IP(127.0.0.1)로 센터를 새로 만들어서 IP별 센터 만들기 제한을 올려 둔다
const env = { ...process.env, AI_PROVIDER: "fake", SIGNUP_MAX_PER_IP_PER_HOUR: "10000" } as Record<string, string>;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  // CI에서는 실패했을 때 올릴 HTML 보고서도 만든다
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
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
