import assert from "node:assert/strict";
import { test } from "node:test";

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
  setState,
  stateFromDraft,
  acceptState,
  writeFollowup,
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
        body_part: null,
      },
      {
        draft_index: null,
        category: "observation",
        content: "식사를 다 하셨다",
        evidence: null,
        speaker_uncertain: false,
        risk_tag: null,
        body_part: null,
      },
    ],
    dismissed_draft_indexes: [1],
    followup_checks: [],
    dismissed_followup_items: [],
    meal_level: null,
    mood: null,
  });
});

test("확인하지 않은 항목이 있으면 본문을 만들지 않는다", () => {
  assert.throws(() => buildConfirmBody(cardsFromDraft(draft)));
});

const withFollowups: Draft = {
  items: [],
  missing_topics: [],
  open_followups: [
    { item_id: "f1", content: "무릎 상태 확인", visited_on: "2026-11-20" },
    { item_id: "f2", content: "산책 의향 확인", visited_on: "2026-11-20" },
  ],
  followup_results: [
    { item_id: "f1", result: "아직 불편하다고 하심", evidence: "무릎이 불편", evidence_found: true, segment_index: 0 },
  ],
};

test("1단계 초안에는 이전 확인 사항이 없다", () => {
  assert.deepEqual(followupCardsFromDraft(draft), []);
  assert.deepEqual(followupCardsFromDraft(null), []);
});

test("AI 제안이 있는 확인 사항만 확인 필요로 센다", () => {
  const fcards = followupCardsFromDraft(withFollowups);
  assert.deepEqual(
    fcards.map((f) => [f.itemId, f.state, f.result]),
    [
      ["f1", "pending", "아직 불편하다고 하심"],
      ["f2", "open", ""],
    ],
  );
  assert.equal(remaining([], fcards), 1);
  assert.equal(canConfirm([], fcards), false);
});

test("제안을 확인하면 결과만 있어도 확정할 수 있다", () => {
  let fcards = followupCardsFromDraft(withFollowups);
  fcards = acceptFollowup(fcards, "f1");
  assert.equal(remaining([], fcards), 0);
  assert.equal(canConfirm([], fcards), true);
  assert.deepEqual(buildConfirmBody([], fcards), {
    items: [],
    dismissed_draft_indexes: [],
    followup_checks: [{ item_id: "f1", result: "아직 불편하다고 하심", evidence: "무릎이 불편" }],
    dismissed_followup_items: [],
    meal_level: null,
    mood: null,
  });
});

test("제안을 삭제하면 삭제 목록에, 제안 없는 사항은 직접 쓰면 결과로", () => {
  let fcards = followupCardsFromDraft(withFollowups);
  fcards = dismissFollowup(fcards, "f1");
  assert.equal(canConfirm([], fcards), false); // 남길 것이 없음
  fcards = writeFollowup(fcards, "f2", "  오늘은 집에서 쉬고 싶다고 하심 ");
  assert.equal(fcards[1].state, "accepted");
  assert.deepEqual(buildConfirmBody([], fcards), {
    items: [],
    dismissed_draft_indexes: [],
    followup_checks: [{ item_id: "f2", result: "오늘은 집에서 쉬고 싶다고 하심", evidence: null }],
    dismissed_followup_items: ["f1"],
    meal_level: null,
    mood: null,
  });
  // 되돌리면 제안 있는 사항은 확인 필요, 없는 사항은 미입력으로
  fcards = restoreFollowup(restoreFollowup(fcards, "f1"), "f2");
  assert.deepEqual(
    fcards.map((f) => [f.state, f.result]),
    [
      ["pending", "아직 불편하다고 하심"],
      ["open", ""],
    ],
  );
});

test("제안을 고쳐 쓰면 근거는 유지하고 확인한 것으로 본다", () => {
  let fcards = followupCardsFromDraft(withFollowups);
  fcards = writeFollowup(fcards, "f1", "조금 나아졌다고 하심");
  assert.deepEqual([fcards[0].state, fcards[0].result, fcards[0].evidence], ["accepted", "조금 나아졌다고 하심", "무릎이 불편"]);
  assert.equal(writeFollowup(fcards, "f2", "   "), fcards);
});

test("오늘 상태: AI 제안이 있으면 확인해야 확정, 바꾸면 확인한 것으로 본다", () => {
  const draft: Draft = {
    items: [
      {
        category: "remark",
        content: "무릎이 불편하다",
        evidence: "무릎이 불편하다고",
        evidence_found: true,
        segment_index: 0,
        speaker_uncertain: false,
        risk_tag: "pain",
        body_part: "knee",
      },
    ],
    missing_topics: [],
    state: { meal_level: 2, meal_evidence: "반 정도 드셨습니다", mood: null, mood_evidence: null },
  };
  const cards = accept(cardsFromDraft(draft), "d0");
  const sc = stateFromDraft(draft);
  assert.equal(remaining(cards, [], sc), 1);
  assert.equal(canConfirm(cards, [], sc), false);

  const changed = setState(sc, { mood: "low" });
  assert.equal(canConfirm(cards, [], changed), true);
  const body = buildConfirmBody(cards, [], changed);
  assert.deepEqual([body.meal_level, body.mood, body.items[0].body_part], [2, "low", "knee"]);
  assert.equal(acceptState(sc).state, "accepted");

  // 1~3단계 초안(state 없음)은 확인할 것이 없다
  assert.equal(stateFromDraft({ items: [], missing_topics: [] }).state, "accepted");
});
