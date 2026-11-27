import type { Category, ConfirmBody, Draft, RiskTag } from "./types";

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
  change: { category: Category; content: string },
): Card[] {
  const content = change.content.trim();
  if (!content) return cards;
  return update(cards, key, { category: change.category, content, state: "accepted" });
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
      state: "accepted",
    },
  ];
}

export const remaining = (cards: Card[]) => cards.filter((c) => c.state === "pending").length;

export const canConfirm = (cards: Card[]) =>
  remaining(cards) === 0 && cards.some((c) => c.state === "accepted");

export function buildConfirmBody(cards: Card[]): ConfirmBody {
  if (remaining(cards) > 0) throw new Error("확인하지 않은 AI 항목이 있습니다");
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
      })),
    dismissed_draft_indexes: cards.flatMap((c) =>
      c.state === "dismissed" && c.draftIndex !== null ? [c.draftIndex] : [],
    ),
  };
}
