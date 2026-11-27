import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { FAKE_AUDIO, PASSWORD, setupCaregiver, uniqueId } from "./helpers";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** 화면 하나를 axe로 검사한다. 숨겨진 이전 화면(Next Activity)은 검사하지 않는다. */
async function audit(page: Page, name: string, title: string) {
  await page.waitForLoadState("networkidle");
  // 화면마다 제목이 있는지 (클라이언트 이동 중 제목이 바뀌는 순간을 검사하지 않게 기다린다)
  await expect(page).toHaveTitle(`${title} · 돌봄수첩`);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const problems = result.violations.map(
    (v) => `${name}: [${v.impact}] ${v.id} — ${v.help} (${v.nodes.length}곳) ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`,
  );
  return problems;
}

test("주요 화면 접근성 (WCAG 2.2 AA 자동 검사)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const problems: string[] = [];

  await page.goto("/login");
  problems.push(...(await audit(page, "로그인", "로그인")));
  await page.goto("/signup");
  problems.push(...(await audit(page, "가입", "가입")));

  // 요양보호사
  const { recipientName, manager } = await setupCaregiver(page);
  await page.goto("/");
  problems.push(...(await audit(page, "요양보호사 홈", "수급자")));
  await page.getByRole("link", { name: recipientName }).click();
  await expect(page.getByRole("heading", { name: recipientName })).toBeVisible();
  problems.push(...(await audit(page, "방문 전 확인", "방문 전 확인")));
  await page.getByRole("link", { name: "오늘 방문 기록하기" }).click();
  problems.push(...(await audit(page, "녹음", "방문 기록하기")));
  await page.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await page.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  await expect(page.getByText(/확인이 필요한 AI 항목 \d+개/)).toBeVisible({ timeout: 30_000 });
  problems.push(...(await audit(page, "검토", "방문 기록")));
  const accept = page.getByRole("button", { name: "확인", exact: true });
  while ((await accept.count()) > 0) await accept.first().click();
  await page.getByRole("button", { name: "확정하기" }).click();
  await expect(page.getByText("센터 확인 전입니다.").filter({ visible: true })).toBeVisible();
  problems.push(...(await audit(page, "확정 기록", "방문 기록")));

  // 기관 담당자
  const boss = await (await browser.newContext()).newPage();
  await boss.goto("/login");
  await boss.getByLabel("아이디").fill(manager);
  await boss.getByLabel("비밀번호").fill(PASSWORD);
  await boss.getByRole("button", { name: "로그인" }).click();
  await expect(boss.getByRole("link", { name: /센터 관리/ })).toBeVisible();
  problems.push(...(await audit(boss, "기관 담당자 홈", "수급자")));
  await boss.getByRole("link", { name: /센터 관리/ }).click();
  problems.push(...(await audit(boss, "센터 관리", "센터 관리")));
  await boss.goto("/");
  await boss.getByRole("link", { name: recipientName }).click();
  await boss.getByRole("link", { name: /담당 배정 · 동의 · 보호자 관리/ }).click();
  await expect(boss.getByRole("heading", { name: "보호자", exact: true })).toBeVisible();
  problems.push(...(await audit(boss, "수급자 관리", "수급자 관리")));

  // 보호자: 공유 동의와 초대는 API로
  const rid = (await (await boss.request.get("/api/recipients")).json())[0].id as string;
  await boss.request.post(`/api/recipients/${rid}/consents`, {
    data: { kind: "guardian_share", granted_on: new Date().toLocaleDateString("sv-SE") },
  });
  const { code } = await (
    await boss.request.post("/api/org/invites", { data: { role: "guardian", recipient_id: rid, categories: ["remark"] } })
  ).json();
  const family = await (await browser.newContext()).newPage();
  await family.request.post("/api/auth/signup", {
    data: { login_id: uniqueId("fam"), password: PASSWORD, display_name: "보호자", invite_code: code },
  });
  await family.goto("/family");
  await expect(family.getByRole("heading", { name: recipientName })).toBeVisible();
  problems.push(...(await audit(family, "보호자", "보호자")));

  console.log(problems.join("\n") || "위반 없음");
  expect(problems).toEqual([]);
});
