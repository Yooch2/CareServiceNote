import { expect, test, type Page } from "@playwright/test";

import { FAKE_AUDIO, PASSWORD, setupCaregiver } from "./helpers";

async function recordVisit(page: Page) {
  await page.getByRole("link", { name: "오늘 방문 기록하기" }).click();
  await page.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await page.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  await expect(page.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });
  const accept = page.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await page.getByRole("button", { name: "확정하기" }).click();
  await expect(page.getByText("센터 확인 전입니다.").filter({ visible: true })).toBeVisible();
  await page.getByRole("link", { name: "‹ 기록 목록" }).filter({ visible: true }).click();
}

test("정정하면 이력이 남고 변화 알림이 다시 평가되며, 기관 담당자는 이력과 내보내기를 본다", async ({ page, browser }) => {
  const { recipientName, manager } = await setupCaregiver(page);
  await page.goto("/");
  await page.getByRole("link", { name: recipientName }).click();
  await recordVisit(page);
  await recordVisit(page);
  await expect(page.getByRole("region", { name: "변화 알림" }).getByText("무릎 불편 반복")).toBeVisible();

  // 첫 방문 기록(목록의 두 번째)을 허리로 정정
  await page.getByRole("link", { name: /확정$/ }).nth(1).click();
  const remark = page.getByRole("region", { name: "말씀" });
  await remark.getByRole("button", { name: "정정" }).first().click();
  await remark.getByLabel("내용").fill("허리가 좀 불편하다");
  await remark.getByLabel("불편을 말한 부위").selectOption("back");
  const save = remark.getByRole("button", { name: "정정 저장" });
  await expect(save).toBeDisabled(); // 사유 필수
  await remark.getByLabel("정정 사유 (필수)").fill("녹음을 다시 들어 보니 허리였음");
  await save.click();
  await expect(remark.getByText("허리가 좀 불편하다")).toBeVisible();
  await expect(remark.getByText("정정됨")).toBeVisible();
  await remark.getByText("정정 이력 1건").click();
  await expect(remark.getByText("녹음을 다시 들어 보니 허리였음")).toBeVisible();

  // 무릎 반복 조건이 사라져 알림이 닫힘
  await page.getByRole("link", { name: "‹ 기록 목록" }).filter({ visible: true }).click();
  await page.reload();
  await expect(page.getByRole("region", { name: "변화 알림" })).toHaveCount(0);

  // 기관 담당자: 이력과 내보내기
  const boss = await (await browser.newContext()).newPage();
  await boss.goto("/login");
  await boss.getByLabel("아이디").fill(manager);
  await boss.getByLabel("비밀번호").fill(PASSWORD);
  await boss.getByRole("button", { name: "로그인" }).click();
  await boss.getByRole("link", { name: recipientName }).click();
  await boss.getByRole("link", { name: /담당 배정 · 동의 · 보호자 관리/ }).click();
  const history = boss.getByRole("region", { name: "기록 내보내기와 이력" });
  await expect(history.getByText("정정", { exact: true })).toBeVisible();
  const download = boss.waitForEvent("download");
  await history.getByRole("link", { name: "확정 기록 내보내기 (CSV)" }).click();
  expect((await download).suggestedFilename()).toMatch(/^records-[0-9a-f-]{36}\.csv$/);
  await expect(history.getByText("내보내기", { exact: true })).toBeVisible();
});
