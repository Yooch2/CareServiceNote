import { expect, test } from "@playwright/test";

import { signupAndPickAudio } from "./helpers";

test("가입 → 수급자 추가 → 업로드 → 검토 → 확정", async ({ page }) => {
  await signupAndPickAudio(page);
  await page.getByRole("button", { name: "기록 올리기" }).click();

  await expect(page).toHaveURL(/\/records\/[0-9a-f-]{36}$/);
  await expect(page.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/언급 없음: .*배변/)).toBeVisible();
  await expect(page.getByText("AI 초안, 확인 필요").first()).toBeVisible();

  // 근거를 누르면 전사문 구간이 강조된다
  await page.getByRole("button", { name: /근거/ }).first().click();
  await expect(page.locator('[aria-current="true"]')).toHaveCount(1);

  // 하나는 고쳐서 확인, 나머지는 그대로 확인
  const confirm = page.getByRole("button", { name: "확정하기" });
  await expect(confirm).toBeDisabled();
  await page.getByRole("button", { name: "수정" }).first().click();
  await page.getByLabel("내용").first().fill("오른쪽 무릎 불편 호소");
  await page.getByRole("button", { name: "저장" }).click();
  const accept = page.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await expect(page.getByText("모든 AI 항목을 확인했습니다")).toBeVisible();
  await confirm.click();

  await expect(page.getByText("AI 초안 수정")).toBeVisible();
  await expect(page.getByText("AI 초안 그대로").first()).toBeVisible();
  await expect(page.getByText("오른쪽 무릎 불편 호소")).toBeVisible();
});
