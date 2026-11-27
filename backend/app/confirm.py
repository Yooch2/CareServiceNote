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


def build_followup_checks(draft: dict[str, Any], body: ConfirmIn) -> list[dict[str, Any]]:
    """AI가 제안한 확인 결과를 모두 채택 또는 삭제했는지 확인하고, 저장할 값을 만든다."""
    suggestions = {r["item_id"]: r for r in draft.get("followup_results", [])}
    given = [str(c.item_id) for c in body.followup_checks]
    dismissed = [str(i) for i in body.dismissed_followup_items]
    if len(set(given) | set(dismissed)) != len(given) + len(dismissed):
        raise ConfirmError("같은 확인 사항이 두 번 들어 있습니다")
    if set(dismissed) - set(suggestions):
        raise ConfirmError("AI가 제안하지 않은 확인 결과는 삭제할 수 없습니다")
    if set(suggestions) - set(given) - set(dismissed):
        raise ConfirmError("AI가 제안한 확인 결과를 모두 확인하거나 삭제해야 확정할 수 있습니다")

    result: list[dict[str, Any]] = []
    for check in body.followup_checks:
        suggestion = suggestions.get(str(check.item_id))
        if suggestion is None:
            origin = "human"
        else:
            origin = "ai" if suggestion.get("result") == check.result else "ai_edited"
        result.append(
            {
                "followup_item_id": check.item_id,
                "result": check.result,
                "evidence": check.evidence,
                "origin": origin,
            }
        )
    return result
