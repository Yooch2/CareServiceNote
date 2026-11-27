import { expect, test, type Browser, type Page } from "@playwright/test";

import { FAKE_AUDIO, PASSWORD, uniqueId } from "./helpers";

async function signupPage(browser: Browser, fill: (page: Page) => Promise<void>): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/signup");
  await fill(page);
  await page.getByRole("button", { name: "가입하기" }).click();
  return page;
}

async function basics(page: Page, loginId: string, name: string) {
  await page.getByLabel("아이디").fill(loginId);
  await page.getByLabel("비밀번호").fill(PASSWORD);
  await page.getByLabel("표시 이름 (가명)").fill(name);
}

async function readCode(page: Page): Promise<string> {
  // 숨겨진 이전 화면(Activity)에 남은 코드는 건너뛴다
  const shown = page.getByText(/^[A-Z2-9]{5}-[A-Z2-9]{5}$/).filter({ visible: true });
  await expect(shown).toBeVisible();
  return (await shown.textContent()) ?? "";
}

test("센터 만들기 → 동의·초대·배정 → 요양보호사 기록 → 센터 확인 서명 → 보호자는 열람 범위만, 연결 해제 시 차단", async ({
  browser,
}) => {
  const id = uniqueId("r");
  const recipient = `가상 어르신 ${id.slice(-4)}`;

  // 기관 담당자: 센터를 만들고 수급자 추가
  const manager = await signupPage(browser, async (p) => {
    await p.getByText("센터 만들기").click();
    await p.getByLabel("센터 이름 (가명)").fill("테스트 센터");
    await basics(p, `${id}_m`, "테스트 담당자");
  });
  await expect(manager.getByRole("link", { name: "센터 관리" })).toBeVisible();
  await manager.getByLabel("수급자 추가 (가명)").fill(recipient);
  await manager.getByRole("button", { name: "추가", exact: true }).click();
  await expect(manager.getByText("담당 없음")).toBeVisible();

  // 동의 두 가지 기록, 보호자 초대(말씀만)
  await manager.getByRole("link", { name: recipient }).click();
  await manager.getByRole("link", { name: /담당 배정 · 동의 · 보호자 관리/ }).click();
  // 하나 기록하고 목록이 다시 그려진 뒤 다음 것을 누른다
  for (let i = 1; i <= 2; i++) {
    await manager.getByRole("button", { name: "동의 기록" }).first().click();
    await expect(manager.getByText(/받음$/)).toHaveCount(i);
  }
  await manager.getByRole("button", { name: "보호자 초대 코드 만들기" }).click();
  const guardianCode = await readCode(manager);

  // 요양보호사 초대 코드
  await manager.getByRole("link", { name: "‹ 방문 전 확인" }).click();
  await manager.getByRole("link", { name: "‹ 수급자 목록" }).click();
  await manager.getByRole("link", { name: "센터 관리" }).click();
  await manager.getByRole("button", { name: "요양보호사 초대 코드 만들기" }).click();
  const carerCode = await readCode(manager);

  // 요양보호사: 초대 코드로 가입, 아직 배정 전
  const carer = await signupPage(browser, async (p) => {
    await p.getByLabel("초대 코드", { exact: true }).fill(carerCode.toLowerCase());
    await basics(p, `${id}_c`, "테스트 요양보호사");
  });
  await expect(carer.getByText("배정된 수급자가 없습니다")).toBeVisible();

  // 기관 담당자: 배정
  await manager.goto("/");
  await manager.getByRole("link", { name: recipient }).click();
  await manager.getByRole("link", { name: /담당 배정 · 동의 · 보호자 관리/ }).click();
  await manager.getByRole("button", { name: "배정" }).click();
  await expect(manager.getByText("테스트 요양보호사").first()).toBeVisible();

  // 요양보호사: 기록하고 확정
  await carer.reload();
  await carer.getByRole("link", { name: recipient }).click();
  await carer.getByRole("link", { name: "오늘 방문 기록하기" }).click();
  await carer.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await carer.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await carer.getByRole("button", { name: "기록 올리기" }).click();
  await expect(carer.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });
  const accept = carer.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await carer.getByRole("button", { name: "확정하기" }).click();
  await expect(carer.getByText("센터 확인 전입니다.")).toBeVisible();

  // 기관 담당자: 확인 대기 → 서명
  await manager.goto("/");
  await expect(manager.getByText("확인 대기 1건")).toBeVisible();
  await manager.getByRole("link", { name: "센터 관리" }).click();
  await manager.getByRole("region", { name: "확인 대기" }).getByRole("link").click();
  await manager.getByRole("button", { name: /센터 확인 서명/ }).click();
  await expect(manager.getByText("센터 확인", { exact: true })).toBeVisible();
  await carer.reload();
  await expect(carer.getByText("센터 확인", { exact: true })).toBeVisible();

  // 보호자: 말씀만 보이고 관찰·다음 확인은 안 보인다
  const family = await signupPage(browser, async (p) => {
    await p.getByLabel("초대 코드", { exact: true }).fill(guardianCode);
    await basics(p, `${id}_f`, "테스트 보호자");
  });
  await expect(family).toHaveURL(/\/family$/);
  await expect(family.getByRole("heading", { name: recipient })).toBeVisible();
  await expect(family.getByText("오른쪽 무릎이 좀 불편하다")).toBeVisible();
  await expect(family.getByText("점심을 반 정도 드심")).toHaveCount(0);
  await expect(family.getByText("무릎 상태와 산책 의향 다시 확인")).toHaveCount(0);

  // 기관 담당자가 연결을 해제하면 바로 막힌다
  await manager.goto("/");
  await manager.getByRole("link", { name: recipient }).click();
  await manager.getByRole("link", { name: /담당 배정 · 동의 · 보호자 관리/ }).click();
  await manager.getByRole("button", { name: "연결 해제" }).click();
  await expect(manager.getByRole("button", { name: "다시 연결" })).toBeVisible();
  await family.reload();
  await expect(family.getByText("보호자 연결이 해제되었습니다")).toBeVisible();
});
