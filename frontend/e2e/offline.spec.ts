import { expect, test } from "@playwright/test";

import { signupAndPickAudio } from "./helpers";

test("연결이 끊기면 기기에 저장했다가 다시 연결되면 올린다", async ({ page, context }) => {
  await signupAndPickAudio(page);

  await context.setOffline(true);
  await page.getByRole("button", { name: "기록 올리기" }).click();
  await expect(page.getByText(/이 기기에 저장했습니다/)).toBeVisible();
  await expect(page.getByText("업로드 대기 1건")).toBeVisible();

  // 대기열에는 수급자 이름이 들어가지 않는다
  const stored = await page.evaluate(
    () =>
      new Promise<string>((resolve) => {
        const req = indexedDB.open("csn-offline");
        req.onsuccess = () => {
          const all = req.result.transaction("uploads").objectStore("uploads").getAll();
          all.onsuccess = () => resolve(JSON.stringify(all.result.map((u: Record<string, unknown>) => ({ ...u, audio: null }))));
        };
      }),
  );
  expect(stored).not.toContain("가상 어르신");

  await context.setOffline(false);
  await expect(page.getByText(/업로드 대기/)).toBeHidden({ timeout: 15_000 });

  await page.getByRole("link", { name: "‹ 기록 목록" }).click();
  await expect(page.getByRole("link", { name: /처리 대기|옮기는 중|나누는 중|검토 필요/ })).toHaveCount(1);
});
