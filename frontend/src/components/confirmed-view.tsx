import { CATEGORY_LABEL, CATEGORY_ORDER, ORIGIN_LABEL, RISK_LABEL } from "@/lib/labels";
import type { VisitRecord } from "@/lib/types";
import { CategoryHeading, TabbedSheet } from "./category";
import { Badge } from "./ui";

export function ConfirmedView({ record }: { record: VisitRecord }) {
  return (
    <div className="flex flex-col gap-6">
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
