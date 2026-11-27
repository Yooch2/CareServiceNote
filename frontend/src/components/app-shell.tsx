"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { api } from "@/lib/api";
import { useUser } from "./auth-gate";
import { Button } from "./ui";

/** 녹음이 기기 대기열에 들어가면 보내는 이벤트 */
export const QUEUE_CHANGED = "csn:queue-changed";

export function AppShell({ children }: { children: ReactNode }) {
  const user = useUser();
  const router = useRouter();

  async function logout() {
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
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
