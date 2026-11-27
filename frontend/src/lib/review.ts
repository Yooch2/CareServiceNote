import type { BodyPart, Category, ConfirmBody, Draft, Mood, RiskTag } from "./types";

export type CardState = "pending" | "accepted" | "dismissed";

/** 검토 화면의 항목 하나. AI 초안 항목은 draftIndex가 있고, 직접 추가한 항목은 null. */
export interface Card {
  key: string;
  draftIndex: number | null;
  category: Category;
  content: string;
  evidence: string | null;
  evidenceFound: boolean;
  segmentIndex: number | null;
  speakerUncertain: boolean;
  riskTag: RiskTag | null;
  bodyPart: BodyPart | null;
  state: CardState;
}

export function cardsFromDraft(draft: Draft | null): Card[] {
  return (draft?.items ?? []).map((item, i) => ({
    key: `d${i}`,
    draftIndex: i,
    category: item.category,
    content: item.content,
    evidence: item.evidence,
    evidenceFound: item.evidence_found,
    segmentIndex: item.segment_index,
    speakerUncertain: item.speaker_uncertain,
    riskTag: item.risk_tag,
    bodyPart: item.body_part ?? null,
    state: "pending",
  }));
}

function update(cards: Card[], key: string, patch: Partial<Card>): Card[] {
  return cards.map((c) => (c.key === key ? { ...c, ...patch } : c));
}

export const accept = (cards: Card[], key: string) => update(cards, key, { state: "accepted" });
export const dismiss = (cards: Card[], key: string) => update(cards, key, { state: "dismissed" });
export const restore = (cards: Card[], key: string) => update(cards, key, { state: "pending" });

/** 수정해서 저장하면 사람이 확인한 것으로 본다. */
export function edit(
  cards: Card[],
  key: string,
  change: { category: Category; content: string; bodyPart?: BodyPart | null },
): Card[] {
  const content = change.content.trim();
  if (!content) return cards;
  const bodyPart = change.bodyPart === undefined ? {} : { bodyPart: change.bodyPart };
  return update(cards, key, { category: change.category, content, ...bodyPart, state: "accepted" });
}

export function addHuman(
  cards: Card[],
  key: string,
  category: Category,
  content: string,
): Card[] {
  const text = content.trim();
  if (!text) return cards;
  return [
    ...cards,
    {
      key,
      draftIndex: null,
      category,
      content: text,
      evidence: null,
      evidenceFound: false,
      segmentIndex: null,
      speakerUncertain: false,
      riskTag: null,
      bodyPart: null,
      state: "accepted",
    },
  ];
}

/**
 * 이전 방문의 '다음 확인' 사항. AI 제안이 있으면 pending(확인 필요)에서 시작하고,
 * 없으면 open(미입력)에서 시작해 직접 쓰면 accepted가 된다. open은 그대로 두고 확정해도 된다.
 */
export type FollowupState = "pending" | "accepted" | "dismissed" | "open";

export interface FollowupCard {
  itemId: string;
  content: string;
  visitedOn: string;
  suggestion: {
    result: string;
    evidence: string | null;
    evidenceFound: boolean;
    segmentIndex: number | null;
  } | null;
  result: string;
  evidence: string | null;
  state: FollowupState;
}

export function followupCardsFromDraft(draft: Draft | null): FollowupCard[] {
  const results = new Map((draft?.followup_results ?? []).map((r) => [r.item_id, r]));
  return (draft?.open_followups ?? []).map((f) => {
    const r = results.get(f.item_id);
    const suggestion = r
      ? { result: r.result, evidence: r.evidence, evidenceFound: r.evidence_found, segmentIndex: r.segment_index }
      : null;
    return {
      itemId: f.item_id,
      content: f.content,
      visitedOn: f.visited_on,
      suggestion,
      result: suggestion?.result ?? "",
      evidence: suggestion?.evidence ?? null,
      state: suggestion ? "pending" : "open",
    };
  });
}

function updateFollowup(fcards: FollowupCard[], id: string, patch: Partial<FollowupCard>): FollowupCard[] {
  return fcards.map((f) => (f.itemId === id ? { ...f, ...patch } : f));
}

export const acceptFollowup = (fcards: FollowupCard[], id: string) =>
  updateFollowup(fcards, id, { state: "accepted" });
export const dismissFollowup = (fcards: FollowupCard[], id: string) =>
  updateFollowup(fcards, id, { state: "dismissed" });

/** 처음 상태로: 제안이 있으면 제안 내용으로 확인 필요, 없으면 미입력 */
export function restoreFollowup(fcards: FollowupCard[], id: string): FollowupCard[] {
  return fcards.map((f) =>
    f.itemId === id
      ? {
          ...f,
          result: f.suggestion?.result ?? "",
          evidence: f.suggestion?.evidence ?? null,
          state: f.suggestion ? "pending" : "open",
        }
      : f,
  );
}

/** 결과를 직접 쓰거나 고친다. 근거는 AI 제안의 것을 유지한다. */
export function writeFollowup(fcards: FollowupCard[], id: string, text: string): FollowupCard[] {
  const result = text.trim();
  if (!result) return fcards;
  return updateFollowup(fcards, id, { result, state: "accepted" });
}

/**
 * 오늘 상태(식사량·기분). AI가 하나라도 제안했으면 확인 필요(pending)에서 시작한다.
 * 고르거나 바꾸면 확인한 것으로 본다. 언급이 없으면 비워 둔 채로 확정해도 된다.
 */
export interface StateCard {
  mealLevel: number | null;
  mood: Mood | null;
  mealEvidence: string | null;
  moodEvidence: string | null;
  suggested: boolean;
  state: "pending" | "accepted";
}

export function stateFromDraft(draft: Draft | null): StateCard {
  const s = draft?.state;
  const suggested = s?.meal_level != null || s?.mood != null;
  return {
    mealLevel: s?.meal_level ?? null,
    mood: s?.mood ?? null,
    mealEvidence: s?.meal_evidence ?? null,
    moodEvidence: s?.mood_evidence ?? null,
    suggested,
    state: suggested ? "pending" : "accepted",
  };
}

export const acceptState = (sc: StateCard): StateCard => ({ ...sc, state: "accepted" });

export function setState(sc: StateCard, change: { mealLevel?: number | null; mood?: Mood | null }): StateCard {
  return { ...sc, ...change, state: "accepted" };
}

const NO_STATE: StateCard = stateFromDraft(null);

export const remaining = (cards: Card[], fcards: FollowupCard[] = [], sc: StateCard = NO_STATE) =>
  cards.filter((c) => c.state === "pending").length +
  fcards.filter((f) => f.state === "pending").length +
  (sc.state === "pending" ? 1 : 0);

export const canConfirm = (cards: Card[], fcards: FollowupCard[] = [], sc: StateCard = NO_STATE) =>
  remaining(cards, fcards, sc) === 0 &&
  (cards.some((c) => c.state === "accepted") || fcards.some((f) => f.state === "accepted"));

export function buildConfirmBody(cards: Card[], fcards: FollowupCard[] = [], sc: StateCard = NO_STATE): ConfirmBody {
  if (remaining(cards, fcards, sc) > 0) throw new Error("확인하지 않은 AI 항목이 있습니다");
  return {
    items: cards
      .filter((c) => c.state === "accepted")
      .map((c) => ({
        draft_index: c.draftIndex,
        category: c.category,
        content: c.content,
        evidence: c.evidence,
        speaker_uncertain: c.speakerUncertain,
        risk_tag: c.riskTag,
        body_part: c.bodyPart,
      })),
    dismissed_draft_indexes: cards.flatMap((c) =>
      c.state === "dismissed" && c.draftIndex !== null ? [c.draftIndex] : [],
    ),
    followup_checks: fcards
      .filter((f) => f.state === "accepted")
      .map((f) => ({ item_id: f.itemId, result: f.result, evidence: f.evidence })),
    dismissed_followup_items: fcards.filter((f) => f.state === "dismissed").map((f) => f.itemId),
    meal_level: sc.mealLevel,
    mood: sc.mood,
  };
}
