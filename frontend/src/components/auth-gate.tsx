"use client";

import { useRouter } from "next/navigation";
import { createContext, use, useEffect, useState, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";
import { Button, Loading, Notice } from "./ui";

const UserContext = createContext<User | null>(null);

export function useUser(): User {
  const user = use(UserContext);
  if (!user) throw new Error("AuthGate 밖에서 useUser를 호출했습니다");
  return user;
}

/** 로그인 상태를 확인하고, 아니면 로그인 화면으로 보낸다. */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) router.replace("/login");
        else setFailed(true);
      });
  }, [router, attempt]);

  if (failed) {
    return (
      <main className="mx-auto flex w-full max-w-md flex-col gap-4 px-5 py-10">
        <Notice tone="error">서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요.</Notice>
        <Button
          onClick={() => {
            setFailed(false);
            setAttempt((n) => n + 1);
          }}
        >
          다시 시도
        </Button>
      </main>
    );
  }
  if (!user) return <Loading />;
  return <UserContext value={user}>{children}</UserContext>;
}
