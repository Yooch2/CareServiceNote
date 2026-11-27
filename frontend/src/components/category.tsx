import type { ReactNode } from "react";

import { CATEGORY_LABEL } from "@/lib/labels";
import type { Category } from "@/lib/types";

// 수첩 색인 탭처럼 항목 왼쪽에 분류 색을 붙인다. Tailwind가 찾을 수 있게 클래스 이름을 그대로 쓴다.
const TAB: Record<Category, { edge: string; label: string }> = {
  remark: { edge: "border-l-remark", label: "bg-remark" },
  observation: { edge: "border-l-observe", label: "bg-observe" },
  followup: { edge: "border-l-follow", label: "bg-follow" },
};

export function CategoryHeading({ category, count }: { category: Category; count: number }) {
  return (
    <h2 className="mb-2 flex items-baseline gap-2">
      <span className={`rounded-t-md rounded-br-md px-3 py-1 font-bold text-white ${TAB[category].label}`}>
        {CATEGORY_LABEL[category]}
      </span>
      <span className="text-sm text-muted">{count}개</span>
    </h2>
  );
}

export function TabbedSheet({
  category,
  className = "",
  children,
}: {
  category: Category;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`rounded-r-lg border border-l-[6px] border-line bg-sheet p-4 ${TAB[category].edge} ${className}`}>
      {children}
    </div>
  );
}
