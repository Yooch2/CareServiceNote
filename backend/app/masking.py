"""전사문에서 불필요한 식별정보(연락처, 주민등록번호)를 가린다.

전사 직후, 저장하고 AI 분류에 넘기기 전에 적용한다. 숫자로 전사된 경우만 잡는다
(예: '공일공 일이삼사'처럼 말로 읽은 번호는 못 잡는다). 이름은 오탐이 많아 가리지 않는다.
"""

import re

from app.ai.types import Segment, Transcript

_RULES = (
    # 주민등록번호: 앞 6자리 + 뒤 7자리(1~4로 시작)
    (re.compile(r"(?<!\d)\d{6}\s*-?\s*[1-4]\d{6}(?!\d)"), "[주민등록번호]"),
    # 휴대전화·지역번호 전화: 0으로 시작해 숫자 7~8개가 더 이어짐. 구분 기호 위치는 따지지 않는다
    # (실제 STT가 '010-123-45678'처럼 자리를 다르게 끊어 쓰는 경우가 있었다)
    (re.compile(r"(?<!\d)0\d{1,2}(?:[\s.-]?\d){7,8}(?!\d)"), "[전화번호]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[이메일]"),
)


def mask(text: str) -> str:
    for pattern, label in _RULES:
        text = pattern.sub(label, text)
    return text


def mask_transcript(transcript: Transcript) -> Transcript:
    return Transcript(
        text=mask(transcript.text),
        segments=[Segment(s.start_ms, s.end_ms, mask(s.text)) for s in transcript.segments],
        approximate_times=transcript.approximate_times,
    )
