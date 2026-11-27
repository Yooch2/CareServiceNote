import { useRef, useState, type SubmitEvent } from "react";

import { ApiError, postJson } from "@/lib/api";
import { CATEGORY_LABEL, CATEGORY_ORDER, errorMessage, RISK_LABEL, TOPIC_LABEL } from "@/lib/labels";
import {
  accept,
  acceptFollowup,
  addHuman,
  buildConfirmBody,
  canConfirm,
  cardsFromDraft,
  dismiss,
  dismissFollowup,
  edit,
  followupCardsFromDraft,
  remaining,
  restore,
  restoreFollowup,
  writeFollowup,
  type Card,
} from "@/lib/review";
import type { Category, VisitRecord } from "@/lib/types";
import { CategoryHeading, TabbedSheet } from "./category";
import { FollowupReview } from "./followup-review";
import { Transcript } from "./transcript";
import { Badge, Button, Notice, Sheet } from "./ui";

const SELECT = "min-h-12 rounded-xl border border-line bg-sheet px-3";
const TEXTAREA = "rounded-xl border border-line bg-sheet p-3 focus:border-pine focus:outline-none";

export function ReviewPanel({
  record,
  onConfirmed,
}: {
  record: VisitRecord;
  onConfirmed: (r: VisitRecord) => void;
}) {
  const [cards, setCards] = useState(() => cardsFromDraft(record.draft));
  const [fcards, setFcards] = useState(() => followupCardsFromDraft(record.draft));
  const [active, setActive] = useState<number | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const nextKey = useRef(0);
  const segments = record.transcript_segments ?? [];
  const left = remaining(cards, fcards);
  const missing = record.draft?.missing_topics ?? [];

  function play(index: number) {
    setActive(index);
    const el = audioRef.current;
    const seg = segments[index];
    if (!el || !seg) return;
    el.currentTime = seg.start_ms / 1000;
    void el.play().catch(() => undefined);
  }

  function add(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const form = new FormData(formEl);
    nextKey.current += 1;
    setCards((c) =>
      addHuman(c, `h${nextKey.current}`, form.get("category") as Category, String(form.get("content") ?? "")),
    );
    formEl.reset();
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      onConfirmed(await postJson<VisitRecord>(`/records/${record.id}/confirm`, buildConfirmBody(cards, fcards)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "확정하지 못했습니다. 연결을 확인하고 다시 눌러 주세요.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 pb-32">
      {record.status === "failed" && (
        <Notice tone="error">{errorMessage(record.error_code)} 아래에서 직접 작성해 확정할 수 있습니다.</Notice>
      )}
      {missing.length > 0 && (
        <Notice tone="warn">
          <p className="font-semibold">언급 없음: {missing.map((t) => TOPIC_LABEL[t]).join("·")}</p>
          <p className="text-sm">녹음에서 이야기가 없었습니다. 확인한 내용이 있다면 직접 추가해 주세요.</p>
        </Notice>
      )}

      {(record.has_audio || segments.length > 0 || record.transcript) && (
        <Sheet>
          <h2 className="mb-2 font-semibold">녹음과 전사문</h2>
          {record.has_audio && (
            <audio
              ref={audioRef}
              controls
              preload="metadata"
              src={`/api/records/${record.id}/audio`}
              className="mb-3 w-full"
            />
          )}
          {segments.length > 0 ? (
            <Transcript segments={segments} active={active} approximate={record.approximate_times} onSelect={play} />
          ) : (
            record.transcript && <p>{record.transcript}</p>
          )}
        </Sheet>
      )}

      <FollowupReview
        fcards={fcards}
        onAccept={(id) => setFcards((f) => acceptFollowup(f, id))}
        onDismiss={(id) => setFcards((f) => dismissFollowup(f, id))}
        onRestore={(id) => setFcards((f) => restoreFollowup(f, id))}
        onWrite={(id, text) => setFcards((f) => writeFollowup(f, id, text))}
        onEvidence={play}
      />

      {CATEGORY_ORDER.map((category) => {
        const group = cards.filter((c) => c.category === category);
        if (group.length === 0) return null;
        return (
          <section key={category} aria-label={CATEGORY_LABEL[category]}>
            <CategoryHeading category={category} count={group.length} />
            <ul className="flex flex-col gap-2">
              {group.map((card) => (
                <li key={card.key}>
                  {editing === card.key ? (
                    <EditCard
                      card={card}
                      onCancel={() => setEditing(null)}
                      onSave={(change) => {
                        setCards((c) => edit(c, card.key, change));
                        setEditing(null);
                      }}
                    />
                  ) : (
                    <ItemCard
                      card={card}
                      onEvidence={card.segmentIndex !== null ? () => play(card.segmentIndex as number) : undefined}
                      onAccept={() => setCards((c) => accept(c, card.key))}
                      onEdit={() => setEditing(card.key)}
                      onDismiss={() => setCards((c) => dismiss(c, card.key))}
                      onRestore={() => setCards((c) => restore(c, card.key))}
                    />
                  )}
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      <Sheet>
        <form onSubmit={add} className="flex flex-col gap-3">
          <h2 className="font-semibold">직접 추가</h2>
          <select name="category" aria-label="분류" className={SELECT}>
            {CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </select>
          <textarea name="content" aria-label="내용" required maxLength={1000} rows={2} className={TEXTAREA} />
          <Button type="submit" variant="secondary">
            항목 추가
          </Button>
        </form>
      </Sheet>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="fixed inset-x-0 bottom-0 border-t border-line bg-sheet">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <p aria-live="polite" className={left > 0 ? "font-semibold text-follow" : "text-muted"}>
            {left > 0 ? `확인이 필요한 AI 항목 ${left}개` : "모든 AI 항목을 확인했습니다"}
          </p>
          <Button onClick={confirm} disabled={!canConfirm(cards, fcards) || busy}>
            확정하기
          </Button>
        </div>
      </div>
    </div>
  );
}

function ItemCard({
  card,
  onEvidence,
  onAccept,
  onEdit,
  onDismiss,
  onRestore,
}: {
  card: Card;
  onEvidence?: () => void;
  onAccept: () => void;
  onEdit: () => void;
  onDismiss: () => void;
  onRestore: () => void;
}) {
  const dismissed = card.state === "dismissed";
  const aiPending = card.draftIndex !== null && card.state === "pending";
  return (
    <TabbedSheet
      category={card.category}
      className={`${dismissed ? "opacity-50" : ""} ${card.riskTag && !dismissed ? "outline-2 outline-risk/60" : ""}`}
    >
      {(aiPending || card.state === "accepted" || card.riskTag || card.speakerUncertain) && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {aiPending && <Badge tone="follow">AI 초안, 확인 필요</Badge>}
          {card.state === "accepted" && <Badge tone="pine">확인함</Badge>}
          {card.riskTag && <Badge tone="risk">{RISK_LABEL[card.riskTag]} 주의</Badge>}
          {card.speakerUncertain && <Badge>누가 한 말인지 불확실</Badge>}
        </div>
      )}
      <p className={`text-lg ${dismissed ? "line-through" : ""}`}>{card.content}</p>
      {card.evidence && (
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
      {card.draftIndex !== null && !card.evidenceFound && (
        <p className="mt-2 text-sm font-medium text-risk">녹음에서 이 근거를 찾지 못했습니다. 내용이 맞는지 꼭 확인해 주세요.</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {dismissed ? (
          <Button variant="ghost" onClick={onRestore}>
            되돌리기
          </Button>
        ) : (
          <>
            {card.state === "pending" && <Button onClick={onAccept}>확인</Button>}
            <Button variant="secondary" onClick={onEdit}>
              수정
            </Button>
            <Button variant="danger" onClick={onDismiss}>
              삭제
            </Button>
          </>
        )}
      </div>
    </TabbedSheet>
  );
}

function EditCard({
  card,
  onSave,
  onCancel,
}: {
  card: Card;
  onSave: (change: { category: Category; content: string }) => void;
  onCancel: () => void;
}) {
  const [category, setCategory] = useState(card.category);
  const [content, setContent] = useState(card.content);
  return (
    <TabbedSheet category={category} className="flex flex-col gap-3">
      <select
        aria-label="분류"
        value={category}
        onChange={(e) => setCategory(e.target.value as Category)}
        className={SELECT}
      >
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
        className={TEXTAREA}
      />
      <div className="flex gap-2">
        <Button onClick={() => onSave({ category, content })} disabled={!content.trim()}>
          저장
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          취소
        </Button>
      </div>
    </TabbedSheet>
  );
}
