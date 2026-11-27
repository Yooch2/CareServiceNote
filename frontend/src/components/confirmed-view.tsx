"use client";

import Link from "next/link";
import { useState } from "react";

import { BODY_PART_LABEL, CATEGORY_LABEL, CATEGORY_ORDER, MEAL_LABEL, MOOD_LABEL, ORIGIN_LABEL, RISK_LABEL } from "@/lib/labels";
import type { VisitRecord } from "@/lib/types";
import { useUser } from "./auth-gate";
import { CategoryHeading, TabbedSheet } from "./category";
import { ItemCorrectionForm, RevisionList, StateCorrectionForm } from "./correction";
import { Badge, Button } from "./ui";

export function ConfirmedView({ record, onChange }: { record: VisitRecord; onChange: (r: VisitRecord) => void }) {
  const user = useUser();
  // 작성자(지금 배정 중이라 이 화면을 볼 수 있음)와 기관 담당자만 정정한다
  const canCorrect = user.role === "manager" || (user.role === "caregiver" && record.caregiver_id === user.id);
  const [editing, setEditing] = useState<string | null>(null); // 항목 id 또는 "state"
  const saved = (r: VisitRecord) => {
    setEditing(null);
    onChange(r);
  };
  const stateRevisions = record.revisions.filter((r) => r.item_id === null);
  return (
    <div className="flex flex-col gap-6">
      {editing === "state" && <StateCorrectionForm record={record} onSaved={saved} onCancel={() => setEditing(null)} />}
      {editing !== "state" && (record.meal_level !== null || record.mood !== null || canCorrect) && (
        <div>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1" aria-label="오늘 상태">
            {record.meal_level !== null && (
              <span>
                <span className="text-muted">식사량 </span>
                <strong>{MEAL_LABEL[record.meal_level]}</strong>
              </span>
            )}
            {record.mood !== null && (
              <span>
                <span className="text-muted">기분 </span>
                <strong>{MOOD_LABEL[record.mood]}</strong>
              </span>
            )}
            {record.meal_level === null && record.mood === null && <span className="text-muted">식사량·기분 언급 없음</span>}
            {stateRevisions.length > 0 && <Badge tone="follow">정정됨</Badge>}
            {canCorrect && (
              <Button variant="ghost" className="min-h-9 px-2 text-sm" onClick={() => setEditing("state")}>
                상태 정정
              </Button>
            )}
          </p>
          <RevisionList revisions={stateRevisions} />
        </div>
      )}
      {record.followup_checks.length > 0 && (
        <section aria-label="확인한 이전 사항">
          <h2 className="mb-2 text-lg font-bold">확인한 이전 사항</h2>
          <ul className="flex flex-col gap-2">
            {record.followup_checks.map((c) => (
              <li key={c.followup_item_id}>
                <TabbedSheet category="followup">
                  <Link href={`/records/${c.followup_record_id}`} className="text-sm text-muted underline underline-offset-4">
                    {c.followup_visited_on} 방문에서
                  </Link>
                  <p className="font-semibold">{c.followup_content}</p>
                  <p className="mt-2 text-lg">{c.result}</p>
                  {c.evidence && (
                    <p className="mt-1 text-muted">
                      <span className="sr-only">근거 </span>“{c.evidence}”
                    </p>
                  )}
                  <div className="mt-2">
                    <Badge>{ORIGIN_LABEL[c.origin]}</Badge>
                  </div>
                </TabbedSheet>
              </li>
            ))}
          </ul>
        </section>
      )}
      {CATEGORY_ORDER.map((category) => {
        const items = record.items.filter((i) => i.category === category);
        if (items.length === 0) return null;
        return (
          <section key={category} aria-label={CATEGORY_LABEL[category]}>
            <CategoryHeading category={category} count={items.length} />
            <ul className="flex flex-col gap-2">
              {items.map((item) => (
                <li key={item.id}>
                  <TabbedSheet category={category}>
                    {editing === item.id ? (
                      <ItemCorrectionForm recordId={record.id} item={item} onSaved={saved} onCancel={() => setEditing(null)} />
                    ) : (
                      <>
                        <p className="text-lg">{item.content}</p>
                        {item.evidence && (
                          <p className="mt-2 text-muted">
                            <span className="sr-only">근거 </span>“{item.evidence}”
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {item.risk_tag && <Badge tone="risk">{RISK_LABEL[item.risk_tag]} 주의</Badge>}
                          {item.body_part && <Badge>{BODY_PART_LABEL[item.body_part]} 불편</Badge>}
                          <Badge>{ORIGIN_LABEL[item.origin]}</Badge>
                          {record.revisions.some((r) => r.item_id === item.id) && <Badge tone="follow">정정됨</Badge>}
                          {canCorrect && (
                            <Button variant="ghost" className="min-h-8 px-2 text-sm" onClick={() => setEditing(item.id)}>
                              정정
                            </Button>
                          )}
                        </div>
                        <RevisionList revisions={record.revisions.filter((r) => r.item_id === item.id)} />
                        {item.category === "followup" &&
                          (item.check ? (
                            <Link
                              href={`/records/${item.check.record_id}`}
                              className="mt-3 block rounded-lg bg-pine/5 px-3 py-2 hover:bg-pine/10"
                            >
                              <span className="text-sm font-semibold text-pine">확인 완료 · {item.check.visited_on}</span>
                              <span className="block">{item.check.result}</span>
                            </Link>
                          ) : (
                            <p className="mt-3 text-sm font-medium text-follow">아직 확인 전</p>
                          ))}
                      </>
                    )}
                  </TabbedSheet>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {record.transcript && (
        <details className="rounded-lg border border-line bg-sheet p-4">
          <summary className="min-h-8 cursor-pointer font-semibold">전사문 보기</summary>
          <p className="mt-2 text-muted">{record.transcript}</p>
        </details>
      )}
    </div>
  );
}
