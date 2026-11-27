"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { PROCESSING, STATUS_LABEL } from "@/lib/labels";
import type { VisitRecord } from "@/lib/types";
import { useUser } from "./auth-gate";
import { ConfirmedView } from "./confirmed-view";
import { BackLink, statusTone } from "./recipient-view";
import { ReviewPanel } from "./review-panel";
import { Badge, Button, Loading, Notice, PageTitle } from "./ui";

const POLL_MS = 1500;

export function RecordView() {
  const { id } = useParams<{ id: string }>();
  const [record, setRecord] = useState<VisitRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const r = await api<VisitRecord>(`/records/${id}`);
        if (cancelled) return;
        setRecord(r);
        if (PROCESSING.has(r.status)) timer = setTimeout(load, POLL_MS);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) setError("기록을 찾을 수 없습니다. 기록 목록에서 다시 골라 주세요.");
        else timer = setTimeout(load, POLL_MS * 2); // 일시적인 연결 문제면 계속 시도
      }
    };
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!record) return <Loading />;

  return (
    <>
      <BackLink href={`/recipients/${record.recipient_id}`}>기록 목록</BackLink>
      <PageTitle sub={<Badge tone={statusTone(record.status)}>{STATUS_LABEL[record.status]}</Badge>}>
        {record.visited_on} 방문
      </PageTitle>
      {PROCESSING.has(record.status) && (
        <div className="flex flex-col items-center gap-3 py-14 text-center" role="status">
          <div aria-hidden className="size-10 animate-spin rounded-full border-4 border-line border-t-pine" />
          <p className="text-lg font-semibold">{STATUS_LABEL[record.status]}</p>
          <p className="text-muted">보통 1분 안에 끝납니다. 화면을 닫아도 처리는 계속됩니다.</p>
        </div>
      )}
      {(record.status === "draft_ready" || record.status === "failed") && (
        <ReviewPanel key={record.status} record={record} onConfirmed={setRecord} />
      )}
      {record.status === "confirmed" && (
        <>
          <ReviewSignature record={record} onSigned={setRecord} />
          <ConfirmedView record={record} />
        </>
      )}
    </>
  );
}

/** 센터 확인 서명: 기관 담당자가 확정 기록을 읽었다는 표시 */
function ReviewSignature({ record, onSigned }: { record: VisitRecord; onSigned: (r: VisitRecord) => void }) {
  const user = useUser();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (record.review) {
    return (
      <p className="mb-5 flex flex-wrap items-center gap-2 text-muted">
        <Badge tone="pine">센터 확인</Badge>
        {record.review.reviewer_name} · {new Date(record.review.reviewed_at).toLocaleString("ko-KR")}
      </p>
    );
  }
  if (user.role !== "manager") return <p className="mb-5 text-sm text-muted">센터 확인 전입니다.</p>;

  async function sign() {
    setBusy(true);
    setError(null);
    try {
      onSigned(await api<VisitRecord>(`/records/${record.id}/review`, { method: "POST" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "연결을 확인하고 다시 눌러 주세요.");
      setBusy(false);
    }
  }

  return (
    <div className="mb-5 flex flex-col gap-2">
      <Button onClick={sign} disabled={busy}>
        읽고 확인했습니다 (센터 확인 서명)
      </Button>
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}
