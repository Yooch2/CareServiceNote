import { expect, test, type Page } from "@playwright/test";

import { FAKE_AUDIO, PASSWORD, setupCaregiver, uniqueId } from "./helpers";

async function login(page: Page, loginId: string) {
  await page.goto("/login");
  await page.getByLabel("아이디").fill(loginId);
  await page.getByLabel("비밀번호").fill(PASSWORD);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).not.toHaveURL(/login/);
}

test("방문 시작·종료 → 기관 담당자가 하루 요약 승인·우려 안내 → 보호자는 범위 안 요약과 안내만, 업무 메시지는 직원만", async ({
  page,
  browser,
}) => {
  const { recipientName, manager } = await setupCaregiver(page);
  await page.goto("/");
  await page.getByRole("link", { name: recipientName }).click();

  // 요양보호사: 방문 시작 → 기록·확정 → 방문 종료, 업무 메시지, 우려
  await page.getByRole("button", { name: "방문 시작" }).click();
  await expect(page.getByText("방문 중")).toBeVisible();
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
  await page.getByRole("button", { name: "방문 종료" }).click();
  await expect(page.getByRole("button", { name: "방문 시작" })).toBeVisible();
  await page.getByLabel("메시지", { exact: true }).fill("현관 비밀번호가 바뀌었다고 하십니다");
  await page.getByRole("button", { name: "보내기" }).click();
  await page.getByRole("button", { name: "센터에 우려 알리기" }).click();
  await page.getByLabel("걱정되는 점").fill("기침을 자주 하셨어요");
  await page.getByRole("button", { name: "센터에 보내기" }).click();

  // 기관 담당자: 공유 동의·보호자 초대(말씀만)는 API로 준비
  const boss = await (await browser.newContext()).newPage();
  await login(boss, manager);
  const recipients = await (await boss.request.get("/api/recipients")).json();
  const rid = recipients[0].id as string;
  await boss.request.post(`/api/recipients/${rid}/consents`, {
    data: { kind: "guardian_share", granted_on: new Date().toLocaleDateString("sv-SE") },
  });
  const { code } = await (
    await boss.request.post("/api/org/invites", { data: { role: "guardian", recipient_id: rid, categories: ["remark"] } })
  ).json();
  const family = await (await browser.newContext()).newPage();
  await family.goto("/signup");
  await family.getByLabel("초대 코드", { exact: true }).fill(code);
  await family.getByLabel("아이디").fill(uniqueId("fam"));
  await family.getByLabel("비밀번호").fill(PASSWORD);
  await family.getByLabel("표시 이름 (가명)").fill("테스트 보호자");
  await family.getByRole("button", { name: "가입하기" }).click();
  await expect(family).toHaveURL(/\/family$/);
  await expect(family.getByText("센터가 확인한 하루 요약")).toHaveCount(0); // 승인 전

  // 기관 담당자: 업무 메시지 확인, 하루 요약 만들기·승인
  await boss.goto("/");
  await boss.getByRole("link", { name: recipientName }).click();
  await expect(boss.getByText("현관 비밀번호가 바뀌었다고 하십니다")).toBeVisible();
  await boss.getByRole("link", { name: /확정$/ }).first().click(); // 지난 기록의 확정 기록
  const summary = boss.getByRole("region", { name: "보호자 하루 요약" });
  await summary.getByRole("button", { name: "요약 만들기" }).click();
  await expect(summary.getByText("승인 전")).toBeVisible();
  await summary.getByRole("button", { name: "승인하고 보호자에게 공유" }).click();
  await expect(summary.getByText("보호자에게 공유 중")).toBeVisible();

  // 기관 담당자: 우려 처리 + 보호자 안내
  await boss.goto("/center");
  const inbox = boss.getByRole("region", { name: "알림" });
  await inbox.getByLabel("보호자에게 보낼 안내 (선택)").fill("내일 병원 진료를 예약했습니다.");
  await inbox.getByLabel(/테스트 보호자/).check();
  await inbox.getByRole("button", { name: "조치함" }).click();
  await expect(inbox.getByText("처리할 알림이 없습니다.")).toBeVisible();

  // 보호자: 방문 시각, 범위 안 요약(말씀), 안내문만
  await family.reload();
  await expect(family.getByText(/오늘 .* 방문 시작 · .* 종료/)).toBeVisible();
  await expect(family.getByText("내일 병원 진료를 예약했습니다.")).toBeVisible();
  await expect(family.getByText("센터가 확인한 하루 요약")).toBeVisible();
  await expect(family.getByText("기침을 자주 하셨어요")).toHaveCount(0);
  await expect(family.getByText("현관 비밀번호")).toHaveCount(0);
  await expect(family.getByText("점심을 반 정도 드심")).toHaveCount(0);
});
