from typing import Any

from app.schemas import ConfirmIn


class ConfirmError(ValueError):
    pass


def build_confirmed_items(
    draft_items: list[dict[str, Any]], body: ConfirmIn
) -> list[dict[str, Any]]:
    """초안 항목이 모두 채택 또는 삭제로 처리됐는지 확인하고, 저장할 항목 값을 만든다."""
    used = [i.draft_index for i in body.items if i.draft_index is not None]
    used += body.dismissed_draft_indexes
    if sorted(used) != list(range(len(draft_items))):
        raise ConfirmError("AI 초안 항목을 모두 확인하거나 삭제해야 확정할 수 있습니다")

    result: list[dict[str, Any]] = []
    for position, item in enumerate(body.items):
        if item.draft_index is None:
            origin = "human"
        else:
            original = draft_items[item.draft_index]
            unchanged = (
                original.get("category") == item.category
                and original.get("content") == item.content
            )
            origin = "ai" if unchanged else "ai_edited"
        result.append(
            {
                "category": item.category,
                "content": item.content,
                "evidence": item.evidence,
                "speaker_uncertain": item.speaker_uncertain,
                "risk_tag": item.risk_tag,
                "origin": origin,
                "position": position,
            }
        )
    return result
