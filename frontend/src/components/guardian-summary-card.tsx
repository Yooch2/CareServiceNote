"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/labels";
import type { GuardianSummary } from "@/lib/types";
import { useUser } from "./auth-gate";
import { Badge, Button, Notice, Sheet } from "./ui";

const TEXTAREA = "w-full rounded-xl border border-line bg-sheet p-3 focus:border-pine focus:outline-none";

/**
 * 보호자 하루 요약: 기관 담당자가 만들고, 고치고, 승인한다. 승인해야 보호자에게 보인다.
 * 요양보호사는 읽기만 한다.
 */
export function GuardianSummaryCard({ recordId }: { recordId: string }) {
  const user = useUser();
  const manager = user.role === "manager";
  const [summary, setSummary] = useState<GuardianSummary | null | undefined>(undefined);
  const [drafts, setDrafts] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = `/records/${recordId}/guardian-summary`;

  useEffect(() => {
    api<GuardianSummary | null>(url)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [url]);

  async function call(path: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    try {
      setSummary(await api<GuardianSummary>(path, init));
      setDrafts(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "연결을 확인하고 다시 눌러 주세요.");
    } finally {
      setBusy(false);
    }
  }

  if (summary === undefined || (!manager && summary === null)) return null;
  const approved = summary?.status === "approved";

  return (
    <section aria-label="보호자 하루 요약" className="mb-6">
      <Sheet>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="font-semibold">보호자 하루 요약</h2>
          {summary && <Badge tone={approved ? "pine" : "follow"}>{approved ? "보호자에게 공유 중" : "승인 전"}</Badge>}
        </div>
        {!summary && <p className="text-muted">확정된 항목으로 보호자에게 보낼 짧은 요약을 만듭니다. 승인해야 보호자에게 보입니다.</p>}

        {summary && drafts === null && (
          <ol className="flex flex-col gap-2">
            {summary.sentences.map((s, i) => (
              <li key={i}>
                <p>{s.text}</p>
                <p className="mt-0.5 flex flex-wrap gap-1 text-xs text-muted">
                  근거: {s.categories.map((c) => CATEGORY_LABEL[c]).join(", ")}
                  {s.edited && " · 담당자 수정"}
                </p>
              </li>
            ))}
          </ol>
        )}

        {summary && drafts !== null && (
          <div className="flex flex-col gap-3">
            {drafts.map((text, i) => (
              <label key={i} className="flex flex-col gap-1 text-sm font-medium">
                {i + 1}번째 문장 (근거: {summary.sentences[i].categories.map((c) => CATEGORY_LABEL[c]).join(", ")})
                <textarea
                  value={text}
                  maxLength={300}
                  rows={2}
                  onChange={(e) => setDrafts((d) => d && d.map((v, j) => (j === i ? e.target.value : v)))}
                  className={`${TEXTAREA} text-base font-normal`}
                />
              </label>
            ))}
            <p className="text-sm text-muted">문장을 비우면 지웁니다. 근거가 정해진 문장만 고칠 수 있어 새 문장은 추가할 수 없습니다.</p>
          </div>
        )}

        {approved && summary?.approver_name && (
          <p className="mt-2 text-xs text-muted">{summary.approver_name} 승인</p>
        )}
        {!manager && !approved && <p className="mt-2 text-sm text-muted">기관 담당자가 확인하고 있습니다.</p>}

        {manager && (
          <div className="mt-3 flex flex-wrap gap-2">
            {drafts !== null ? (
              <>
                <Button
                  disabled={busy}
                  onClick={() =>
                    call(url, { method: "PUT", body: JSON.stringify({ sentences: drafts.map((text) => ({ text })) }) })
                  }
                >
                  저장
                </Button>
                <Button variant="ghost" onClick={() => setDrafts(null)}>
                  취소
                </Button>
              </>
            ) : approved ? (
              <Button variant="secondary" disabled={busy} onClick={() => call(`${url}/unapprove`, { method: "POST" })}>
                승인 취소
              </Button>
            ) : (
              <>
                {summary && (
                  <Button disabled={busy} onClick={() => call(`${url}/approve`, { method: "POST" })}>
                    승인하고 보호자에게 공유
                  </Button>
                )}
                {summary && (
                  <Button variant="secondary" onClick={() => setDrafts(summary.sentences.map((s) => s.text))}>
                    문장 고치기
                  </Button>
                )}
                <Button variant={summary ? "ghost" : "secondary"} disabled={busy} onClick={() => call(url, { method: "POST" })}>
                  {busy ? "만드는 중…" : summary ? "다시 만들기" : "요약 만들기"}
                </Button>
              </>
            )}
          </div>
        )}
        {error && (
          <div className="mt-3">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
      </Sheet>
    </section>
  );
}
