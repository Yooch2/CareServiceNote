"""3단계: 초대 가입, 배정 해제, 동의 철회, 보호자 열람 범위, 비활성화, 센터 확인 서명"""

import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Consent, Invite, User, VisitRecord
from tests.helpers import (
    PASSWORD,
    add_recipient,
    colleague,
    make_confirmed,
    process_all,
    put_audio,
    signup,
    signup_center,
)


def _join(client: TestClient, code: str, login_id: str = "newbie01") -> Any:
    return client.post(
        "/auth/signup",
        json={
            "login_id": login_id,
            "password": PASSWORD,
            "display_name": "새사람",
            "invite_code": code,
        },
    )


def test_center_signup_makes_manager(client: TestClient) -> None:
    me = signup_center(client, center_name="가상센터A")
    assert me["role"] == "manager"
    assert me["org_name"] == "가상센터A"


def test_invite_code_signup_and_reuse(client: TestClient, other_client: TestClient) -> None:
    signup_center(client)
    created = client.post("/org/invites", json={"role": "caregiver"}).json()
    code = created["code"]
    assert len(client.get("/org/invites").json()) == 1

    # 소문자·공백으로 넣어도 같은 코드
    res = _join(other_client, f"  {code.lower()} ")
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "caregiver"
    assert client.get("/org/invites").json() == []

    again = _join(TestClient(app), code, "newbie02")
    assert again.status_code == 400


def test_bad_invite_codes_share_one_message(client: TestClient, db: Session) -> None:
    signup_center(client)
    expired = client.post("/org/invites", json={"role": "caregiver"}).json()
    invite = db.get(Invite, uuid.UUID(expired["id"]))
    assert invite is not None
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    fresh = TestClient(app)
    messages = {_join(fresh, code).json()["detail"] for code in (expired["code"], "ZZZZZ-ZZZZZ")}
    assert messages == {"초대 코드가 올바르지 않습니다"}


def test_invite_code_is_not_stored_in_plain_text(client: TestClient, db: Session) -> None:
    signup_center(client)
    code = client.post("/org/invites", json={"role": "caregiver"}).json()["code"]
    stored = db.scalars(select(Invite.code_hash)).all()
    assert code not in stored and code.replace("-", "") not in stored


def test_same_invite_used_concurrently_only_once(client: TestClient) -> None:
    signup_center(client)
    code = client.post("/org/invites", json={"role": "caregiver"}).json()["code"]
    results: list[int] = []

    def join(i: int) -> None:
        results.append(_join(TestClient(app), code, f"racer0{i}").status_code)

    threads = [threading.Thread(target=join, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 400, 400, 400]


def test_duplicate_login_does_not_burn_invite(client: TestClient) -> None:
    signup_center(client, login_id="boss01")
    code = client.post("/org/invites", json={"role": "caregiver"}).json()["code"]
    assert _join(TestClient(app), code, "boss01").status_code == 409
    assert _join(TestClient(app), code, "newbie01").status_code == 201


def test_unassigning_revokes_access_immediately(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    client.post(
        f"/recipients/{rid}/consents", json={"kind": "health_record", "granted_on": "2026-11-01"}
    )
    carer = colleague(client, other_client, "carer01")
    assert (
        client.post(
            f"/recipients/{rid}/assignments", json={"caregiver_id": carer["id"]}
        ).status_code
        == 201
    )
    record_id = str(uuid.uuid4())
    assert put_audio(other_client, record_id, rid).status_code == 201

    admin = client.get(f"/recipients/{rid}/admin").json()
    active = admin["assignments"][0]
    assert active["caregiver_name"] == "동료" and active["pending_records"] == 1
    client.delete(f"/recipients/{rid}/assignments/{active['id']}")

    assert other_client.get(f"/recipients/{rid}").status_code == 404
    assert other_client.get(f"/records/{record_id}").status_code == 404
    assert other_client.get(f"/records/{record_id}/audio").status_code == 404
    # 같은 id로 다시 보내도 기존 기록을 돌려주지 않는다
    assert put_audio(other_client, record_id, rid).status_code == 404
    assert other_client.get("/recipients").json() == []


def test_assign_only_active_caregivers_of_same_center(
    client: TestClient, other_client: TestClient
) -> None:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    outsider = signup(other_client, login_id="outsider1")  # 다른 센터
    res = client.post(f"/recipients/{rid}/assignments", json={"caregiver_id": outsider["id"]})
    assert res.status_code == 422
    me = client.get("/auth/me").json()
    res = client.post(f"/recipients/{rid}/assignments", json={"caregiver_id": me["id"]})
    assert res.status_code == 422  # 기관 담당자는 배정 대상이 아님


def test_withdrawn_consent_blocks_new_processing_but_keeps_records(
    client: TestClient, db: Session
) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    pending = str(uuid.uuid4())
    assert put_audio(client, pending, rid).status_code == 201
    make_confirmed(db, [("remark", "산책을 원하심")], recipient_id=uuid.UUID(rid))

    with_consent = client.get(f"/recipients/{rid}").json()
    assert with_consent["consents"] == ["health_record"]

    consent = db.scalar(select(Consent).where(Consent.recipient_id == uuid.UUID(rid)))
    assert consent is not None
    consent.withdrawn_at = datetime.now(UTC)
    db.commit()

    assert put_audio(client, str(uuid.uuid4()), rid).status_code == 409
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 409
    process_all()  # 철회 전에 올라간 녹음도 AI로 보내지 않는다
    assert client.get(f"/records/{pending}").json()["error_code"] == "consent_withdrawn"
    body = {"items": [{"category": "remark", "content": "직접 씀"}]}
    assert client.post(f"/records/{pending}/confirm", json=body).status_code == 409
    # 이미 확정된 기록 열람은 유지
    assert client.get(f"/recipients/{rid}/handover").status_code == 200
    assert client.get(f"/recipients/{rid}/records").json() != []


def test_consent_rules(client: TestClient) -> None:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    url = f"/recipients/{rid}/consents"
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert (
        client.post(url, json={"kind": "health_record", "granted_on": tomorrow}).status_code == 422
    )
    first = client.post(url, json={"kind": "health_record", "granted_on": "2026-11-01"})
    assert first.status_code == 201
    assert (
        client.post(url, json={"kind": "health_record", "granted_on": "2026-11-02"}).status_code
        == 409
    )
    withdrawn = client.post(f"{url}/{first.json()['id']}/withdraw").json()
    assert withdrawn["withdrawn_at"] is not None
    # 철회 뒤 다시 받으면 새 행, 이력은 남는다
    assert (
        client.post(url, json={"kind": "health_record", "granted_on": "2026-11-03"}).status_code
        == 201
    )
    assert len(client.get(f"/recipients/{rid}/admin").json()["consents"]) == 2


def _guardian_world(client: TestClient, guardian: TestClient, db: Session) -> tuple[str, str]:
    """기관 담당자(client)가 수급자·동의·보호자 초대를 만들고 보호자(guardian)가 가입한다."""
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    for kind in ("health_record", "guardian_share"):
        client.post(f"/recipients/{rid}/consents", json={"kind": kind, "granted_on": "2026-11-01"})
    code = client.post(
        "/org/invites", json={"role": "guardian", "recipient_id": rid, "categories": ["remark"]}
    ).json()["code"]
    res = _join(guardian, code, "family01")
    assert res.status_code == 201
    record = make_confirmed(
        db,
        [
            ("remark", "손녀 이야기를 하심"),
            ("observation", "식사를 절반 남기심"),
            ("followup", "식사량 다시 확인"),
        ],
        recipient_id=uuid.UUID(rid),
        visited_on=date.today(),
        transcript="전사문 비밀 문장",
    )
    record.items[1].evidence = "근거 비밀 구절"
    db.commit()
    link_id = client.get(f"/recipients/{rid}/admin").json()["guardians"][0]["id"]
    return rid, link_id


def test_guardian_sees_only_allowed_categories(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    _, link_id = _guardian_world(client, other_client, db)
    res = other_client.get("/guardian/home")
    assert res.status_code == 200
    home = res.json()
    assert home["categories"] == ["remark"]
    assert [i["content"] for v in home["records"] for i in v["items"]] == ["손녀 이야기를 하심"]
    for secret in (
        "식사를 절반",
        "식사량 다시",
        "전사문 비밀",
        "근거 비밀",
        "record_id",
        "evidence",
    ):
        assert secret not in res.text

    client.patch(f"/org/guardian-links/{link_id}", json={"categories": ["remark", "followup"]})
    contents = [
        i["content"]
        for v in other_client.get("/guardian/home").json()["records"]
        for i in v["items"]
    ]
    assert contents == ["손녀 이야기를 하심", "식사량 다시 확인"]


def test_guardian_blocked_by_link_account_or_consent(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, link_id = _guardian_world(client, other_client, db)

    client.patch(f"/org/guardian-links/{link_id}", json={"active": False})
    res = other_client.get("/guardian/home")
    assert res.status_code == 403 and res.json()["detail"] == "보호자 연결이 해제되었습니다"
    client.patch(f"/org/guardian-links/{link_id}", json={"active": True})
    assert other_client.get("/guardian/home").status_code == 200

    share = next(
        c
        for c in client.get(f"/recipients/{rid}/admin").json()["consents"]
        if c["kind"] == "guardian_share"
    )
    client.post(f"/recipients/{rid}/consents/{share['id']}/withdraw")
    assert other_client.get("/guardian/home").status_code == 403
    client.post(
        f"/recipients/{rid}/consents", json={"kind": "guardian_share", "granted_on": "2026-11-02"}
    )

    family = db.scalar(select(User).where(User.login_id == "family01"))
    assert family is not None
    assert client.patch(f"/org/members/{family.id}", json={"active": False}).status_code == 204
    # 쿠키가 남아 있어도 다음 요청부터 막히고, 다시 로그인할 수도 없다
    assert other_client.get("/guardian/home").status_code == 401
    login = other_client.post("/auth/login", json={"login_id": "family01", "password": PASSWORD})
    assert login.status_code == 401


def test_manager_cannot_deactivate_self(client: TestClient) -> None:
    me = signup_center(client)
    assert client.patch(f"/org/members/{me['id']}", json={"active": False}).status_code == 409


def test_review_signature(client: TestClient, other_client: TestClient, db: Session) -> None:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    record = make_confirmed(db, [("remark", "산책을 원하심")], recipient_id=uuid.UUID(rid))
    queue = client.get("/org/reviews").json()
    assert [q["record_id"] for q in queue] == [str(record.id)]

    signed = client.post(f"/records/{record.id}/review")
    assert signed.status_code == 200
    assert signed.json()["review"]["reviewer_name"] == "박담당"
    assert client.post(f"/records/{record.id}/review").status_code == 409
    assert client.get("/org/reviews").json() == []
    db.expire_all()
    stored = db.get(VisitRecord, record.id)
    assert stored is not None and stored.reviewed_at is not None
