import { expect, type Page } from "@playwright/test";

export const FAKE_AUDIO = { name: "sample.webm", mimeType: "audio/webm", buffer: Buffer.from("fake-audio") };

/** 새 계정으로 가입하고 수급자를 추가한 뒤, 녹음 화면에서 파일을 골라 둔다. */
export async function signupAndPickAudio(page: Page): Promise<void> {
  const loginId = `e2e_${Date.now().toString(36)}`;
  await page.goto("/signup");
  await page.getByLabel("아이디").fill(loginId);
  await page.getByLabel("비밀번호").fill("e2e-password-1");
  await page.getByLabel("표시 이름 (가명)").fill("테스트 요양보호사");
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page.getByRole("heading", { name: "수급자" })).toBeVisible();

  const name = `가상 어르신 ${loginId.slice(-4)}`;
  await page.getByLabel("수급자 추가 (가명)").fill(name);
  await page.getByRole("button", { name: "추가", exact: true }).click();
  await page.getByRole("link", { name }).click();
  await page.getByRole("link", { name: "오늘 방문 기록하기" }).click();

  const upload = page.getByRole("button", { name: "기록 올리기" });
  await expect(upload).toBeDisabled();
  await page.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await page.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await expect(upload).toBeEnabled();
}
