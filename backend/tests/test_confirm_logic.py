from typing import Any

import pytest

from app.confirm import ConfirmError, build_confirmed_items
from app.schemas import ConfirmIn

DRAFT: list[dict[str, Any]] = [
    {"category": "remark", "content": "무릎이 아프다", "evidence": "무릎이 아프다고"},
    {"category": "observation", "content": "점심 반 공기", "evidence": "반 정도"},
    {"category": "followup", "content": "산책 의향 확인", "evidence": "산책"},
]


def _body(items: list[dict[str, Any]], dismissed: list[int] | None = None) -> ConfirmIn:
    return ConfirmIn.model_validate({"items": items, "dismissed_draft_indexes": dismissed or []})


def test_origin_is_computed_by_server() -> None:
    result = build_confirmed_items(
        DRAFT,
        _body(
            [
                {"draft_index": 0, "category": "remark", "content": "무릎이 아프다"},
                {"draft_index": 1, "category": "observation", "content": "점심을 절반 드심"},
                {"draft_index": 2, "category": "remark", "content": "산책 의향 확인"},
                {"category": "observation", "content": "직접 추가"},
            ]
        ),
    )
    assert [r["origin"] for r in result] == ["ai", "ai_edited", "ai_edited", "human"]
    assert [r["position"] for r in result] == [0, 1, 2, 3]


def test_dismissed_counts_as_reviewed() -> None:
    result = build_confirmed_items(
        DRAFT,
        _body([{"draft_index": 0, "category": "remark", "content": "무릎이 아프다"}], [1, 2]),
    )
    assert len(result) == 1


@pytest.mark.parametrize(
    ("items", "dismissed"),
    [
        ([{"draft_index": 0, "category": "remark", "content": "a"}], [1]),
        ([{"draft_index": 0, "category": "remark", "content": "a"}], [0, 1, 2]),
        ([{"draft_index": 3, "category": "remark", "content": "a"}], [0, 1, 2]),
        (
            [
                {"draft_index": 0, "category": "remark", "content": "a"},
                {"draft_index": 0, "category": "remark", "content": "b"},
            ],
            [1, 2],
        ),
    ],
)
def test_every_draft_index_exactly_once(items: list[dict[str, Any]], dismissed: list[int]) -> None:
    with pytest.raises(ConfirmError):
        build_confirmed_items(DRAFT, _body(items, dismissed))


def test_no_draft_allows_only_human_items() -> None:
    result = build_confirmed_items([], _body([{"category": "remark", "content": "직접 작성"}]))
    assert result[0]["origin"] == "human"
    with pytest.raises(ConfirmError):
        build_confirmed_items([], _body([{"draft_index": 0, "category": "remark", "content": "x"}]))
