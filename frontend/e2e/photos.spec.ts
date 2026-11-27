import { expect, test } from "@playwright/test";

import { FAKE_AUDIO, signupAndPickAudio } from "./helpers";

// 1×1 PNG (가상 사진)
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

test("검토 중 사진을 붙이고 지울 수 있고, 확정 뒤에는 보기만 한다", async ({ page }) => {
  await signupAndPickAudio(page);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  await expect(page.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });

  const photos = page.getByRole("region", { name: "사진" });
  await expect(photos.getByText(/위치 정보는 지우고 저장/)).toBeVisible();
  for (const name of ["a.png", "b.png"]) {
    await photos.getByText("사진 붙이기").locator("input").setInputFiles({ name, mimeType: "image/png", buffer: PNG });
    await expect(photos.getByRole("img")).toHaveCount(name === "a.png" ? 1 : 2);
  }
  await photos.getByRole("button", { name: "지우기" }).first().click();
  await expect(photos.getByRole("img")).toHaveCount(1);
  // 사진이 아닌 파일은 거절
  await photos.getByText("사진 붙이기").locator("input").setInputFiles(FAKE_AUDIO);
  await expect(photos.getByText("사진으로 읽을 수 없는 파일입니다")).toBeVisible();

  const accept = page.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await page.getByRole("button", { name: "확정하기" }).click();
  const confirmed = page.getByRole("region", { name: "사진" });
  await expect(confirmed.getByRole("img", { name: "기록 사진 1" })).toBeVisible();
  await expect(confirmed.getByText("사진 붙이기")).toHaveCount(0);
  const loaded = await confirmed.getByRole("img").evaluate((img: HTMLImageElement) => img.naturalWidth);
  expect(loaded).toBe(1); // 실제로 복호화된 이미지가 내려옴
});
