"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLayoutEffect, useState, type SubmitEvent } from "react";

import { ApiError, postJson } from "@/lib/api";
import { Button, Field, Notice } from "./ui";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [way, setWay] = useState<"center" | "invite">("invite");
  const signup = mode === "signup";

  // 로그인 후 숨겨진 화면(Activity)이 '진행 중'으로 남지 않게, 숨겨질 때 초기화한다
  useLayoutEffect(
    () => () => {
      setPending(false);
      setError(null);
    },
    [],
  );

  async function submit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setPending(true);
    setError(null);
    try {
      form.delete("way");
      await postJson(signup ? "/auth/signup" : "/auth/login", Object.fromEntries(form));
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.");
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-5 py-10">
      <div className="border-l-[6px] border-pine pl-4">
        <p className="text-lg font-bold text-pine">돌봄수첩</p>
        <h1 className="mt-1 text-3xl leading-tight font-bold">{signup ? "가입" : "로그인"}</h1>
        <p className="mt-2 text-muted">방문에서 들은 말과 본 것을 다음 돌봄으로 넘깁니다.</p>
      </div>
      <Notice tone="warn">데모 서비스라 모든 데이터는 가상입니다. 실제 이름, 연락처, 건강정보는 입력하지 마세요.</Notice>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {signup && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1.5 font-medium">가입 방법</legend>
            <div className="grid grid-cols-2 gap-1 rounded-xl border border-line bg-sheet p-1">
              {(
                [
                  ["invite", "초대 코드로 가입"],
                  ["center", "센터 만들기"],
                ] as const
              ).map(([value, label]) => (
                <label
                  key={value}
                  className={`flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-2 text-center font-semibold has-focus-visible:outline-3 has-focus-visible:outline-pine ${way === value ? "bg-pine text-white" : "text-muted hover:text-ink"}`}
                >
                  <input
                    type="radio"
                    name="way"
                    value={value}
                    checked={way === value}
                    onChange={() => setWay(value)}
                    className="sr-only"
                  />
                  {label}
                </label>
              ))}
            </div>
            <p className="text-sm text-muted">
              {way === "invite"
                ? "요양보호사와 보호자는 기관 담당자에게 받은 초대 코드로 가입합니다."
                : "센터를 만들면 기관 담당자가 되어 수급자와 구성원을 관리합니다."}
            </p>
          </fieldset>
        )}
        {signup &&
          (way === "invite" ? (
            <Field
              key="invite"
              label="초대 코드"
              name="invite_code"
              autoCapitalize="characters"
              autoComplete="off"
              placeholder="예: ABCDE-23456"
              maxLength={30}
              required
            />
          ) : (
            <Field key="center" label="센터 이름 (가명)" name="center_name" maxLength={30} required />
          ))}
        <Field
          label="아이디"
          name="login_id"
          autoComplete="username"
          autoCapitalize="none"
          required
          pattern={signup ? "[a-z0-9_]{4,20}" : undefined}
          hint={signup ? "영문 소문자, 숫자, 밑줄로 4~20자" : undefined}
        />
        <Field
          label="비밀번호"
          name="password"
          type="password"
          autoComplete={signup ? "new-password" : "current-password"}
          minLength={signup ? 8 : undefined}
          hint={signup ? "8자 이상" : undefined}
          required
        />
        {signup && <Field label="표시 이름 (가명)" name="display_name" maxLength={30} required />}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" disabled={pending}>
          {signup ? "가입하기" : "로그인"}
        </Button>
      </form>
      <p className="text-center text-muted">
        {signup ? "이미 계정이 있다면 " : "처음이라면 "}
        <Link className="font-semibold text-pine underline underline-offset-4" href={signup ? "/login" : "/signup"}>
          {signup ? "로그인" : "가입하기"}
        </Link>
      </p>
      {!signup && (
        <p className="text-center text-sm text-muted">
          데모 계정(비밀번호 demo1234): 요양보호사 demo · 기관 담당자 manager · 보호자 family
        </p>
      )}
    </main>
  );
}
