from app.ai.types import Segment, Transcript
from app.masking import mask, mask_transcript


def test_mask_contacts_and_ids() -> None:
    text = (
        "따님 번호는 010-1234-5678이고 집 전화는 02 345 6789, "
        "주민번호 900101-2345678, 메일은 kim.daughter@example.com 이에요."
    )
    assert mask(text) == (
        "따님 번호는 [전화번호]이고 집 전화는 [전화번호], "
        "주민번호 [주민등록번호], 메일은 [이메일] 이에요."
    )


def test_mask_keeps_ordinary_numbers() -> None:
    text = "혈압은 130에 80, 약은 2알, 2026년 11월 27일 오후 3시에 오셨어요. 01012345678"
    assert (
        mask(text) == "혈압은 130에 80, 약은 2알, 2026년 11월 27일 오후 3시에 오셨어요. [전화번호]"
    )


def test_mask_transcript_segments() -> None:
    t = Transcript("번호는 01098765432", [Segment(0, 1000, "번호는 01098765432")], False)
    masked = mask_transcript(t)
    assert masked.text == "번호는 [전화번호]" and masked.segments[0].text == "번호는 [전화번호]"


def test_mask_phone_with_irregular_grouping_from_stt() -> None:
    # mlx-whisper가 실제로 '010 1234 5678'을 이렇게 전사했다
    assert mask("따님 번호는 010-123-45678입니다.") == "따님 번호는 [전화번호]입니다."
    assert mask("031.1234.567 8") == "[전화번호]"
