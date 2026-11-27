import re

from pydantic import BaseModel

from app.ai.types import StructuredLLM

SUMMARY_SYSTEM = """너는 방문요양 인계를 돕는다. 다음 방문을 맡을 요양보호사가 방문 전에 읽을 짧은 인계 요약을 쓴다.

입력은 확정된 방문 기록 항목 목록이다. 각 줄은 'I번호. [방문일] [분류] 내용' 형식이다.

규칙
1. 목록에 있는 내용만 쓴다. 추측, 진단, 조언, 위험도 판단을 하지 않는다.
2. 최대 5문장. 다음 방문에서 알아야 할 것(반복되는 불편, 요청, 아직 확인할 일)을 먼저 쓴다.
3. 문장마다 refs에 근거가 된 항목 번호(I1, I2 ...)를 하나 이상 넣는다. 근거가 없는 문장은 쓰지 않는다.
4. 지정된 JSON 형식으로만 답한다."""  # noqa: E501


GUARDIAN_SUMMARY_SYSTEM = """너는 방문요양 센터가 보호자에게 보내는 하루 소식을 돕는다. 오늘 방문에서 확정된 기록 항목으로 보호자가 읽을 짧은 요약을 쓴다.

입력의 각 줄은 'I번호. [분류] 내용' 형식이다.

규칙
1. 목록에 있는 내용만 쓴다. 추측, 진단, 조언, 위험도 판단을 하지 않는다. 걱정을 키우거나 줄이는 표현을 덧붙이지 않는다.
2. 최대 3문장. 보호자가 읽기 쉬운 존댓말로, 어르신을 '어르신'이라고 부른다. 사람 이름은 쓰지 않는다.
3. 문장마다 refs에 근거가 된 항목 번호(I1, I2 ...)를 하나 이상 넣는다. 서로 다른 분류의 내용은 되도록 다른 문장에 쓴다.
4. 지정된 JSON 형식으로만 답한다."""  # noqa: E501


class SummarySentence(BaseModel):
    text: str
    refs: list[str]


class SummaryOut(BaseModel):
    sentences: list[SummarySentence]


def summarize(llm: StructuredLLM, lines: list[str]) -> SummaryOut:
    user = "확정된 방문 기록 항목:\n" + "\n".join(lines)
    return llm.generate(SUMMARY_SYSTEM, user, SummaryOut)


def summarize_for_guardian(llm: StructuredLLM, lines: list[str]) -> SummaryOut:
    user = "오늘 방문의 확정 항목:\n" + "\n".join(lines)
    return llm.generate(GUARDIAN_SUMMARY_SYSTEM, user, SummaryOut)


def clean_summary[R](
    out: SummaryOut, refs: dict[str, R], limit: int = 5
) -> list[tuple[str, list[R]]]:
    """없는 항목 번호는 지우고, 근거가 하나도 남지 않은 문장은 버린다."""
    cleaned: list[tuple[str, list[R]]] = []
    for sentence in out.sentences[:limit]:
        # 작은 모델이 문장 안에 '(I1)', '[I2, I3]' 같은 참조 번호를 적는 경우가 있어 지운다
        text = re.sub(r"\s*[(\[]\s*I\d+(?:\s*,\s*I\d+)*\s*[)\]]", "", sentence.text).strip()
        targets = [refs[r.strip()] for r in dict.fromkeys(sentence.refs) if r.strip() in refs]
        if text and targets:
            cleaned.append((text, targets))
    return cleaned
