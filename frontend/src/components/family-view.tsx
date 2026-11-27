"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABEL, CATEGORY_ORDER, dateOnly, timeOnly } from "@/lib/labels";
import type { GuardianHome } from "@/lib/types";
import { useUser } from "./auth-gate";
import { TabbedSheet } from "./category";
import { Loading, Notice, PageTitle } from "./ui";

/** 보호자 화면: 열람 범위 안의 확정 항목만 방문일별로 */
export function FamilyView() {
  const user = useUser();
  const [home, setHome] = useState<GuardianHome | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  useEffect(() => {
    api<GuardianHome>("/guardian/home")
      .then(setHome)
      .catch((err: unknown) =>
        setBlocked(err instanceof ApiError ? err.message : "기록을 불러오지 못했습니다. 새로고침해 주세요."),
      );
  }, []);

  if (user.role !== "guardian") return <Notice tone="error">보호자 계정으로 볼 수 있는 화면입니다.</Notice>;
  if (blocked) return <Notice tone="error">{blocked}</Notice>;
  if (!home) return <Loading />;

  const scope = CATEGORY_ORDER.filter((c) => home.categories.includes(c)).map((c) => CATEGORY_LABEL[c]);
  return (
    <>
      <PageTitle sub={`${user.org_name}에서 공유하는 최근 30일 방문 기록`}>{home.recipient_name}</PageTitle>
      <Notice>
        수급자 동의에 따라 <strong>{scope.join(", ")}</strong> 내용만 볼 수 있습니다. 궁금한 점은 센터에 문의해 주세요.
      </Notice>
      <Sessions sessions={home.sessions} />
      {home.notices.length > 0 && (
        <section aria-label="센터 안내" className="mt-6">
          <h2 className="mb-2 text-lg font-bold">센터 안내</h2>
          <ul className="flex flex-col gap-2">
            {home.notices.map((n, i) => (
              <li key={i} className="rounded-r-lg border-l-4 border-pine bg-sheet px-4 py-3">
                <p>{n.message}</p>
                <p className="mt-1 text-sm text-muted">{dateOnly(n.shared_at)}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {home.records.length === 0 && <p className="mt-6 text-muted">최근 30일 동안 공유된 기록이 없습니다.</p>}
      <ol className="mt-6 flex flex-col gap-6">
        {home.records.map((r, i) => (
          <li key={`${r.visited_on}-${i}`} aria-label={`${r.visited_on} 방문`}>
            <h2 className="mb-2 text-lg font-bold">{r.visited_on} 방문</h2>
            {r.summary.length > 0 && (
              <div className="mb-3 rounded-lg border border-line bg-sheet p-4">
                <p className="mb-1 text-sm text-muted">센터가 확인한 하루 요약</p>
                {r.summary.map((t, j) => (
                  <p key={j} className="text-lg">
                    {t}
                  </p>
                ))}
              </div>
            )}
            <details open={r.summary.length === 0}>
              <summary className="mb-2 cursor-pointer text-muted">기록 자세히</summary>
            <ul className="flex flex-col gap-2">
              {r.items.map((item, j) => (
                <li key={j}>
                  <TabbedSheet category={item.category}>
                    <p className="text-sm text-muted">{CATEGORY_LABEL[item.category]}</p>
                    <p className="text-lg">{item.content}</p>
                  </TabbedSheet>
                </li>
              ))}
              {r.checks.map((c, j) => (
                <li key={`c${j}`}>
                  <TabbedSheet category="followup">
                    <p className="text-sm text-muted">이전에 확인하기로 한 것 · {c.followup_content}</p>
                    <p className="text-lg">{c.result}</p>
                  </TabbedSheet>
                </li>
              ))}
            </ul>
            </details>
          </li>
        ))}
      </ol>
    </>
  );
}

/** 최근 방문 시각 (오늘이면 '오늘'). 요양보호사 이름은 받지 않는다. */
function Sessions({ sessions }: { sessions: GuardianHome["sessions"] }) {
  if (sessions.length === 0) return null;
  const today = new Date().toLocaleDateString("sv-SE");
  return (
    <section aria-label="방문 시각" className="mt-6">
      <h2 className="mb-2 text-lg font-bold">방문 시각</h2>
      <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
        {sessions.slice(0, 5).map((s) => {
          const day = dateOnly(s.started_at);
          return (
            <li key={s.started_at} className="px-4 py-2">
              <span className="font-semibold">{day === today ? "오늘" : day}</span>{" "}
              {timeOnly(s.started_at)} 방문 시작
              {s.ended_at ? ` · ${timeOnly(s.ended_at)} 종료` : <span className="text-pine"> · 방문 중</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
