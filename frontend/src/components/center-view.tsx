"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

import { api, ApiError, postJson } from "@/lib/api";
import { alertTitle, CATEGORY_LABEL, dateOnly, ROLE_LABEL } from "@/lib/labels";
import type { Invite, InviteCreated, Member, OrgAlert, ReviewQueueItem } from "@/lib/types";
import { AlertBody } from "./alerts-panel";
import { useUser } from "./auth-gate";
import { BackLink } from "./recipient-view";
import { Badge, Button, Loading, Notice, PageTitle, Sheet } from "./ui";

function message(err: unknown): string {
  return err instanceof ApiError ? err.message : "연결을 확인하고 다시 시도해 주세요.";
}

/** 만든 초대 코드는 이 화면에서 한 번만 보여 준다 (서버에는 해시만 남는다). */
export function NewInviteCode({ invite, who }: { invite: InviteCreated; who: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div role="status" className="rounded-lg border-2 border-dashed border-pine bg-pine/5 p-4">
      <p className="font-semibold">{who} 초대 코드</p>
      <p className="my-2 font-mono text-3xl font-bold tracking-wider">{invite.code}</p>
      <p className="text-sm text-muted">{dateOnly(invite.expires_at)}까지 한 번 쓸 수 있습니다. 이 화면을 벗어나면 다시 볼 수 없습니다.</p>
      <Button
        variant="secondary"
        className="mt-3"
        onClick={() =>
          navigator.clipboard
            ?.writeText(invite.code)
            .then(() => setCopied(true))
            .catch(() => undefined)
        }
      >
        {copied ? "복사했습니다" : "코드 복사"}
      </Button>
    </div>
  );
}

/** 센터 관리: 확인 대기 기록, 요양보호사 초대, 구성원 */
export function CenterView() {
  const user = useUser();
  const [reviews, setReviews] = useState<ReviewQueueItem[] | null>(null);
  const [alerts, setAlerts] = useState<OrgAlert[] | null>(null);
  const [resolved, setResolved] = useState<OrgAlert[]>([]);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 다른 화면으로 가면(Activity로 숨겨져도) 만든 코드를 지운다: 코드는 한 번만 보여 준다
  useLayoutEffect(() => () => setCreated(null), []);

  const load = useCallback(() => {
    Promise.all([
      api<ReviewQueueItem[]>("/org/reviews"),
      api<Member[]>("/org/members"),
      api<Invite[]>("/org/invites"),
      api<OrgAlert[]>("/org/alerts"),
      api<OrgAlert[]>("/org/alerts?status=resolved"),
    ])
      .then(([r, m, i, a, done]) => {
        setReviews(r);
        setMembers(m);
        setInvites(i);
        setAlerts(a);
        setResolved(done.slice(0, 5));
      })
      .catch((err: unknown) => setError(message(err)));
  }, []);

  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      load();
    } catch (err) {
      setError(message(err));
    }
  }

  if (user.role !== "manager") return <Notice tone="error">기관 담당자만 볼 수 있는 화면입니다.</Notice>;
  if (!reviews || !members || !invites || !alerts) return error ? <Notice tone="error">{error}</Notice> : <Loading />;

  return (
    <>
      <BackLink href="/">수급자 목록</BackLink>
      <PageTitle sub={user.org_name}>센터 관리</PageTitle>
      {error && (
        <div className="mb-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      <section aria-label="알림" className="mb-8">
        <h2 className="mb-2 text-lg font-bold">
          알림 <span className="font-normal text-muted">미처리 {alerts.length}건</span>
        </h2>
        {alerts.length === 0 ? (
          <p className="text-muted">처리할 알림이 없습니다.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {alerts.map((a) => (
              <li key={a.id}>
                <AlertCard
                  alert={a}
                  onResolve={(resolution, note, guardian_message, guardian_ids) =>
                    run(() => postJson(`/org/alerts/${a.id}/resolve`, { resolution, note, guardian_message, guardian_ids }))
                  }
                />
              </li>
            ))}
          </ul>
        )}
        {resolved.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-muted">최근 처리한 알림</summary>
            <ul className="mt-2 flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
              {resolved.map((a) => (
                <li key={a.id} className="px-4 py-2 text-sm">
                  <span className="font-semibold">
                    {a.recipient_name} · {alertTitle(a.kind, a.key)}
                  </span>{" "}
                  <Badge tone={a.resolution === "acted" ? "pine" : "neutral"}>{a.resolution === "acted" ? "조치함" : "오탐"}</Badge>
                  <span className="block text-muted">
                    {a.resolved_by_name} · {a.resolved_at && dateOnly(a.resolved_at)}
                    {a.resolution_note && ` · ${a.resolution_note}`}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section aria-label="확인 대기" className="mb-8">
        <h2 className="mb-2 text-lg font-bold">
          확인 대기 <span className="font-normal text-muted">{reviews.length}건</span>
        </h2>
        {reviews.length === 0 ? (
          <p className="text-muted">센터 확인을 기다리는 기록이 없습니다.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
            {reviews.map((r) => (
              <li key={r.record_id}>
                <Link href={`/records/${r.record_id}`} className="block px-4 py-3 hover:bg-paper">
                  <span className="font-semibold">
                    {r.recipient_name} · {r.visited_on} 방문
                  </span>
                  <span className="block text-sm text-muted">{r.caregiver_name} 작성</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="요양보호사 초대" className="mb-8">
        <h2 className="mb-2 text-lg font-bold">요양보호사 초대</h2>
        <Sheet className="flex flex-col gap-3">
          <p className="text-muted">초대 코드를 만들어 전달하면 요양보호사가 가입할 때 입력합니다. 보호자 초대는 수급자 관리 화면에서 만듭니다.</p>
          <Button
            variant="secondary"
            onClick={() =>
              run(async () => setCreated(await postJson<InviteCreated>("/org/invites", { role: "caregiver" })))
            }
          >
            요양보호사 초대 코드 만들기
          </Button>
          {created && <NewInviteCode invite={created} who="요양보호사" />}
        </Sheet>
        {invites.length > 0 && (
          <>
            <h3 className="mt-4 mb-2 font-semibold">사용 전 초대</h3>
            <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
              {invites.map((i) => (
                <li key={i.id} className="flex items-center justify-between gap-3 px-4 py-2">
                  <span>
                    {ROLE_LABEL[i.role]}
                    {i.recipient_name && ` · ${i.recipient_name}`}
                    {i.categories && (
                      <span className="block text-sm text-muted">{i.categories.map((c) => CATEGORY_LABEL[c]).join(", ")}</span>
                    )}
                    <span className="block text-sm text-muted">{dateOnly(i.expires_at)}까지</span>
                  </span>
                  <Button variant="ghost" onClick={() => run(() => api(`/org/invites/${i.id}`, { method: "DELETE" }))}>
                    취소
                  </Button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-label="구성원">
        <h2 className="mb-2 text-lg font-bold">구성원</h2>
        <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet">
          {members.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <span>
                <span className="font-semibold">{m.display_name}</span>{" "}
                <span className="text-sm text-muted">
                  {ROLE_LABEL[m.role]}
                  {m.recipient_name && ` · ${m.recipient_name}`}
                </span>
                {!m.active && (
                  <span className="mt-1 block">
                    <Badge tone="risk">비활성</Badge>
                  </span>
                )}
              </span>
              {m.id !== user.id && (
                <Button
                  variant={m.active ? "danger" : "secondary"}
                  onClick={() =>
                    run(() => api(`/org/members/${m.id}`, { method: "PATCH", body: JSON.stringify({ active: !m.active }) }))
                  }
                >
                  {m.active ? "비활성화" : "다시 활성화"}
                </Button>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-sm text-muted">비활성화하면 그 계정은 바로 로그인과 열람이 막힙니다.</p>
      </section>
    </>
  );
}

/** 미처리 알림 한 건: 근거를 보고 조치함/오탐으로 처리한다 */
function AlertCard({
  alert,
  onResolve,
}: {
  alert: OrgAlert;
  onResolve: (resolution: "acted" | "false_alarm", note: string, guardianMessage: string, guardianIds: string[]) => void;
}) {
  const [note, setNote] = useState("");
  const [guardianMessage, setGuardianMessage] = useState("");
  const [guardianIds, setGuardianIds] = useState<string[]>([]);
  const sharing = guardianMessage.trim() !== "";
  return (
    <div className="rounded-r-lg border-l-4 border-risk bg-sheet px-4 py-3">
      <p className="text-sm text-muted">
        {alert.recipient_name} · {dateOnly(alert.created_at)}
        {alert.created_by_name && ` · ${alert.created_by_name} 올림`}
      </p>
      <AlertBody alert={alert} />
      <label className="mt-3 flex flex-col gap-1 text-sm font-medium">
        처리 메모 (선택)
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          className="min-h-11 rounded-xl border border-line bg-sheet px-3 text-base font-normal"
        />
      </label>
      <label className="mt-2 flex flex-col gap-1 text-sm font-medium">
        보호자에게 보낼 안내 (선택)
        <textarea
          value={guardianMessage}
          onChange={(e) => setGuardianMessage(e.target.value)}
          maxLength={500}
          rows={2}
          placeholder="예: 내일 병원 진료를 예약해 두었습니다."
          className="rounded-xl border border-line bg-sheet p-3 text-base font-normal"
        />
        <span className="font-normal text-muted">이 문장만 보호자 화면에 나갑니다. 알림 내용과 메모는 보내지 않습니다.</span>
      </label>
      {sharing && (
        <fieldset className="mt-2">
          <legend className="text-sm font-medium">받을 보호자 (열람 범위를 보고 골라 주세요)</legend>
          {alert.guardians.length === 0 && <p className="text-sm text-muted">연결된 보호자가 없습니다.</p>}
          {alert.guardians.map((g) => (
            <label key={g.guardian_id} className="mt-1 flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                className="size-5 accent-pine"
                checked={guardianIds.includes(g.guardian_id)}
                onChange={(e) =>
                  setGuardianIds((ids) => (e.target.checked ? [...ids, g.guardian_id] : ids.filter((i) => i !== g.guardian_id)))
                }
              />
              {g.name}
              <span className="text-sm text-muted">({g.categories.map((c) => CATEGORY_LABEL[c]).join(", ")})</span>
            </label>
          ))}
        </fieldset>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button disabled={sharing && guardianIds.length === 0} onClick={() => onResolve("acted", note, guardianMessage, guardianIds)}>
          조치함
        </Button>
        <Button
          variant="secondary"
          disabled={sharing && guardianIds.length === 0}
          onClick={() => onResolve("false_alarm", note, guardianMessage, guardianIds)}
        >
          오탐
        </Button>
      </div>
    </div>
  );
}
