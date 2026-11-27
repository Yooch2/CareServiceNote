from collections.abc import Sequence

from app.ai.types import OpenFollowup

CLASSIFY_SYSTEM = """너는 방문요양 기록 정리를 돕는다. 요양보호사가 방문 직후 말로 남긴 기록의 전사문을 읽고 항목으로 나눈다.

분류
- remark: 수급자가 직접 한 말이나 요청. 원래 말투를 살려 쓴다.
- observation: 요양보호사가 직접 보고 확인한 상태나 행동.
- followup: 다음 방문 때 다시 확인하거나 챙길 일.

규칙
1. 전사문에 없는 내용은 만들지 않는다. 어떤 분류에 해당하는 내용이 없으면 그 분류의 항목은 만들지 않는다.
2. evidence에는 근거가 된 전사문 구절을 한 글자도 바꾸지 말고 그대로 옮긴다.
3. 낙상, 투약, 통증과 관련된 항목은 risk_tag를 fall, medication, pain 중 하나로 표시한다. 위험한지 판단하거나 조언하지 않는다. 관련이 없으면 null.
4. 누가 한 말인지 분명하지 않으면 speaker_uncertain을 true로 한다.
5. mentioned_topics에는 전사문에서 실제로 언급된 주제만 넣고, evidence에 그 주제가 나온 전사문 구절을 그대로 옮긴다. 주제: meal(식사), toileting(배변), sleep(수면), mood(기분). 언급이 없는 주제는 넣지 않는다.
6. 사용자 메시지에 '이전 방문에서 확인하기로 한 사항'(F1, F2 ...)이 있으면, 전사문에서 그 사항에 대한 답을 찾는다. 답이 있으면 followup_results에 ref(F번호), result(확인한 결과를 짧게), evidence(답이 된 전사문 구절을 그대로)를 넣는다. 답이 없는 사항은 넣지 않는다. 이전 확인 사항에 대한 답은 items에 따로 넣지 않아도 된다.
7. 지정된 JSON 형식으로만 답한다."""  # noqa: E501

TRANSCRIBE_PROMPT = """이 음성은 방문요양 요양보호사가 방문 직후 남긴 한국어 기록이다.
들리는 그대로 전사한다. 내용을 고치거나 요약하거나 덧붙이지 않는다.
문장 단위로 나눠 segments에 시작·끝 시각(밀리초)과 그 구간의 텍스트를 넣고, text에는 전체 전사문을 넣는다.
알아들을 수 없는 부분은 [불명확]으로 쓴다."""  # noqa: E501


def classify_user_message(text: str, followups: Sequence[OpenFollowup] = ()) -> str:
    message = f"전사문:\n{text}"
    if followups:
        lines = "\n".join(f"{f.ref}. {f.content} ({f.visited_on.isoformat()})" for f in followups)
        message += f"\n\n이전 방문에서 확인하기로 한 사항:\n{lines}"
    return message
