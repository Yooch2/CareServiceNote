import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const FAKE_AUDIO = { name: "sample.webm", mimeType: "audio/webm", buffer: Buffer.from("fake-audio") };
export const PASSWORD = "e2e-password-1";

export function uniqueId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}

async function call<T = unknown>(req: APIRequestContext, method: "post" | "get", path: string, data?: unknown): Promise<T> {
  const res = await req[method](`/api${path}`, data === undefined ? undefined : { data });
  expect(res.ok(), `${method.toUpperCase()} ${path} → ${res.status()} ${await res.text()}`).toBeTruthy();
  return (res.status() === 204 ? undefined : await res.json()) as T;
}

/**
 * API로 센터(기관 담당자)·수급자·건강정보 동의·요양보호사 계정·배정을 만들고,
 * 브라우저는 요양보호사로 로그인된 상태로 둔다.
 */
export async function setupCaregiver(page: Page): Promise<{ recipientName: string; manager: string }> {
  const req = page.request;
  const manager = uniqueId("boss");
  const carer = uniqueId("e2e");
  const recipientName = `가상 어르신 ${carer.slice(-4)}`;

  await call(req, "post", "/auth/signup", {
    login_id: manager,
    password: PASSWORD,
    display_name: "테스트 담당자",
    center_name: "테스트 센터",
  });
  const recipient = await call<{ id: string }>(req, "post", "/recipients", { name: recipientName });
  await call(req, "post", `/recipients/${recipient.id}/consents`, {
    kind: "health_record",
    granted_on: new Date().toLocaleDateString("sv-SE"),
  });
  const { code } = await call<{ code: string }>(req, "post", "/org/invites", { role: "caregiver" });

  const user = await call<{ id: string }>(req, "post", "/auth/signup", {
    login_id: carer,
    password: PASSWORD,
    display_name: "테스트 요양보호사",
    invite_code: code,
  });
  await call(req, "post", "/auth/login", { login_id: manager, password: PASSWORD });
  await call(req, "post", `/recipients/${recipient.id}/assignments`, { caregiver_id: user.id });
  await call(req, "post", "/auth/login", { login_id: carer, password: PASSWORD });
  return { recipientName, manager };
}

/** 요양보호사로 준비한 뒤 수급자 녹음 화면에서 파일을 골라 둔다. */
export async function signupAndPickAudio(page: Page): Promise<void> {
  const { recipientName } = await setupCaregiver(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "수급자" })).toBeVisible();
  await page.getByRole("link", { name: recipientName }).click();
  await page.getByRole("link", { name: "오늘 방문 기록하기" }).click();

  const upload = page.getByRole("button", { name: "기록 올리기" });
  await expect(upload).toBeDisabled();
  await page.getByLabel(/녹음해서 기록에 쓴다는 것을 알렸습니다/).check();
  await page.getByLabel("또는 음성 파일 올리기").setInputFiles(FAKE_AUDIO);
  await expect(upload).toBeEnabled();
}
