"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/labels";
import type { Recipient, RecordStatus, RecordSummary } from "@/lib/types";
import { Badge, Loading, Notice, PageTitle, type Tone } from "./ui";

export function statusTone(status: RecordStatus): Tone {
  if (status === "confirmed") return "pine";
  if (status === "draft_ready") return "follow";
  if (status === "failed") return "risk";
  return "neutral";
}

export function BackLink({ href, children }: { href: string; children: string }) {
  return (
    <Link href={href} className="-ml-1 inline-flex min-h-11 items-center px-1 text-muted hover:text-ink">
      ‹ {children}
    </Link>
  );
}

export function RecipientView() {
  const { id } = useParams<{ id: string }>();
  const [recipient, setRecipient] = useState<Recipient | null>(null);
  const [records, setRecords] = useState<RecordSummary[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([api<Recipient>(`/recipients/${id}`), api<RecordSummary[]>(`/recipients/${id}/records`)])
      .then(([r, list]) => {
        setRecipient(r);
        setRecords(list);
      })
      .catch(() => setError(true));
  }, [id]);

  if (error) return <Notice tone="error">수급자 정보를 불러오지 못했습니다. 목록으로 돌아가 다시 골라 주세요.</Notice>;
  if (!recipient || !records) return <Loading />;

  return (
    <>
      <BackLink href="/">수급자 목록</BackLink>
      <PageTitle>{recipient.name}</PageTitle>
      <Link
        href={`/recipients/${id}/record`}
        className="flex min-h-16 items-center justify-center gap-3 rounded-xl bg-pine text-xl font-semibold text-white hover:bg-pine-dark"
      >
        <span aria-hidden className="size-3.5 rounded-full bg-white" />
        오늘 방문 기록하기
      </Link>
      <h2 className="mt-8 mb-2 font-semibold text-muted">지난 기록</h2>
      {records.length === 0 ? (
        <p className="text-muted">아직 기록이 없습니다.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
          {records.map((r) => (
            <li key={r.id}>
              <Link href={`/records/${r.id}`} className="flex min-h-14 items-center justify-between gap-3 px-4 py-3 hover:bg-paper">
                <span>
                  <span className="font-semibold">{r.visited_on}</span>
                  {!r.is_mine && <span className="ml-2 text-sm text-muted">다른 요양보호사</span>}
                </span>
                <Badge tone={statusTone(r.status)}>{STATUS_LABEL[r.status]}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
