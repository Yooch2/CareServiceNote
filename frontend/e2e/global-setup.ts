import { spawn } from "node:child_process";

/** fake AI 워커를 띄우고, 테스트가 끝나면 종료한다. */
export default function globalSetup() {
  const worker = spawn("uv", ["run", "python", "-m", "app.worker"], {
    cwd: "../backend",
    env: { ...process.env, AI_PROVIDER: "fake" },
    stdio: "ignore",
  });
  return () => {
    worker.kill();
  };
}
