"use client";

import Link from "next/link";
import { useEffect, useState, type SubmitEvent } from "react";

import { api, ApiError, postJson } from "@/lib/api";
import type { Recipient } from "@/lib/types";
import { Button, Field, Loading, Notice, PageTitle, Sheet } from "./ui";

export function RecipientList() {
  const [recipients, setRecipients] = useState<Recipient[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Recipient[]>("/recipients")
      .then(setRecipients)
      .catch(() => setError("수급자 목록을 불러오지 못했습니다. 새로고침해 주세요."));
  }, []);

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

  return (
    <>
      <PageTitle sub="오늘 방문할 어르신을 고르세요">수급자</PageTitle>
      {error && <Notice tone="error">{error}</Notice>}
      {recipients === null && !error && <Loading />}
      {recipients?.length === 0 && <p className="text-muted">아직 등록된 수급자가 없습니다. 아래에서 추가해 주세요.</p>}
      <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
        {recipients?.map((r) => (
          <li key={r.id}>
            <Link href={`/recipients/${r.id}`} className="flex min-h-16 items-center justify-between px-4 text-xl font-semibold hover:bg-paper">
              {r.name}
              <span aria-hidden className="text-2xl text-muted">›</span>
            </Link>
          </li>
        ))}
      </ul>
      <Sheet className="mt-8">
        <form onSubmit={add} className="flex flex-col gap-3">
          <Field label="수급자 추가 (가명)" name="name" maxLength={30} required placeholder="예: 김가상 어르신" />
          <Button type="submit" variant="secondary">
            추가
          </Button>
        </form>
      </Sheet>
    </>
  );
}
