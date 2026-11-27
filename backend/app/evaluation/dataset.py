# ruff: noqa: E501  (가상 전사문 데이터라 줄이 길다)
"""평가용 가상 시나리오. 실제 인물·기록이 아니다.

정답 항목은 '분류 + 꼭 들어갈 핵심어'로 적는다. 모델 문장 표현이 달라도 핵심어가 있으면 맞힌 것으로 본다.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Expect:
    category: str
    keywords: tuple[str, ...]  # 모두 들어 있어야 맞힘 (하나 안에서 '|'로 대체 표현)
    body_part: str | None = None
    risk_tag: str | None = None


@dataclass(frozen=True)
class FollowupCase:
    ref: str
    content: str
    answered: bool  # 이번 전사문에 답이 있는지


@dataclass(frozen=True)
class Scenario:
    id: str
    note: str  # 무엇을 보려는 시나리오인지
    transcript: str
    expected: tuple[Expect, ...]
    optional: tuple[Expect, ...] = ()  # 만들어도 틀리지 않은 항목
    no_body_part: tuple[str, ...] = ()  # 이 핵심어가 든 항목에 부위를 붙이면 오탐
    meal_level: int | None = None
    mood: str | None = None
    followups: tuple[FollowupCase, ...] = field(default_factory=tuple)


E = Expect

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "basic-knee-walk",
        "기본: 말씀·관찰·다음 확인 + 부위 + 식사량",
        "오늘 어르신이 오른쪽 무릎이 좀 불편하다고 하셨어요. 그래도 날 좋으면 산책 나가고 싶다고 하셨고요. "
        "점심은 반 정도 드셨습니다. 다음 방문 때 무릎 상태랑 산책 의향 다시 여쭤봐야 할 것 같아요.",
        (
            E("remark", ("무릎",), body_part="knee", risk_tag="pain"),
            E("remark", ("산책",)),
            E("observation", ("점심|식사",)),
            E("followup", ("무릎|산책",)),
        ),
        meal_level=2,
    ),
    Scenario(
        "blanket-not-pain",
        "헷갈리는 사례: 무릎이 나오지만 불편이 아님",
        "날이 추워서 무릎 담요를 덮어 드렸어요. 어르신이 따뜻하다고 좋아하셨어요. 저녁은 다 드셨고 기분도 좋아 보이셨어요.",
        (E("observation", ("담요",)), E("remark", ("따뜻",))),
        optional=(E("observation", ("저녁|식사",)), E("observation", ("기분",))),
        no_body_part=("담요", "따뜻"),
        meal_level=4,
        mood="good",
    ),
    Scenario(
        "fall-risk",
        "위험 표시: 낙상",
        "화장실 가시다가 미끄러질 뻔하셨어요. 넘어지지는 않으셨는데 많이 놀라셨어요. 욕실 미끄럼 방지 매트가 필요해 보여요. "
        "다음에 매트 설치됐는지 확인하겠습니다.",
        (
            E("observation", ("미끄러|넘어",), risk_tag="fall"),
            E("followup", ("매트",)),
        ),
        optional=(E("remark", ("놀라",)), E("observation", ("놀라",)), E("observation", ("매트",))),
    ),
    Scenario(
        "medication",
        "위험 표시: 투약, 기분 처짐",
        "아침 혈압약을 깜빡하고 안 드셨다고 하셔서 같이 확인하고 드시게 했어요. 요즘 입맛이 없다고 하시고 기운이 없어 보이셨어요. "
        "점심은 조금밖에 못 드셨어요.",
        (
            E("observation", ("혈압약|약",), risk_tag="medication"),
            E("remark", ("입맛",)),
        ),
        optional=(
            E("observation", ("기운",)),
            E("observation", ("점심|식사",)),
            E("remark", ("약|혈압",)),
        ),
        meal_level=1,
        mood="low",
    ),
    Scenario(
        "back-pain-hand",
        "부위 두 개: 허리, 손",
        "허리가 쑤신다고 자주 말씀하셨어요. 손가락 마디도 아프다고 하셔서 따뜻한 물수건을 대 드렸어요.",
        (
            E("remark", ("허리",), body_part="back", risk_tag="pain"),
            E("remark", ("손",), body_part="hand", risk_tag="pain"),
        ),
        optional=(E("observation", ("물수건",)),),
    ),
    Scenario(
        "family-request",
        "요청이 담긴 말씀, 위험 없음",
        "따님이 이번 주말에 오신다고 반찬은 따님이 해 오실 거라고 하셨어요. 다음 주에 병원 가는 날짜 다시 알려 달라고 하셨어요.",
        (
            E("remark", ("따님|딸",)),
            E("followup", ("병원",)),
        ),
        optional=(E("remark", ("병원",)), E("remark", ("반찬",))),
    ),
    Scenario(
        "uncertain-speaker",
        "발화자 불분명(라디오) — 확정 기록으로 만들면 안 되는 말",
        "라디오에서 누가 다리가 아프다고 말하는 게 들렸는데 어르신 말씀인지는 잘 모르겠어요. 오늘 어르신은 주로 주무셨어요.",
        (E("observation", ("주무|잠",)),),
        optional=(E("remark", ("다리",)), E("observation", ("다리|라디오",))),
    ),
    Scenario(
        "contact-masked",
        "연락처가 섞인 전사문 (분류 전에 가려짐)",
        "아드님 연락처가 010-2345-6789로 바뀌었다고 하셔서 센터에 전달하겠다고 했어요. 저녁은 대부분 드셨어요.",
        (E("remark", ("연락처|번호|아드님|아들",)),),
        optional=(E("followup", ("전달|센터",)), E("observation", ("저녁|식사",))),
        meal_level=3,
    ),
    Scenario(
        "followup-answers",
        "이전 확인 사항: 둘은 답이 있고 하나는 없음",
        "지난번에 여쭤보기로 한 산책은 오늘은 집에서 쉬고 싶다고 하셨어요. 무릎은 어제보다 조금 나아졌다고 하셨고, 저녁은 다 드셨습니다.",
        (),
        optional=(
            E("remark", ("쉬고|산책",)),
            E("remark", ("무릎",), body_part="knee"),
            E("observation", ("저녁|식사",)),
        ),
        meal_level=4,
        followups=(
            FollowupCase("F1", "산책 의향 다시 여쭤보기", True),
            FollowupCase("F2", "무릎 상태 다시 확인", True),
            FollowupCase("F3", "복약 시간 지키시는지 확인", False),
        ),
    ),
    Scenario(
        "followup-none",
        "이전 확인 사항이 있지만 이번 녹음에는 답이 없음",
        "오늘은 함께 텔레비전을 보며 이야기를 나눴어요. 옛날 고향 이야기를 즐겁게 하셨어요.",
        (E("remark", ("고향",)),),
        optional=(E("observation", ("텔레비전|이야기",)),),
        mood="good",
        followups=(FollowupCase("F1", "안경 수리 맡겼는지 확인", False),),
    ),
    Scenario(
        "shoulder-meal-none",
        "어깨 불편, 식사 언급 없음",
        "어깨가 결려서 팔을 올리기 힘들다고 하셨어요. 빨래 너는 건 제가 도와 드렸어요.",
        (E("remark", ("어깨",), body_part="shoulder", risk_tag="pain"),),
        optional=(E("observation", ("빨래",)), E("remark", ("팔",))),
    ),
    Scenario(
        "short-record",
        "아주 짧은 기록",
        "특별한 일은 없었고 식사는 거의 못 하셨어요.",
        (E("observation", ("식사",)),),
        meal_level=0,
    ),
    Scenario(
        "foot-swelling-followup",
        "발 부종 관찰 + 다음 확인",
        "발등이 좀 부어 있었어요. 어르신은 아프지는 않다고 하셨어요. 다음 방문 때 붓기 줄었는지 다시 볼게요.",
        (
            E("observation", ("발|부어|붓",), body_part="foot"),
            E("followup", ("붓기|부종|부어",)),
        ),
        optional=(E("remark", ("아프지",)),),
    ),
    Scenario(
        "mood-good-no-items-risk",
        "기분 좋음, 위험 없음",
        "오늘은 기분이 아주 좋으셔서 노래도 부르셨어요. 화분에 물 주는 걸 같이 했어요.",
        (E("observation", ("노래|기분",)),),
        optional=(E("observation", ("화분",)), E("remark", ("노래",))),
        mood="good",
    ),
)


@dataclass(frozen=True)
class AlertVisit:
    day: int
    parts: tuple[str, ...] = ()  # 이 방문에 확정된 불편 부위
    uncertain_parts: tuple[str, ...] = ()  # 발화자 불분명 항목의 부위
    meal_level: int | None = None


@dataclass(frozen=True)
class AlertScenario:
    id: str
    note: str
    visits: tuple[AlertVisit, ...]  # 이 순서대로 확정된다 (방문일 순서와 다를 수 있음)
    expected: frozenset[tuple[str, str]]  # 미처리 알림 (kind, key)


V = AlertVisit

ALERT_SCENARIOS: tuple[AlertScenario, ...] = (
    AlertScenario("knee-twice", "7일 안에 같은 부위 두 번", (V(0, ("knee",)), V(6, ("knee",))),
                  frozenset({("repeated_discomfort", "knee")})),
    AlertScenario("knee-8-days", "8일 차이는 알림 없음", (V(0, ("knee",)), V(8, ("knee",))), frozenset()),
    AlertScenario("different-parts", "다른 부위는 알림 없음", (V(0, ("knee",)), V(2, ("back",))), frozenset()),
    AlertScenario("uncertain", "발화자 미확인 항목은 제외", (V(0, ("knee",)), V(1, (), ("knee",))), frozenset()),
    AlertScenario("same-visit", "한 방문 안 두 항목은 알림 없음", (V(0, ("knee", "knee")),), frozenset()),
    AlertScenario("meal-drop", "식사량 2단계 감소", (V(0, meal_level=4), V(3, meal_level=2)),
                  frozenset({("meal_drop", "meal")})),
    AlertScenario("meal-one-step", "한 단계 감소는 알림 없음",
                  (V(0, meal_level=3), V(2, meal_level=2)), frozenset()),
    AlertScenario("meal-gap-visit", "식사 언급 없는 방문은 건너뛰고 비교",
                  (V(0, meal_level=4), V(1), V(2, meal_level=1)), frozenset({("meal_drop", "meal")})),
    AlertScenario("late-confirm", "앞 방문이 나중에 확정돼도 잡힘",
                  (V(5, meal_level=1), V(2, meal_level=4)), frozenset({("meal_drop", "meal")})),
    AlertScenario("both", "부위 반복과 식사 감소가 함께",
                  (V(0, ("back",), meal_level=4), V(4, ("back",), meal_level=1)),
                  frozenset({("repeated_discomfort", "back"), ("meal_drop", "meal")})),
)  # fmt: skip
