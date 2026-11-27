import assert from "node:assert/strict";
import { test } from "node:test";

import {
  accept,
  addHuman,
  buildConfirmBody,
  canConfirm,
  cardsFromDraft,
  dismiss,
  edit,
  remaining,
  restore,
} from "./review.ts";
import type { Draft } from "./types";

const draft: Draft = {
  items: [
    {
      category: "remark",
      content: "오른쪽 무릎이 불편하다",
      evidence: "무릎이 좀 불편하다고",
      evidence_found: true,
      segment_index: 0,
      speaker_uncertain: false,
      risk_tag: "pain",
    },
    {
      category: "followup",
      content: "산책 의향 다시 여쭙기",
      evidence: null,
      evidence_found: false,
      segment_index: null,
      speaker_uncertain: true,
      risk_tag: null,
    },
  ],
  missing_topics: ["toileting"],
};

test("초안 항목은 모두 확인 필요 상태로 시작한다", () => {
  const cards = cardsFromDraft(draft);
  assert.deepEqual(
    cards.map((c) => [c.draftIndex, c.state]),
    [
      [0, "pending"],
      [1, "pending"],
    ],
  );
  assert.equal(remaining(cards), 2);
  assert.equal(canConfirm(cards), false);
  assert.deepEqual(cardsFromDraft(null), []);
});

test("확인·삭제·되돌리기에 따라 남은 개수가 바뀐다", () => {
  let cards = cardsFromDraft(draft);
  cards = accept(cards, cards[0].key);
  assert.equal(remaining(cards), 1);
  cards = dismiss(cards, cards[1].key);
  assert.equal(remaining(cards), 0);
  assert.equal(canConfirm(cards), true);
  cards = restore(cards, cards[1].key);
  assert.equal(remaining(cards), 1);
});

test("수정하면 확인한 것으로 본다", () => {
  let cards = cardsFromDraft(draft);
  cards = edit(cards, cards[1].key, { category: "observation", content: "  산책을 원하셨다 " });
  assert.equal(cards[1].state, "accepted");
  assert.equal(cards[1].category, "observation");
  assert.equal(cards[1].content, "산책을 원하셨다");
  assert.equal(edit(cards, cards[0].key, { category: "remark", content: "  " }), cards);
});

test("모두 삭제하면 남길 항목이 없어 확정할 수 없다", () => {
  let cards = cardsFromDraft(draft);
  cards = dismiss(dismiss(cards, cards[0].key), cards[1].key);
  assert.equal(canConfirm(cards), false);
  cards = addHuman(cards, "h1", "observation", "식사를 다 하셨다");
  assert.equal(canConfirm(cards), true);
});

test("빈 내용으로 직접 추가하면 무시한다", () => {
  assert.deepEqual(addHuman([], "h1", "remark", "   "), []);
});

test("확정 요청 본문: 채택 항목과 삭제한 초안 번호", () => {
  let cards = cardsFromDraft(draft);
  cards = accept(cards, cards[0].key);
  cards = dismiss(cards, cards[1].key);
  cards = addHuman(cards, "h1", "observation", "식사를 다 하셨다");
  assert.deepEqual(buildConfirmBody(cards), {
    items: [
      {
        draft_index: 0,
        category: "remark",
        content: "오른쪽 무릎이 불편하다",
        evidence: "무릎이 좀 불편하다고",
        speaker_uncertain: false,
        risk_tag: "pain",
      },
      {
        draft_index: null,
        category: "observation",
        content: "식사를 다 하셨다",
        evidence: null,
        speaker_uncertain: false,
        risk_tag: null,
      },
    ],
    dismissed_draft_indexes: [1],
  });
});

test("확인하지 않은 항목이 있으면 본문을 만들지 않는다", () => {
  assert.throws(() => buildConfirmBody(cardsFromDraft(draft)));
});
