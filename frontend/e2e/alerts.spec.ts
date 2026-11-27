import { expect, test, type Page } from "@playwright/test";

import { FAKE_AUDIO, PASSWORD, setupCaregiver } from "./helpers";

/** 녹음 화면에서 올리고 AI 항목(오늘 상태 포함)을 모두 확인해 확정한다 */
async function recordVisit(page: Page) {
  await page.getByRole("link", { name: "오늘 방문 기록하기" }).click();
  await page.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await page.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  await expect(page.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });
  // AI가 제안한 오늘 상태(식사량 절반)와 불편 부위
  const state = page.getByRole("region", { name: "오늘 상태" });
  await expect(state.getByLabel("식사량")).toHaveValue("2");
  await expect(page.getByText("무릎 불편").first()).toBeVisible();
  const accept = page.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await page.getByRole("button", { name: "확정하기" }).click();
  await expect(page.getByText("식사량 절반").filter({ visible: true })).toBeVisible();
  await page.getByRole("link", { name: "‹ 기록 목록" }).click();
}

test("같은 부위 불편이 두 번 확정되면 알림 → 긴급 우려 → 기관 담당자가 인박스에서 처리", async ({ page, browser }) => {
  const { recipientName, manager } = await setupCaregiver(page);
  await page.goto("/");
  await page.getByRole("link", { name: recipientName }).click();

  await recordVisit(page);
  await expect(page.getByRole("region", { name: "변화 알림" })).toHaveCount(0);
  await recordVisit(page);

  const alerts = page.getByRole("region", { name: "변화 알림" });
  await expect(alerts.getByText("무릎 불편 반복")).toBeVisible();
  await expect(alerts.getByRole("link")).toHaveCount(2); // 두 방문의 근거
  await expect(page.getByRole("region", { name: "식사량과 기분" })).toBeVisible();

  await page.getByRole("button", { name: "센터에 우려 알리기" }).click();
  await expect(page.getByText(/응급 상황이면 먼저 119/)).toBeVisible();
  await page.getByLabel("걱정되는 점").fill("숨이 차 보이셨어요");
  await page.getByRole("button", { name: "센터에 보내기" }).click();
  await expect(alerts.getByText("긴급 우려")).toBeVisible();

  // 기관 담당자
  const boss = await (await browser.newContext()).newPage();
  await boss.goto("/login");
  await boss.getByLabel("아이디").fill(manager);
  await boss.getByLabel("비밀번호").fill(PASSWORD);
  await boss.getByRole("button", { name: "로그인" }).click();
  await expect(boss.getByText("알림 2건")).toBeVisible();
  await boss.getByRole("link", { name: /센터 관리/ }).click();
  const inbox = boss.getByRole("region", { name: "알림" });
  await expect(inbox.getByText("미처리 2건")).toBeVisible();
  await inbox.getByLabel("처리 메모 (선택)").first().fill("보호자와 통화, 병원 예약");
  await inbox.getByRole("button", { name: "조치함" }).first().click();
  await expect(inbox.getByText("미처리 1건")).toBeVisible();
  await inbox.getByRole("button", { name: "오탐" }).click();
  await expect(inbox.getByText("처리할 알림이 없습니다.")).toBeVisible();
  await inbox.getByText("최근 처리한 알림").click();
  await expect(inbox.getByText(/보호자와 통화, 병원 예약/)).toBeVisible();

  await page.reload();
  await expect(page.getByRole("region", { name: "변화 알림" })).toHaveCount(0);
});
