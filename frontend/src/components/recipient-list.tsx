"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type SubmitEvent } from "react";

import { api, ApiError, postJson } from "@/lib/api";
import type { Recipient, ReviewQueueItem } from "@/lib/types";
import { useUser } from "./auth-gate";
import { Badge, Button, Field, Loading, Notice, PageTitle, Sheet } from "./ui";

export function RecipientList() {
  const user = useUser();
  const router = useRouter();
  const manager = user.role === "manager";
  const [recipients, setRecipients] = useState<Recipient[] | null>(null);
  const [reviews, setReviews] = useState<number | null>(null);
  const [openAlerts, setOpenAlerts] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user.role === "guardian") {
      router.replace("/family");
      return;
    }
    api<Recipient[]>("/recipients")
      .then(setRecipients)
      .catch(() => setError("수급자 목록을 불러오지 못했습니다. 새로고침해 주세요."));
    if (user.role === "manager") {
      api<ReviewQueueItem[]>("/org/reviews")
        .then((q) => setReviews(q.length))
        .catch(() => undefined);
      api<unknown[]>("/org/alerts")
        .then((a) => setOpenAlerts(a.length))
        .catch(() => undefined);
    }
  }, [user.role, router]);

  async function add(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const name = String(new FormData(formEl).get("name") ?? "");
    try {
      const created = await postJson<Recipient>("/recipients", { name });
      setRecipients((list) => [...(list ?? []), created]);
      formEl.reset();
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "추가하지 못했습니다. 연결을 확인해 주세요.");
    }
  }

  if (user.role === "guardian") return <Loading />;

  return (
    <>
      <PageTitle sub={manager ? `${user.org_name} 수급자` : "오늘 방문할 어르신을 고르세요"}>수급자</PageTitle>
      {manager && (
        <Link
          href="/center"
          className="mb-5 flex min-h-14 items-center justify-between rounded-xl border border-line bg-sheet px-4 font-semibold hover:border-pine"
        >
          센터 관리
          <span className="flex flex-wrap justify-end gap-1.5 text-muted">
            {openAlerts > 0 && <Badge tone="risk">알림 {openAlerts}건</Badge>}
            {reviews ? <Badge tone="follow">확인 대기 {reviews}건</Badge> : null}
            {!openAlerts && !reviews && <span aria-hidden>›</span>}
          </span>
        </Link>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      {recipients === null && !error && <Loading />}
      {recipients?.length === 0 && (
        <p className="text-muted">
          {manager
            ? "아직 등록된 수급자가 없습니다. 아래에서 추가해 주세요."
            : "배정된 수급자가 없습니다. 기관 담당자에게 배정을 요청하세요."}
        </p>
      )}
      <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
        {recipients?.map((r) => (
          <li key={r.id}>
            <Link href={`/recipients/${r.id}`} className="flex min-h-16 items-center justify-between gap-3 px-4 py-3 hover:bg-paper">
              <span>
                <span className="text-xl font-semibold">{r.name}</span>
                {manager && (
                  <span className="mt-1 flex flex-wrap gap-1.5 text-sm text-muted">
                    {r.caregiver_names.length > 0 ? `담당 ${r.caregiver_names.join(", ")}` : <Badge tone="follow">담당 없음</Badge>}
                    {!r.consents.includes("health_record") && <Badge tone="risk">동의 없음</Badge>}
                  </span>
                )}
                {!manager && !r.consents.includes("health_record") && (
                  <span className="mt-1 block">
                    <Badge tone="risk">동의 없음</Badge>
                  </span>
                )}
              </span>
              <span aria-hidden className="text-2xl text-muted">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {manager && (
        <Sheet className="mt-8">
          <form onSubmit={add} className="flex flex-col gap-3">
            <Field label="수급자 추가 (가명)" name="name" maxLength={30} required placeholder="예: 김가상 어르신" />
            <Button type="submit" variant="secondary">
              추가
            </Button>
          </form>
        </Sheet>
      )}
    </>
  );
}
