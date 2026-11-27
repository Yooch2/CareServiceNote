"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import {
  clearOtherUsers,
  clearPending,
  listPending,
  removePending,
  type PendingUpload,
} from "@/lib/offline-queue";
import { flushPending } from "@/lib/upload";
import { useUser } from "./auth-gate";
import { Button, Notice } from "./ui";

/** 녹음이 기기 대기열에 들어가면 보내는 이벤트 */
export const QUEUE_CHANGED = "csn:queue-changed";

export function AppShell({ children }: { children: ReactNode }) {
  const user = useUser();
  const router = useRouter();

  async function logout() {
    const waiting = await listPending(user.id).catch(() => []);
    if (
      waiting.length > 0 &&
      !window.confirm(`올리지 못한 기록 ${waiting.length}건이 이 기기에서 지워집니다. 로그아웃할까요?`)
    ) {
      return;
    }
    await clearPending(user.id).catch(() => undefined);
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
    }
  }

  return (
    <>
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-1.5">
          <Link href="/" className="py-2 text-lg font-bold text-pine">
            돌봄수첩
          </Link>
          <div className="flex items-center gap-1 text-muted">
            <span className="text-sm">{user.display_name}</span>
            <Button variant="ghost" onClick={logout}>
              로그아웃
            </Button>
          </div>
        </div>
      </header>
      <PendingBanner userId={user.id} />
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}

/** 기기에 저장된 녹음 수를 보여 주고, 앱을 열 때와 다시 연결될 때 올린다. */
function PendingBanner({ userId }: { userId: string }) {
  const [pending, setPending] = useState<PendingUpload[]>([]);

  const flush = useCallback(() => {
    flushPending(userId)
      .then(setPending)
      .catch(() => undefined);
  }, [userId]);

  useEffect(() => {
    clearOtherUsers(userId)
      .catch(() => undefined)
      .finally(flush);
    const refresh = () =>
      listPending(userId)
        .then(setPending)
        .catch(() => undefined);
    window.addEventListener("online", flush);
    window.addEventListener(QUEUE_CHANGED, refresh);
    return () => {
      window.removeEventListener("online", flush);
      window.removeEventListener(QUEUE_CHANGED, refresh);
    };
  }, [flush, userId]);

  if (pending.length === 0) return null;
  const rejected = pending.filter((p) => p.lastError);
  return (
    <div className="mx-auto w-full max-w-2xl px-4 pt-4">
      <Notice tone="warn">
        <p className="font-semibold">업로드 대기 {pending.length}건</p>
        <p className="text-sm">이 기기에 저장되어 있습니다. 연결되면 자동으로 올라갑니다.</p>
        {rejected.map((p) => (
          <p key={p.id} className="mt-2 text-sm">
            {p.visitedOn} 기록을 올리지 못했습니다: {p.lastError}{" "}
            <button
              type="button"
              className="font-semibold underline underline-offset-4"
              onClick={() =>
                removePending(p.id)
                  .then(() => listPending(userId))
                  .then(setPending)
              }
            >
              기기에서 지우기
            </button>
          </p>
        ))}
      </Notice>
    </div>
  );
}
