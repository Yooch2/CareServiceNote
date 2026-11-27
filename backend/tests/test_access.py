"""역할 × 엔드포인트 접근 표.

OK = 접근 허용(401·403·404가 아님. 본문 검증 422나 상태 409는 허용으로 본다). 숫자 = 그 상태 코드.
새 엔드포인트를 만들면 test_every_route_is_in_the_table이 실패하므로 표에 줄을 추가해야 한다.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models import Alert, GuardianLink, GuardianSummary, Invite, Recipient
from app.security import hash_password
from tests.helpers import (
    PASSWORD,
    assign,
    give_consent,
    login,
    make_confirmed,
    make_invite,
    make_user,
    new_org,
)

OK = 0
PERSONAS = ("manager", "assigned", "unassigned", "other_manager", "guardian")


@dataclass
class World:
    rid: uuid.UUID
    confirmed: uuid.UUID
    draft: uuid.UUID
    assignment: uuid.UUID
    consent: uuid.UUID
    invite: uuid.UUID
    link: uuid.UUID
    unassigned_id: uuid.UUID
    alert: uuid.UUID
    item: uuid.UUID


def _build(db: Session) -> World:
    org, other = new_org(db), new_org(db, "다른센터")
    pw = hash_password(PASSWORD)
    manager = make_user(db, org.id, "manager", login_id="manager", password_hash=pw)
    assigned = make_user(db, org.id, login_id="assigned", password_hash=pw)
    unassigned = make_user(db, org.id, login_id="unassigned", password_hash=pw)
    make_user(db, other.id, "manager", login_id="other_manager", password_hash=pw)
    guardian = make_user(db, org.id, "guardian", login_id="guardian", password_hash=pw)

    recipient = Recipient(name="가상수급자", org_id=org.id)
    db.add(recipient)
    db.flush()
    assignment = assign(db, recipient.id, assigned.id)
    consent = give_consent(db, recipient.id, manager.id)
    give_consent(db, recipient.id, manager.id, "guardian_share")
    link = GuardianLink(recipient_id=recipient.id, guardian_id=guardian.id, categories=["remark"])
    db.add(link)
    db.commit()

    confirmed = make_confirmed(
        db,
        [("remark", "무릎이 불편하다고 하심")],
        recipient_id=recipient.id,
        caregiver_id=assigned.id,
    )
    draft = make_confirmed(db, [], recipient_id=recipient.id, caregiver_id=assigned.id)
    draft.status, draft.confirmed_at, draft.draft = "draft_ready", None, {"items": []}
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    audio = settings.audio_dir / f"{draft.id}.webm"
    audio.write_bytes(b"fake-audio")
    draft.audio_path = str(audio)
    db.commit()
    invite: Invite = make_invite(db, org.id, manager.id, "ACCESS-TEST1")
    alert = Alert(recipient_id=recipient.id, kind="urgent", key="k", evidence=[], note="우려")
    db.add(alert)
    db.add(
        GuardianSummary(
            record_id=confirmed.id,
            sentences=[
                {
                    "text": "무릎이 불편하다고 하셨어요",
                    "item_ids": [str(confirmed.items[0].id)],
                    "edited": False,
                }
            ],
            created_by=manager.id,
        )
    )
    db.commit()
    return World(
        rid=recipient.id,
        confirmed=confirmed.id,
        draft=draft.id,
        assignment=assignment.id,
        consent=consent.id,
        invite=invite.id,
        link=link.id,
        unassigned_id=unassigned.id,
        alert=alert.id,
        item=confirmed.items[0].id,
    )


Call = Callable[[TestClient, World], Any]


def _put_audio(c: TestClient, w: World) -> Any:
    return c.put(
        f"/records/{uuid.uuid4()}",
        data={
            "recipient_id": str(w.rid),
            "visited_on": "2026-11-27",
            "recorded_at": "2026-11-27T10:00:00+09:00",
        },
        files={"audio": ("rec", b"fake-audio", "audio/webm")},
    )


_HUMAN_ITEM = {"items": [{"category": "remark", "content": "직접 쓴 항목"}]}

# (메서드, 경로 틀, 호출, {역할: 기대})
TABLE: list[tuple[str, str, Call, dict[str, int]]] = [
    ("GET", "/recipients", lambda c, w: c.get("/recipients"),
     {"manager": OK, "assigned": OK, "unassigned": OK, "other_manager": OK, "guardian": 403}),
    ("POST", "/recipients", lambda c, w: c.post("/recipients", json={"name": "새수급자"}),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": OK, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}", lambda c, w: c.get(f"/recipients/{w.rid}"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/records",
     lambda c, w: c.get(f"/recipients/{w.rid}/records"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/handover",
     lambda c, w: c.get(f"/recipients/{w.rid}/handover"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/handover/summary",
     lambda c, w: c.post(f"/recipients/{w.rid}/handover/summary"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/search",
     lambda c, w: c.get(f"/recipients/{w.rid}/search", params={"q": "무릎"}),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/admin", lambda c, w: c.get(f"/recipients/{w.rid}/admin"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/assignments",
     lambda c, w: c.post(
         f"/recipients/{w.rid}/assignments", json={"caregiver_id": str(w.unassigned_id)}
     ),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("DELETE", "/recipients/{recipient_id}/assignments/{assignment_id}",
     lambda c, w: c.delete(f"/recipients/{w.rid}/assignments/{w.assignment}"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/consents",
     lambda c, w: c.post(
         f"/recipients/{w.rid}/consents", json={"kind": "health_record", "granted_on": "2026-11-01"}
     ),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/consents/{consent_id}/withdraw",
     lambda c, w: c.post(f"/recipients/{w.rid}/consents/{w.consent}/withdraw"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("PUT", "/records/{record_id}", _put_audio,
     {"manager": 403, "assigned": OK, "unassigned": 404, "other_manager": 403, "guardian": 403}),
    ("GET", "/records/{record_id}", lambda c, w: c.get(f"/records/{w.confirmed}"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    # 확정 전 기록은 작성자만 (기관 담당자도 볼 수 없다)
    ("GET", "/records/{record_id}#draft", lambda c, w: c.get(f"/records/{w.draft}"),
     {"manager": 404, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/records/{record_id}/audio", lambda c, w: c.get(f"/records/{w.draft}/audio"),
     {"manager": 403, "assigned": OK, "unassigned": 404, "other_manager": 403, "guardian": 403}),
    ("POST", "/records/{record_id}/confirm",
     lambda c, w: c.post(f"/records/{w.draft}/confirm", json=_HUMAN_ITEM),
     {"manager": 403, "assigned": OK, "unassigned": 404, "other_manager": 403, "guardian": 403}),
    ("POST", "/records/{record_id}/review", lambda c, w: c.post(f"/records/{w.confirmed}/review"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/org/members", lambda c, w: c.get("/org/members"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": OK, "guardian": 403}),
    ("PATCH", "/org/members/{user_id}",
     lambda c, w: c.patch(f"/org/members/{w.unassigned_id}", json={"active": True}),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("POST", "/org/invites", lambda c, w: c.post("/org/invites", json={"role": "caregiver"}),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": OK, "guardian": 403}),
    # 다른 센터 수급자로 보호자 초대를 만들 수 없다
    ("POST", "/org/invites#guardian",
     lambda c, w: c.post(
         "/org/invites",
         json={"role": "guardian", "recipient_id": str(w.rid), "categories": ["remark"]},
     ),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/org/invites", lambda c, w: c.get("/org/invites"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": OK, "guardian": 403}),
    ("DELETE", "/org/invites/{invite_id}", lambda c, w: c.delete(f"/org/invites/{w.invite}"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("PATCH", "/org/guardian-links/{link_id}",
     lambda c, w: c.patch(f"/org/guardian-links/{w.link}", json={"categories": ["remark"]}),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/org/reviews", lambda c, w: c.get("/org/reviews"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": OK, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/alerts", lambda c, w: c.get(f"/recipients/{w.rid}/alerts"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/trends", lambda c, w: c.get(f"/recipients/{w.rid}/trends"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/concerns",
     lambda c, w: c.post(f"/recipients/{w.rid}/concerns", json={"note": "걱정되는 점"}),
     {"manager": 403, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/org/alerts", lambda c, w: c.get("/org/alerts"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": OK, "guardian": 403}),
    ("POST", "/org/alerts/{alert_id}/resolve",
     lambda c, w: c.post(f"/org/alerts/{w.alert}/resolve", json={"resolution": "acted"}),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/records/{record_id}/guardian-summary",
     lambda c, w: c.get(f"/records/{w.confirmed}/guardian-summary"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("POST", "/records/{record_id}/guardian-summary",
     lambda c, w: c.post(f"/records/{w.confirmed}/guardian-summary"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("PUT", "/records/{record_id}/guardian-summary",
     lambda c, w: c.put(
         f"/records/{w.confirmed}/guardian-summary", json={"sentences": [{"text": "고친 문장"}]}
     ),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("POST", "/records/{record_id}/guardian-summary/approve",
     lambda c, w: c.post(f"/records/{w.confirmed}/guardian-summary/approve"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("POST", "/records/{record_id}/guardian-summary/unapprove",
     lambda c, w: c.post(f"/records/{w.confirmed}/guardian-summary/unapprove"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/visits", lambda c, w: c.get(f"/recipients/{w.rid}/visits"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/visits/start",
     lambda c, w: c.post(f"/recipients/{w.rid}/visits/start"),
     {"manager": 403, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/visits/end",
     lambda c, w: c.post(f"/recipients/{w.rid}/visits/end"),
     {"manager": 403, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/messages",
     lambda c, w: c.get(f"/recipients/{w.rid}/messages"),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("POST", "/recipients/{recipient_id}/messages",
     lambda c, w: c.post(f"/recipients/{w.rid}/messages", json={"body": "내일 10시로 변경"}),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("PATCH", "/records/{record_id}/items/{item_id}",
     lambda c, w: c.patch(
         f"/records/{w.confirmed}/items/{w.item}",
         json={"category": "remark", "content": "고친 내용", "reason": "잘못 들음"},
     ),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("PATCH", "/records/{record_id}/state",
     lambda c, w: c.patch(
         f"/records/{w.confirmed}/state", json={"meal_level": 3, "reason": "정정"}
     ),
     {"manager": OK, "assigned": OK, "unassigned": 404, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/audit", lambda c, w: c.get(f"/recipients/{w.rid}/audit"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/recipients/{recipient_id}/export", lambda c, w: c.get(f"/recipients/{w.rid}/export"),
     {"manager": OK, "assigned": 403, "unassigned": 403, "other_manager": 404, "guardian": 403}),
    ("GET", "/guardian/home", lambda c, w: c.get("/guardian/home"),
     {"manager": 403, "assigned": 403, "unassigned": 403, "other_manager": 403, "guardian": OK}),
]  # fmt: skip

# 로그인 전이나 누구나 쓰는 경로
EXEMPT = {
    ("GET", "/health"),
    ("POST", "/auth/signup"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("GET", "/auth/me"),
}


def test_every_route_is_in_the_table() -> None:
    # 포함된 라우터는 app.routes에 펼쳐지지 않아 OpenAPI 경로 목록으로 비교한다
    routes = {
        (method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops
    }
    covered = {(m, p.split("#")[0]) for m, p, _, _ in TABLE} | EXEMPT
    assert routes - covered == set(), "접근 표에 없는 경로"
    assert covered - routes == set(), "표에만 있고 실제로 없는 경로"


@pytest.mark.parametrize("persona", PERSONAS)
@pytest.mark.parametrize("row", TABLE, ids=lambda r: f"{r[0]} {r[1]}")
def test_access(
    row: tuple[str, str, Call, dict[str, int]], persona: str, client: TestClient, db: Session
) -> None:
    world = _build(db)
    login(client, persona)
    _, _, call, expected = row
    res = call(client, world)
    want = expected[persona]
    if want == OK:
        assert res.status_code not in (401, 403, 404), res.text
    else:
        assert res.status_code == want, res.text


def test_unauthenticated_gets_401(client: TestClient, db: Session) -> None:
    world = _build(db)
    for _, _, call, _ in TABLE:
        assert call(client, world).status_code == 401
