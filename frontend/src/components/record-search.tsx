"use client";

import Link from "next/link";
import { useState, type SubmitEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABEL, CATEGORY_ORDER } from "@/lib/labels";
import type { SearchHit } from "@/lib/types";
import { Button, Notice } from "./ui";

const KIND_LABEL: Record<SearchHit["kind"], string> = { item: "", check: "확인 결과", transcript: "전사문" };

/** 수급자 기록 검색: 확정된 항목, 확인 결과, 전사문 */
export function RecordSearch({ recipientId }: { recipientId: string }) {
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function search(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const q = String(form.get("q") ?? "").trim();
    const params = new URLSearchParams({ q });
    const category = String(form.get("category") ?? "");
    if (category) params.set("category", category);
    setError(null);
    try {
      setHits(await api<SearchHit[]>(`/recipients/${recipientId}/search?${params}`));
      setQuery(q);
    } catch (err) {
      setHits(null);
      setError(err instanceof ApiError ? err.message : "검색하지 못했습니다. 연결을 확인해 주세요.");
    }
  }

  return (
    <section aria-label="기록 검색">
      <h2 className="mb-2 text-lg font-bold">기록 검색</h2>
      <form onSubmit={search} role="search" className="flex flex-wrap gap-2">
        <input
          name="q"
          aria-label="검색어"
          placeholder="예: 무릎, 산책"
          minLength={2}
          maxLength={50}
          required
          className="min-h-12 min-w-0 flex-1 rounded-xl border border-line bg-sheet px-4 focus:border-pine focus:outline-none"
        />
        <select name="category" aria-label="분류" className="min-h-12 rounded-xl border border-line bg-sheet px-3">
          <option value="">전체</option>
          {CATEGORY_ORDER.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABEL[c]}
            </option>
          ))}
        </select>
        <Button type="submit" variant="secondary">
          찾기
        </Button>
      </form>
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {hits && hits.length === 0 && <p className="mt-3 text-muted">“{query}”이 들어간 확정 기록이 없습니다.</p>}
      {hits && hits.length > 0 && (
        <ul className="mt-3 flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
          {hits.map((h, i) => (
            <li key={`${h.record_id}-${h.kind}-${h.item_id ?? i}`}>
              <Link href={`/records/${h.record_id}`} className="block px-4 py-3 hover:bg-paper">
                <span className="text-sm text-muted">
                  {h.visited_on} · {h.category ? CATEGORY_LABEL[h.category] : KIND_LABEL[h.kind]}
                </span>
                <span className="block">
                  <Highlight text={h.text} query={query} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Highlight({ text, query }: { text: string; query: string }) {
  const at = text.toLowerCase().indexOf(query.toLowerCase());
  if (!query || at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="bg-marker px-0.5 text-ink">{text.slice(at, at + query.length)}</mark>
      {text.slice(at + query.length)}
    </>
  );
}
