import { useState } from "react";

import type { FollowupCard } from "@/lib/review";
import { TabbedSheet } from "./category";
import { Badge, Button } from "./ui";

const TEXTAREA = "w-full rounded-xl border border-line bg-sheet p-3 focus:border-pine focus:outline-none";

/** 검토 화면의 '이전 확인 사항' 섹션: 지난 방문에서 다시 확인하기로 한 일과 이번 녹음의 답 */
export function FollowupReview({
  fcards,
  onAccept,
  onDismiss,
  onRestore,
  onWrite,
  onEvidence,
}: {
  fcards: FollowupCard[];
  onAccept: (id: string) => void;
  onDismiss: (id: string) => void;
  onRestore: (id: string) => void;
  onWrite: (id: string, text: string) => void;
  onEvidence: (segmentIndex: number) => void;
}) {
  if (fcards.length === 0) return null;
  return (
    <section aria-label="이전 확인 사항">
      <h2 className="mb-1 text-lg font-bold">이전 확인 사항</h2>
      <p className="mb-3 text-sm text-muted">
        지난 방문에서 다시 확인하기로 한 일입니다. 이번 녹음에서 찾은 답을 확인해 주세요.
      </p>
      <ul className="flex flex-col gap-2">
        {fcards.map((f) => (
          <li key={f.itemId}>
            <FollowupItem
              key={f.state}
              card={f}
              onAccept={() => onAccept(f.itemId)}
              onDismiss={() => onDismiss(f.itemId)}
              onRestore={() => onRestore(f.itemId)}
              onWrite={(text) => onWrite(f.itemId, text)}
              onEvidence={
                f.suggestion?.segmentIndex != null
                  ? () => onEvidence(f.suggestion?.segmentIndex as number)
                  : undefined
              }
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function FollowupItem({
  card,
  onAccept,
  onDismiss,
  onRestore,
  onWrite,
  onEvidence,
}: {
  card: FollowupCard;
  onAccept: () => void;
  onDismiss: () => void;
  onRestore: () => void;
  onWrite: (text: string) => void;
  onEvidence?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(card.result);
  const dismissed = card.state === "dismissed";

  function save() {
    onWrite(text);
    setEditing(false);
  }

  return (
    <TabbedSheet category="followup" className={dismissed ? "opacity-50" : ""}>
      <p className="text-sm text-muted">{card.visitedOn} 방문에서</p>
      <p className="font-semibold">{card.content}</p>

      <div className="mt-3 rounded-lg bg-paper p-3">
        {card.state === "pending" && <Badge tone="follow">AI가 찾은 답, 확인 필요</Badge>}
        {card.state === "accepted" && <Badge tone="pine">확인 결과</Badge>}
        {dismissed && <Badge>이번 기록에서 제외</Badge>}

        {editing || (card.state === "open" && !dismissed) ? (
          <div className="mt-2 flex flex-col gap-2">
            {card.state === "open" && (
              <p className="text-sm text-muted">이번 녹음에서 답을 찾지 못했습니다. 확인했다면 직접 적어 주세요.</p>
            )}
            <textarea
              aria-label={`${card.content} 확인 결과`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              maxLength={1000}
              className={TEXTAREA}
            />
            <div className="flex gap-2">
              <Button variant="secondary" onClick={save} disabled={!text.trim()}>
                결과 남기기
              </Button>
              {editing && (
                <Button variant="ghost" onClick={() => setEditing(false)}>
                  취소
                </Button>
              )}
            </div>
          </div>
        ) : (
          card.result && <p className={`mt-2 text-lg ${dismissed ? "line-through" : ""}`}>{card.result}</p>
        )}

        {card.suggestion?.evidence && card.evidence && !editing && (
          <button
            type="button"
            onClick={onEvidence}
            disabled={!onEvidence}
            className="mt-2 block w-full rounded-md py-1 text-left text-muted enabled:hover:text-ink"
          >
            <span className="sr-only">근거 </span>
            <span className="bg-marker/70 box-decoration-clone px-0.5 text-ink">“{card.evidence}”</span>
            {onEvidence && <span className="ml-2 text-sm font-semibold text-pine">듣기</span>}
          </button>
        )}
        {card.suggestion && !card.suggestion.evidenceFound && (
          <p className="mt-2 text-sm font-medium text-risk">녹음에서 이 근거를 찾지 못했습니다. 꼭 확인해 주세요.</p>
        )}
      </div>

      {!editing && (
        <div className="mt-3 flex flex-wrap gap-2">
          {dismissed || (card.state === "accepted" && !card.suggestion) ? (
            <Button variant="ghost" onClick={onRestore}>
              되돌리기
            </Button>
          ) : null}
          {card.state === "pending" && <Button onClick={onAccept}>확인</Button>}
          {(card.state === "pending" || card.state === "accepted") && (
            <Button
              variant="secondary"
              onClick={() => {
                setText(card.result);
                setEditing(true);
              }}
            >
              수정
            </Button>
          )}
          {card.suggestion && !dismissed && (
            <Button variant="danger" onClick={onDismiss}>
              삭제
            </Button>
          )}
        </div>
      )}
    </TabbedSheet>
  );
}
