import Link from "next/link";

import { CATEGORY_LABEL, CATEGORY_ORDER, ORIGIN_LABEL, RISK_LABEL } from "@/lib/labels";
import type { VisitRecord } from "@/lib/types";
import { CategoryHeading, TabbedSheet } from "./category";
import { Badge } from "./ui";

export function ConfirmedView({ record }: { record: VisitRecord }) {
  return (
    <div className="flex flex-col gap-6">
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
                    <p className="text-lg">{item.content}</p>
                    {item.evidence && (
                      <p className="mt-2 text-muted">
                        <span className="sr-only">근거 </span>“{item.evidence}”
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.risk_tag && <Badge tone="risk">{RISK_LABEL[item.risk_tag]} 주의</Badge>}
                      <Badge>{ORIGIN_LABEL[item.origin]}</Badge>
                    </div>
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
