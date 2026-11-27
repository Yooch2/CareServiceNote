"use client";

import Link from "next/link";
import { useEffect, useState, type SubmitEvent } from "react";

import { api, ApiError, postJson } from "@/lib/api";
import { alertTitle, MEAL_LABEL, MOOD_LABEL } from "@/lib/labels";
import type { Alert, TrendPoint } from "@/lib/types";
import { Button, Notice } from "./ui";

/** 알림 한 건: 제목, 근거(누르면 원래 기록), 긴급 우려 내용 */
export function AlertBody({ alert }: { alert: Alert }) {
  return (
    <>
      <p className="font-semibold">{alertTitle(alert.kind, alert.key)}</p>
      {alert.note && <p className="mt-1">{alert.note}</p>}
      {alert.evidence.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {alert.evidence.map((e) => (
            <li key={`${e.record_id}-${e.item_id ?? ""}`}>
              <Link href={`/records/${e.record_id}`} className="text-sm underline-offset-4 hover:underline">
                <span className="text-muted">{e.visited_on}</span> {e.text}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** 방문 전 확인 맨 위: 이 수급자의 미처리 알림 */
export function RecipientAlerts({ recipientId, refresh }: { recipientId: string; refresh: number }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  useEffect(() => {
    api<Alert[]>(`/recipients/${recipientId}/alerts`)
      .then(setAlerts)
      .catch(() => undefined);
  }, [recipientId, refresh]);

  if (alerts.length === 0) return null;
  return (
    <section aria-label="변화 알림" className="flex flex-col gap-2">
      <h2 className="text-lg font-bold">
        변화 알림 <span className="font-normal text-muted">{alerts.length}건</span>
      </h2>
      {alerts.map((a) => (
        <div key={a.id} className="rounded-r-lg border-l-4 border-risk bg-risk/5 px-4 py-3">
          <AlertBody alert={a} />
          <p className="mt-2 text-sm text-muted">센터에서 확인 중입니다.</p>
        </div>
      ))}
    </section>
  );
}

/** 요양보호사가 규칙과 관계없이 센터에 우려를 올린다 */
export function ConcernForm({ recipientId, onSent }: { recipientId: string; onSent: () => void }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function send(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    setError(null);
    try {
      await postJson(`/recipients/${recipientId}/concerns`, { note: String(new FormData(formEl).get("note") ?? "") });
      formEl.reset();
      setOpen(false);
      setSent(true);
      onSent();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "보내지 못했습니다. 연결을 확인해 주세요.");
    }
  }

  if (!open) {
    return (
      <div className="flex flex-col gap-2">
        {sent && <Notice>센터에 우려를 보냈습니다.</Notice>}
        <Button variant="secondary" onClick={() => setOpen(true)}>
          센터에 우려 알리기
        </Button>
      </div>
    );
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-3 rounded-lg border border-line bg-sheet p-4">
      <Notice tone="warn">응급 상황이면 먼저 119와 센터 전화로 연락하세요. 여기 남긴 내용은 센터 인박스로만 갑니다.</Notice>
      <label className="flex flex-col gap-1.5 font-medium">
        걱정되는 점
        <textarea
          name="note"
          required
          maxLength={500}
          rows={3}
          className="rounded-xl border border-line bg-sheet p-3 font-normal focus:border-pine focus:outline-none"
        />
      </label>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button type="submit">센터에 보내기</Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          취소
        </Button>
      </div>
    </form>
  );
}

const CHART_H = 96; // 막대 영역 높이 (식사량 4 = 가득)

/** 최근 30일 식사량(막대)·기분(글자). 한 계열이라 범례 없이 제목이 무엇인지 말한다. */
export function Trends({ recipientId }: { recipientId: string }) {
  const [points, setPoints] = useState<TrendPoint[] | null>(null);
  useEffect(() => {
    api<TrendPoint[]>(`/recipients/${recipientId}/trends?days=30`)
      .then(setPoints)
      .catch(() => setPoints([]));
  }, [recipientId]);

  if (!points || points.length === 0) return null;
  return (
    <section aria-label="식사량과 기분" className="flex flex-col gap-2">
      <h2 className="text-lg font-bold">
        식사량과 기분 <span className="font-normal text-muted">최근 30일</span>
      </h2>
      <div className="rounded-lg border border-line bg-sheet p-4">
        <div className="flex gap-3">
          {/* 세로축: 단계 이름 */}
          <div aria-hidden className="relative w-16 shrink-0 text-right text-xs text-muted" style={{ height: CHART_H }}>
            <span className="absolute right-0 -translate-y-1/2" style={{ top: 0 }}>
              다 드심
            </span>
            <span className="absolute right-0 -translate-y-1/2" style={{ top: CHART_H / 2 }}>
              절반
            </span>
            <span className="absolute right-0 -translate-y-1/2" style={{ top: CHART_H }}>
              거의 못 드심
            </span>
          </div>
          <ol className="flex min-w-0 flex-1 items-end gap-0.5 overflow-x-auto" aria-hidden>
            {points.map((p) => (
              <li key={p.record_id} className="flex min-w-7 flex-1 flex-col items-center">
                <Link
                  href={`/records/${p.record_id}`}
                  title={`${p.visited_on} · 식사량 ${p.meal_level === null ? "언급 없음" : MEAL_LABEL[p.meal_level]} · 기분 ${p.mood ? MOOD_LABEL[p.mood] : "언급 없음"}`}
                  className="group flex w-full flex-col items-center justify-end border-b border-line"
                  style={{ height: CHART_H }}
                >
                  {p.meal_level === null ? (
                    <span className="mb-1 text-xs text-muted">–</span>
                  ) : (
                    <span
                      className="w-full max-w-6 rounded-t bg-pine group-hover:bg-pine-dark"
                      style={{ height: Math.max(4, (p.meal_level / 4) * CHART_H) }}
                    />
                  )}
                </Link>
                <span className="mt-1 text-xs text-muted">{p.visited_on.slice(5).replace("-", "/")}</span>
                <span className="text-xs">{p.mood ? MOOD_LABEL[p.mood] : ""}</span>
              </li>
            ))}
          </ol>
        </div>
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-muted">표로 보기</summary>
          <table className="mt-2 w-full text-left">
            <thead className="text-muted">
              <tr>
                <th className="py-1 font-medium">방문일</th>
                <th className="py-1 font-medium">식사량</th>
                <th className="py-1 font-medium">기분</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.record_id} className="border-t border-line">
                  <td className="py-1">{p.visited_on}</td>
                  <td className="py-1">{p.meal_level === null ? "언급 없음" : MEAL_LABEL[p.meal_level]}</td>
                  <td className="py-1">{p.mood ? MOOD_LABEL[p.mood] : "언급 없음"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </section>
  );
}

