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
5. mentioned_topics에는 전사문에서 실제로 언급된 주제만 넣는다: meal(식사), toileting(배변), sleep(수면), mood(기분).
6. 지정된 JSON 형식으로만 답한다."""  # noqa: E501

TRANSCRIBE_PROMPT = """이 음성은 방문요양 요양보호사가 방문 직후 남긴 한국어 기록이다.
들리는 그대로 전사한다. 내용을 고치거나 요약하거나 덧붙이지 않는다.
문장 단위로 나눠 segments에 시작·끝 시각(밀리초)과 그 구간의 텍스트를 넣고, text에는 전체 전사문을 넣는다.
알아들을 수 없는 부분은 [불명확]으로 쓴다."""  # noqa: E501


def classify_user_message(text: str) -> str:
    return f"전사문:\n{text}"
