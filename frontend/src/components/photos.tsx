"use client";

import { useRef, useState } from "react";

import { api, ApiError, errorDetail } from "@/lib/api";
import type { VisitRecord } from "@/lib/types";
import { Button, Notice } from "./ui";

type Photo = VisitRecord["photos"][number];

/** 기록 사진: 검토 중에는 붙이고 지울 수 있고, 확정 뒤에는 보기만 한다. 보호자에게는 보내지 않는다. */
export function Photos({
  record,
  editable,
  max = 3,
}: {
  record: VisitRecord;
  editable: boolean;
  max?: number;
}) {
  const [photos, setPhotos] = useState<Photo[]>(record.photos);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  if (!editable && photos.length === 0) return null;

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("photo", file);
      const res = await fetch(`/api/records/${record.id}/photos`, { method: "POST", body: form, credentials: "same-origin" });
      if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
      const added = (await res.json()) as Photo;
      setPhotos((p) => [...p, added]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "사진을 올리지 못했습니다. 연결을 확인해 주세요.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api(`/records/${record.id}/photos/${id}`, { method: "DELETE" });
      setPhotos((p) => p.filter((x) => x.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "사진을 지우지 못했습니다.");
    }
  }

  return (
    <section aria-label="사진" className="rounded-lg border border-line bg-sheet p-4">
      <h2 className="mb-1 font-semibold">사진 {photos.length > 0 && <span className="font-normal text-muted">{photos.length}장</span>}</h2>
      {editable && (
        <p className="mb-3 text-sm text-muted">
          상처·피부 상태처럼 말로 남기기 어려운 것만 찍어 주세요. 얼굴과 집 주소가 보이지 않게 해 주세요. 위치 정보는 지우고 저장하며,
          센터 직원만 봅니다. 최대 {max}장.
        </p>
      )}
      {photos.length > 0 && (
        <ul className="mb-3 grid grid-cols-3 gap-2">
          {photos.map((p, i) => (
            <li key={p.id} className="flex flex-col gap-1">
              {p.available ? (
                // eslint-disable-next-line @next/next/no-img-element -- 인증이 필요한 사진이라 이미지 최적화 서버를 거치지 않는다
                <img
                  src={`/api/records/${record.id}/photos/${p.id}`}
                  alt={`기록 사진 ${i + 1}`}
                  className="aspect-square w-full rounded-md border border-line object-cover"
                />
              ) : (
                <span className="flex aspect-square items-center justify-center rounded-md border border-dashed border-line text-center text-xs text-muted">
                  보관 기간이 지나 삭제됨
                </span>
              )}
              {editable && (
                <Button variant="ghost" className="min-h-9 text-sm" onClick={() => remove(p.id)}>
                  지우기
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && photos.length < max && (
        <label className="inline-flex min-h-12 cursor-pointer items-center rounded-xl border border-line px-5 font-semibold hover:border-pine has-focus-visible:outline-3 has-focus-visible:outline-pine">
          {busy ? "올리는 중…" : "사진 붙이기"}
          <input
            ref={input}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            className="sr-only"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
        </label>
      )}
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </section>
  );
}
