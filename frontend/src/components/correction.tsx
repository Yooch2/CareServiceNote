"use client";

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import {
  BODY_PART_LABEL,
  BODY_PARTS,
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  MEAL_LABEL,
  MOOD_LABEL,
  MOODS,
} from "@/lib/labels";
import type { BodyPart, Category, Mood, RecordItem, Revision, VisitRecord } from "@/lib/types";
import { Button, Notice } from "./ui";

const INPUT = "min-h-12 rounded-xl border border-line bg-sheet px-3 text-base font-normal";

function useSave(onSaved: (r: VisitRecord) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save(path: string, body: unknown) {
    setBusy(true);
    setError(null);
    try {
      onSaved(await api<VisitRecord>(path, { method: "PATCH", body: JSON.stringify(body) }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "연결을 확인하고 다시 눌러 주세요.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, save };
}

function ReasonField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-sm font-medium">
      정정 사유 (필수)
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={200}
        placeholder="예: 녹음을 다시 들어 보니 허리였음"
        className={INPUT}
      />
    </label>
  );
}

/** 확정 항목 정정: 분류·내용·불편 부위를 고치고 사유를 남긴다 */
export function ItemCorrectionForm({
  recordId,
  item,
  onSaved,
  onCancel,
}: {
  recordId: string;
  item: RecordItem;
  onSaved: (r: VisitRecord) => void;
  onCancel: () => void;
}) {
  const [category, setCategory] = useState<Category>(item.category);
  const [content, setContent] = useState(item.content);
  const [bodyPart, setBodyPart] = useState<BodyPart | null>(item.body_part);
  const [reason, setReason] = useState("");
  const { busy, error, save } = useSave(onSaved);
  return (
    <div className="flex flex-col gap-3">
      <select aria-label="분류" value={category} onChange={(e) => setCategory(e.target.value as Category)} className={INPUT}>
        {CATEGORY_ORDER.map((c) => (
          <option key={c} value={c}>
            {CATEGORY_LABEL[c]}
          </option>
        ))}
      </select>
      <textarea
        aria-label="내용"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={3}
        maxLength={1000}
        className="rounded-xl border border-line bg-sheet p-3"
      />
      <label className="flex flex-col gap-1 text-sm font-medium">
        불편을 말한 부위
        <select value={bodyPart ?? ""} onChange={(e) => setBodyPart((e.target.value || null) as BodyPart | null)} className={INPUT}>
          <option value="">없음</option>
          {BODY_PARTS.map((b) => (
            <option key={b} value={b}>
              {BODY_PART_LABEL[b]}
            </option>
          ))}
        </select>
      </label>
      <ReasonField value={reason} onChange={setReason} />
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button
          disabled={busy || !reason.trim() || !content.trim()}
          onClick={() =>
            save(`/records/${recordId}/items/${item.id}`, {
              category,
              content,
              body_part: bodyPart,
              risk_tag: item.risk_tag,
              reason,
            })
          }
        >
          정정 저장
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          취소
        </Button>
      </div>
    </div>
  );
}

/** 오늘 상태(식사량·기분) 정정 */
export function StateCorrectionForm({
  record,
  onSaved,
  onCancel,
}: {
  record: VisitRecord;
  onSaved: (r: VisitRecord) => void;
  onCancel: () => void;
}) {
  const [meal, setMeal] = useState<number | null>(record.meal_level);
  const [mood, setMood] = useState<Mood | null>(record.mood);
  const [reason, setReason] = useState("");
  const { busy, error, save } = useSave(onSaved);
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-sheet p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm font-medium">
          식사량
          <select value={meal ?? ""} onChange={(e) => setMeal(e.target.value === "" ? null : Number(e.target.value))} className={INPUT}>
            <option value="">언급 없음</option>
            {MEAL_LABEL.map((label, level) => (
              <option key={level} value={level}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          기분
          <select value={mood ?? ""} onChange={(e) => setMood((e.target.value || null) as Mood | null)} className={INPUT}>
            <option value="">언급 없음</option>
            {MOODS.map((m) => (
              <option key={m} value={m}>
                {MOOD_LABEL[m]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ReasonField value={reason} onChange={setReason} />
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button
          disabled={busy || !reason.trim()}
          onClick={() => save(`/records/${record.id}/state`, { meal_level: meal, mood, reason })}
        >
          정정 저장
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          취소
        </Button>
      </div>
    </div>
  );
}

function describe(values: Record<string, unknown>): string {
  if ("content" in values) {
    const part = values.body_part ? ` (${BODY_PART_LABEL[values.body_part as BodyPart]} 불편)` : "";
    return `[${CATEGORY_LABEL[values.category as Category]}] ${String(values.content)}${part}`;
  }
  const meal = values.meal_level == null ? "언급 없음" : MEAL_LABEL[values.meal_level as number];
  const mood = values.mood == null ? "언급 없음" : MOOD_LABEL[values.mood as Mood];
  return `식사량 ${meal} · 기분 ${mood}`;
}

/** 정정 이력: 언제, 누가, 무엇에서 무엇으로, 왜 */
export function RevisionList({ revisions }: { revisions: Revision[] }) {
  if (revisions.length === 0) return null;
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-muted">정정 이력 {revisions.length}건</summary>
      <ol className="mt-1 flex flex-col gap-2">
        {revisions.map((r) => (
          <li key={r.id} className="border-l-2 border-line pl-3">
            <p className="text-muted">
              {new Date(r.created_at).toLocaleString("ko-KR")} · {r.user_name}
            </p>
            <p>
              <span className="text-muted">이전: </span>
              <s>{describe(r.before)}</s>
            </p>
            <p>
              <span className="text-muted">사유: </span>
              {r.reason}
            </p>
          </li>
        ))}
      </ol>
    </details>
  );
}
