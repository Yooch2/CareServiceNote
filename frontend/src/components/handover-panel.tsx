"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABEL, RISK_LABEL } from "@/lib/labels";
import type { Days, Handover, HandoverSummary } from "@/lib/types";
import { Badge, Button, Notice, Sheet } from "./ui";

const PERIODS: Days[] = [7, 14, 30];

/** 방문 전 확인: 남은 확인 사항, AI 인계 요약, 주의 항목, 최근 확인 결과, 후속 확인 완료율 */
export function HandoverPanel({ recipientId, canSummarize }: { recipientId: string; canSummarize: boolean }) {
  const [days, setDays] = useState<Days>(14);
  const [data, setData] = useState<Handover | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<Handover>(`/recipients/${recipientId}/handover?days=${days}`)
      .then((h) => {
        if (!cancelled) {
          setData(h);
          setFailed(false);
        }
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [recipientId, days]);

  if (failed) return <Notice tone="error">방문 전 확인 내용을 불러오지 못했습니다. 새로고침해 주세요.</Notice>;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-5">
      <div role="radiogroup" aria-label="조회 기간" className="flex gap-1 self-start rounded-xl border border-line bg-sheet p-1">
        {PERIODS.map((d) => (
          <button
            key={d}
            type="button"
            role="radio"
            aria-checked={days === d}
            onClick={() => setDays(d)}
            className={`min-h-10 rounded-lg px-4 font-semibold ${days === d ? "bg-pine text-white" : "text-muted hover:text-ink"}`}
          >
            최근 {d}일
          </button>
        ))}
      </div>

      <section aria-label="남은 확인 사항">
        <h2 className="mb-2 text-lg font-bold">
          남은 확인 사항 <span className="font-normal text-muted">{data.open_followups.length}건</span>
        </h2>
        {data.open_followups.length === 0 ? (
          <p className="text-muted">이어서 확인할 일이 없습니다.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-l-[6px] border-line border-l-follow bg-sheet">
            {data.open_followups.map((f) => (
              <li key={f.item_id}>
                <Link href={`/records/${f.record_id}`} className="block px-4 py-3 hover:bg-paper">
                  <span className="font-semibold">{f.content}</span>
                  <span className="block text-sm text-muted">{f.visited_on} 방문에서</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <SummaryBlock
        recipientId={recipientId}
        days={days}
        summary={data.summary}
        hasRecords={data.last_visit_on !== null}
        canSummarize={canSummarize}
        onMade={(summary) => setData((d) => (d ? { ...d, summary } : d))}
      />

      {data.risk_items.length > 0 && (
        <section aria-label="주의 항목">
          <h2 className="mb-2 text-lg font-bold">주의 항목</h2>
          <ul className="flex flex-col gap-2">
            {data.risk_items.map((r) => (
              <li key={r.item_id}>
                <Link
                  href={`/records/${r.record_id}`}
                  className="flex items-start justify-between gap-3 rounded-lg border border-risk/40 bg-sheet px-4 py-3 hover:bg-paper"
                >
                  <span>
                    {r.content}
                    <span className="block text-sm text-muted">
                      {r.visited_on} · {CATEGORY_LABEL[r.category]}
                    </span>
                  </span>
                  <Badge tone="risk">{RISK_LABEL[r.risk_tag]}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="후속 확인">
        <h2 className="mb-2 text-lg font-bold">후속 확인</h2>
        <Completion due={data.completion.due} checked={data.completion.checked} days={days} />
        {data.recent_checks.length > 0 && (
          <ul className="mt-3 flex flex-col gap-2">
            {data.recent_checks.map((c) => (
              <li key={c.followup_item_id}>
                <Link href={`/records/${c.record_id}`} className="block rounded-lg border border-line bg-sheet px-4 py-3 hover:bg-paper">
                  <span className="text-sm text-muted">{c.visited_on} 확인 · {c.followup_content}</span>
                  <span className="block">{c.result}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Completion({ due, checked, days }: { due: number; checked: number; days: number }) {
  if (due === 0) return <p className="text-muted">최근 {days}일 동안 생긴 확인 사항이 없습니다.</p>;
  const percent = Math.round((checked / due) * 100);
  return (
    <div>
      <p>
        최근 {days}일 확인할 일 {due}건 중 <strong>{checked}건</strong> 확인 ({percent}%)
      </p>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-line" aria-hidden>
        <div className="h-full bg-pine" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function SummaryBlock({
  recipientId,
  days,
  summary,
  hasRecords,
  canSummarize,
  onMade,
}: {
  recipientId: string;
  days: Days;
  summary: HandoverSummary | null;
  hasRecords: boolean;
  canSummarize: boolean;
  onMade: (s: HandoverSummary) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function make() {
    setBusy(true);
    setError(null);
    try {
      onMade(await api<HandoverSummary>(`/recipients/${recipientId}/handover/summary?days=${days}`, { method: "POST" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "연결을 확인하고 다시 눌러 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-bold">AI 인계 요약</h2>
        {hasRecords && canSummarize && (
          <Button variant={summary ? "ghost" : "secondary"} onClick={make} disabled={busy}>
            {busy ? "만드는 중…" : summary ? "다시 만들기" : "요약 만들기"}
          </Button>
        )}
      </div>
      {!hasRecords && <p className="mt-2 text-muted">확정된 기록이 생기면 요약을 만들 수 있습니다.</p>}
      {hasRecords && !canSummarize && (
        <p className="mt-2 text-muted">건강정보 처리 동의가 없어 새 요약을 만들 수 없습니다.</p>
      )}
      {hasRecords && canSummarize && !summary && !error && (
        <p className="mt-2 text-muted">최근 {days}일 기록으로 다음 방문에 알아야 할 내용을 정리합니다.</p>
      )}
      {summary?.stale && (
        <p className="mt-2 text-sm font-medium text-follow">요약 뒤에 새로 확정된 기록이 있습니다.</p>
      )}
      {summary && (
        <ol className="mt-3 flex flex-col gap-3">
          {summary.sentences.map((s, i) => (
            <li key={i}>
              <p>{s.text}</p>
              <p className="mt-1 flex flex-wrap gap-1.5">
                {s.items.map((ref) => (
                  <Link
                    key={ref.item_id}
                    href={`/records/${ref.record_id}`}
                    className="rounded-md border border-line px-2 py-0.5 text-sm text-muted hover:border-pine hover:text-ink"
                  >
                    근거 {ref.visited_on}
                  </Link>
                ))}
              </p>
            </li>
          ))}
        </ol>
      )}
      {summary && <p className="mt-3 text-xs text-muted">AI가 확정 기록으로 쓴 요약입니다. 근거를 눌러 원래 기록을 확인하세요.</p>}
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error} 위의 확인 사항과 주의 항목은 그대로 볼 수 있습니다.</Notice>
        </div>
      )}
    </Sheet>
  );
}
