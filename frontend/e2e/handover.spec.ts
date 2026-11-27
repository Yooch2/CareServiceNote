import { expect, test, type Page } from "@playwright/test";

import { FAKE_AUDIO, signupAndPickAudio } from "./helpers";

async function confirmAll(page: Page) {
  await expect(page.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });
  const accept = page.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await page.getByRole("button", { name: "확정하기" }).click();
  await expect(page.getByText("AI 초안 그대로").first()).toBeVisible();
}

test("다음 방문에서 이전 확인 사항을 이어서 확인하고, 방문 전 확인·요약·검색에 반영된다", async ({ page }) => {
  // 첫 방문: '다음 확인' 항목이 생긴다
  await signupAndPickAudio(page);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  await confirmAll(page);
  await expect(page.getByText("아직 확인 전")).toBeVisible();

  // 방문 전 확인: 남은 확인 사항 1건
  await page.getByRole("link", { name: "‹ 기록 목록" }).click();
  const open = page.getByRole("region", { name: "남은 확인 사항" });
  await expect(open.getByText("1건")).toBeVisible();
  await expect(open.getByText("무릎 상태와 산책 의향 다시 확인")).toBeVisible();

  // 두 번째 방문: AI가 이전 확인 사항의 답을 근거와 함께 제안
  await page.getByRole("link", { name: "오늘 방문 기록하기" }).click();
  await page.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await page.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  const previous = page.getByRole("region", { name: "이전 확인 사항" });
  await expect(previous.getByText("AI가 찾은 답, 확인 필요")).toBeVisible({ timeout: 30_000 });
  await expect(previous.getByText("무릎은 아직 불편하다고 하심")).toBeVisible();
  await confirmAll(page);
  const checked = page.getByRole("region", { name: "확인한 이전 사항" });
  await expect(checked.getByText("무릎은 아직 불편하다고 하심")).toBeVisible();

  // 방문 전 확인: 완료율, 최근 확인 결과
  await page.getByRole("link", { name: "‹ 기록 목록" }).click();
  const followup = page.getByRole("region", { name: "후속 확인" });
  await expect(followup.getByText(/확인할 일 2건 중/)).toBeVisible();
  await expect(followup.getByText("무릎은 아직 불편하다고 하심")).toBeVisible();

  // AI 인계 요약: 문장마다 근거 링크
  await page.getByRole("button", { name: "요약 만들기" }).click();
  await expect(page.getByRole("link", { name: /^근거 \d{4}-\d{2}-\d{2}$/ }).first()).toBeVisible();

  // 검색: 확인 결과까지 찾는다
  await page.getByLabel("검색어").fill("무릎");
  await page.getByRole("button", { name: "찾기" }).click();
  const results = page.getByRole("region", { name: "기록 검색" });
  await expect(results.getByText("확인 결과").first()).toBeVisible();
  await expect(results.locator("mark").first()).toHaveText("무릎");
});
