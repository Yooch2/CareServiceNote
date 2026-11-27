"""평가 지표. 모델 출력(draft)과 시나리오 정답을 비교해 개수를 센다."""

import re
import unicodedata
from dataclasses import dataclass, field, fields
from typing import Any

from app.evaluation.dataset import Expect, Scenario


def matches(item: dict[str, Any], expect: Expect) -> bool:
    """분류가 같고 핵심어가 모두 들어 있으면 맞힌 것 ('a|b'는 둘 중 하나)"""
    if item["category"] != expect.category:
        return False
    text = item["content"]
    return all(any(alt in text for alt in kw.split("|")) for kw in expect.keywords)


@dataclass
class Counts:
    expected: int = 0  # 정답 항목 수
    hit: int = 0  # 맞힌 정답 항목
    predicted: int = 0  # 모델 항목 수 (허용 항목 제외)
    false_items: int = 0  # 정답에도 허용 목록에도 없는 모델 항목
    evidence_total: int = 0
    evidence_found: int = 0
    part_expected: int = 0
    part_correct: int = 0
    part_false: int = 0  # 부위가 없어야 할 항목에 부위
    risk_expected: int = 0
    risk_correct: int = 0
    meal_expected: int = 0
    meal_correct: int = 0
    meal_false: int = 0  # 언급이 없는데 식사량을 만듦
    mood_expected: int = 0
    mood_correct: int = 0
    mood_false: int = 0
    followup_expected: int = 0
    followup_found: int = 0
    followup_false: int = 0  # 답이 없는 사항에 답을 만듦
    misses: list[str] = field(default_factory=list)  # 사람이 읽을 메모

    def add(self, other: "Counts") -> None:
        for f in fields(self):
            if f.name == "misses":
                self.misses += other.misses
            else:
                setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))


def score(scenario: Scenario, draft: dict[str, Any]) -> Counts:
    c = Counts()
    items: list[dict[str, Any]] = draft["items"]
    used: set[int] = set()

    for expect in scenario.expected:
        c.expected += 1
        found = next(
            (i for i, it in enumerate(items) if i not in used and matches(it, expect)), None
        )
        if found is None:
            c.misses.append(f"{scenario.id}: 놓침 [{expect.category}] {'/'.join(expect.keywords)}")
            continue
        used.add(found)
        c.hit += 1
        item = items[found]
        if expect.body_part:
            c.part_expected += 1
            if item.get("body_part") == expect.body_part:
                c.part_correct += 1
            else:
                c.misses.append(
                    f"{scenario.id}: 부위 {item.get('body_part')} (정답 {expect.body_part})"
                )
        if expect.risk_tag:
            c.risk_expected += 1
            c.risk_correct += item.get("risk_tag") == expect.risk_tag

    for i, item in enumerate(items):
        allowed = any(matches(item, o) for o in scenario.optional)
        if i not in used and not allowed:
            c.false_items += 1
            c.misses.append(
                f"{scenario.id}: 정답에 없는 항목 [{item['category']}] {item['content']}"
            )
        if i in used or not allowed:
            c.predicted += 1
        c.evidence_total += 1
        c.evidence_found += bool(item.get("evidence_found"))
        if item.get("body_part") and any(k in item["content"] for k in scenario.no_body_part):
            c.part_false += 1
            c.misses.append(f"{scenario.id}: 부위 오탐 {item['body_part']} ← {item['content']}")

    state = draft.get("state") or {}
    for name, expected in (("meal", scenario.meal_level), ("mood", scenario.mood)):
        got = state.get("meal_level" if name == "meal" else "mood")
        if expected is not None:
            setattr(c, f"{name}_expected", 1)
            setattr(c, f"{name}_correct", int(got == expected))
            if got != expected:
                c.misses.append(f"{scenario.id}: {name} {got} (정답 {expected})")
        elif got is not None:
            setattr(c, f"{name}_false", 1)
            c.misses.append(f"{scenario.id}: 언급 없는 {name}에 값 {got}")

    answered = {r["item_id"] for r in draft.get("followup_results", [])}
    for f in scenario.followups:
        if f.answered:
            c.followup_expected += 1
            c.followup_found += f.ref in answered
            if f.ref not in answered:
                c.misses.append(f"{scenario.id}: 이전 확인 {f.ref} 답을 못 찾음")
        elif f.ref in answered:
            c.followup_false += 1
            c.misses.append(f"{scenario.id}: 답이 없는 {f.ref}에 답을 만듦")
    return c


def ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def summary_table(c: Counts) -> dict[str, float | None]:
    """보고서에 쓰는 비율 (분모가 0이면 None)"""
    return {
        "항목 재현율": ratio(c.hit, c.expected),
        "항목 정밀도": ratio(c.predicted - c.false_items, c.predicted),
        "근거 일치율": ratio(c.evidence_found, c.evidence_total),
        "부위 정확도": ratio(c.part_correct, c.part_expected),
        "위험 표시 재현율": ratio(c.risk_correct, c.risk_expected),
        "식사량 정확도": ratio(c.meal_correct, c.meal_expected),
        "기분 정확도": ratio(c.mood_correct, c.mood_expected),
        "후속 확인 재현율": ratio(c.followup_found, c.followup_expected),
    }


def false_counts(c: Counts) -> dict[str, int]:
    return {
        "정답에 없는 항목": c.false_items,
        "부위 오탐": c.part_false,
        "언급 없는 식사량": c.meal_false,
        "언급 없는 기분": c.mood_false,
        "답 없는 후속 확인에 답": c.followup_false,
    }


def _norm_for_cer(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[\s\W_]+", "", text)


def cer(reference: str, hypothesis: str) -> float:
    """글자 오류율: 공백·문장부호를 빼고 편집 거리 / 정답 글자 수"""
    ref, hyp = _norm_for_cer(reference), _norm_for_cer(hypothesis)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i]
        for j, h in enumerate(hyp, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / max(len(ref), 1)
