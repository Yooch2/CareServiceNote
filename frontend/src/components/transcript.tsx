import type { Segment } from "@/lib/types";

/** 전사문 구간 목록. 누르면 그 구간부터 재생하고, 근거로 연결된 구간은 형광펜처럼 칠한다. */
export function Transcript({
  segments,
  active,
  approximate,
  onSelect,
}: {
  segments: Segment[];
  active: number | null;
  approximate: boolean;
  onSelect: (index: number) => void;
}) {
  return (
    <div>
      <ol className="flex flex-col">
        {segments.map((s, i) => (
          <li key={i}>
            <button
              type="button"
              aria-current={active === i ? "true" : undefined}
              onClick={() => onSelect(i)}
              className="flex w-full gap-3 rounded-md px-2 py-2 text-left hover:bg-paper"
            >
              <span className="w-10 shrink-0 pt-0.5 text-sm text-muted">{formatTime(s.start_ms)}</span>
              <span className={active === i ? "bg-marker box-decoration-clone px-0.5" : ""}>{s.text}</span>
            </button>
          </li>
        ))}
      </ol>
      {approximate && <p className="mt-2 text-sm text-muted">재생 위치는 대략적입니다.</p>}
    </div>
  );
}

function formatTime(ms: number): string {
  const sec = Math.floor(ms / 1000);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}
