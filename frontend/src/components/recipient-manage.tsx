"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useState, type SubmitEvent } from "react";

import { api, ApiError, postJson } from "@/lib/api";
import { AUDIT_LABEL, CATEGORY_LABEL, CATEGORY_ORDER, CONSENT_LABEL, dateOnly, ROLE_LABEL } from "@/lib/labels";
import type { AuditEntry, Category, ConsentKind, GuardianLink, InviteCreated, Member, Recipient, RecipientAdmin } from "@/lib/types";
import { NewInviteCode } from "./center-view";
import { BackLink } from "./recipient-view";
import { Badge, Button, Loading, Notice, PageTitle, Sheet } from "./ui";

const KINDS: ConsentKind[] = ["health_record", "guardian_share"];
const CONSENT_HELP: Record<ConsentKind, string> = {
  health_record: "없으면 새 녹음과 AI 요약을 막습니다. 철회해도 이미 확정된 기록은 남습니다.",
  guardian_share: "없으면 보호자가 아무 기록도 볼 수 없습니다.",
};

function today(): string {
  return new Date().toLocaleDateString("sv-SE");
}

/** 수급자 관리(기관 담당자): 담당 배정, 동의 기록, 보호자 연결·열람 범위 */
export function RecipientManage() {
  const { id } = useParams<{ id: string }>();
  const [recipient, setRecipient] = useState<Recipient | null>(null);
  const [admin, setAdmin] = useState<RecipientAdmin | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      api<Recipient>(`/recipients/${id}`),
      api<RecipientAdmin>(`/recipients/${id}/admin`),
      api<Member[]>("/org/members"),
    ])
      .then(([r, a, m]) => {
        setRecipient(r);
        setAdmin(a);
        setMembers(m);
      })
      .catch(() => setFailed(true));
  }, [id]);

  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "연결을 확인하고 다시 시도해 주세요.");
    }
  }

  if (failed) return <Notice tone="error">수급자 관리 정보를 불러오지 못했습니다. 기관 담당자만 볼 수 있습니다.</Notice>;
  if (!recipient || !admin) return <Loading />;

  const current = admin.assignments.filter((a) => a.ended_at === null);
  const past = admin.assignments.filter((a) => a.ended_at !== null);
  const assignable = members.filter(
    (m) => m.role === "caregiver" && m.active && !current.some((a) => a.caregiver_id === m.id),
  );

  return (
    <>
      <BackLink href={`/recipients/${id}`}>방문 전 확인</BackLink>
      <PageTitle sub="담당 배정 · 동의 · 보호자">{recipient.name}</PageTitle>
      {error && (
        <div className="mb-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      <section aria-label="담당 요양보호사" className="mb-8">
        <h2 className="mb-2 text-lg font-bold">담당 요양보호사</h2>
        {current.length === 0 && <p className="mb-2 text-muted">지금 배정된 요양보호사가 없습니다.</p>}
        <ul className="flex flex-col gap-2">
          {current.map((a) => (
            <li key={a.id}>
              <Sheet className="flex items-center justify-between gap-3">
                <span>
                  <span className="font-semibold">{a.caregiver_name}</span>
                  <span className="block text-sm text-muted">{dateOnly(a.started_at)}부터</span>
                  {a.pending_records > 0 && (
                    <span className="mt-1 block text-sm text-follow">
                      확정 전 기록 {a.pending_records}건이 있습니다. 해제하면 작성자도 볼 수 없게 됩니다.
                    </span>
                  )}
                </span>
                <Button variant="danger" onClick={() => run(() => api(`/recipients/${id}/assignments/${a.id}`, { method: "DELETE" }))}>
                  해제
                </Button>
              </Sheet>
            </li>
          ))}
        </ul>
        {assignable.length > 0 && (
          <form
            className="mt-3 flex flex-wrap gap-2"
            onSubmit={(e: SubmitEvent<HTMLFormElement>) => {
              e.preventDefault();
              const caregiver_id = String(new FormData(e.currentTarget).get("caregiver_id"));
              void run(() => postJson(`/recipients/${id}/assignments`, { caregiver_id }));
            }}
          >
            <select name="caregiver_id" aria-label="배정할 요양보호사" className="min-h-12 min-w-0 flex-1 rounded-xl border border-line bg-sheet px-3">
              {assignable.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
            <Button type="submit" variant="secondary">
              배정
            </Button>
          </form>
        )}
        {past.length > 0 && (
          <p className="mt-2 text-sm text-muted">
            지난 담당: {past.map((a) => `${a.caregiver_name}(${dateOnly(a.started_at)}~${dateOnly(a.ended_at ?? a.started_at)})`).join(", ")}
          </p>
        )}
      </section>

      <section aria-label="동의" className="mb-8">
        <h2 className="mb-2 text-lg font-bold">동의</h2>
        <p className="mb-3 text-sm text-muted">센터가 서면으로 받은 동의를 기록합니다. 기록과 철회 이력은 지우지 않습니다.</p>
        <div className="flex flex-col gap-2">
          {KINDS.map((kind) => {
            const active = admin.consents.find((c) => c.kind === kind && c.withdrawn_at === null);
            return (
              <Sheet key={kind}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">{CONSENT_LABEL[kind]} 동의</h3>
                  {active ? <Badge tone="pine">{active.granted_on} 받음</Badge> : <Badge tone="risk">없음</Badge>}
                </div>
                <p className="mt-1 text-sm text-muted">{CONSENT_HELP[kind]}</p>
                {active ? (
                  <Button
                    variant="danger"
                    className="mt-3"
                    onClick={() => run(() => api(`/recipients/${id}/consents/${active.id}/withdraw`, { method: "POST" }))}
                  >
                    철회 기록
                  </Button>
                ) : (
                  <form
                    className="mt-3 flex flex-wrap items-end gap-2"
                    onSubmit={(e: SubmitEvent<HTMLFormElement>) => {
                      e.preventDefault();
                      const granted_on = String(new FormData(e.currentTarget).get("granted_on"));
                      void run(() => postJson(`/recipients/${id}/consents`, { kind, granted_on }));
                    }}
                  >
                    <label className="flex flex-col gap-1 text-sm font-medium">
                      동의 받은 날
                      <input
                        type="date"
                        name="granted_on"
                        defaultValue={today()}
                        max={today()}
                        required
                        className="min-h-12 rounded-xl border border-line bg-sheet px-3 text-base font-normal"
                      />
                    </label>
                    <Button type="submit" variant="secondary">
                      동의 기록
                    </Button>
                  </form>
                )}
              </Sheet>
            );
          })}
        </div>
        {admin.consents.some((c) => c.withdrawn_at) && (
          <p className="mt-2 text-sm text-muted">
            철회 이력:{" "}
            {admin.consents
              .filter((c) => c.withdrawn_at)
              .map((c) => `${CONSENT_LABEL[c.kind]} ${c.granted_on} 받음 → ${dateOnly(c.withdrawn_at ?? "")} 철회`)
              .join(", ")}
          </p>
        )}
      </section>

      <GuardianSection recipientId={id} guardians={admin.guardians} run={run} />
      <RecordsSection recipientId={id} />
    </>
  );
}

function CategoryChecks({ value, onChange, name }: { value: Category[]; onChange: (v: Category[]) => void; name: string }) {
  return (
    <fieldset className="flex flex-wrap gap-2">
      <legend className="sr-only">{name} 열람 범위</legend>
      {CATEGORY_ORDER.map((c) => (
        <label key={c} className="flex min-h-11 items-center gap-2 rounded-lg border border-line px-3">
          <input
            type="checkbox"
            checked={value.includes(c)}
            onChange={(e) => onChange(e.target.checked ? [...value, c] : value.filter((v) => v !== c))}
            className="size-5 accent-pine"
          />
          {CATEGORY_LABEL[c]}
        </label>
      ))}
    </fieldset>
  );
}

function GuardianSection({
  recipientId,
  guardians,
  run,
}: {
  recipientId: string;
  guardians: GuardianLink[];
  run: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [inviteScope, setInviteScope] = useState<Category[]>(["remark"]);
  const [created, setCreated] = useState<InviteCreated | null>(null);

  // 다른 화면으로 가면(Activity로 숨겨져도) 만든 코드를 지운다: 코드는 한 번만 보여 준다
  useLayoutEffect(() => () => setCreated(null), []);

  const patch = (link: GuardianLink, body: Partial<Pick<GuardianLink, "categories" | "active">>) =>
    run(() => api(`/org/guardian-links/${link.id}`, { method: "PATCH", body: JSON.stringify(body) }));

  return (
    <section aria-label="보호자">
      <h2 className="mb-2 text-lg font-bold">보호자</h2>
      <p className="mb-3 text-sm text-muted">
        보호자는 열람 범위에 있는 분류의 확정 항목만 봅니다. 전사문, 음성, 근거 구절은 보지 않습니다.
      </p>
      {guardians.length === 0 && <p className="mb-3 text-muted">연결된 보호자가 없습니다.</p>}
      <ul className="flex flex-col gap-2">
        {guardians.map((g) => (
          <li key={g.id}>
            <Sheet>
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{g.guardian_name}</span>
                <span className="flex gap-1.5">
                  {!g.active && <Badge tone="risk">연결 해제</Badge>}
                  {!g.guardian_active && <Badge tone="risk">계정 비활성</Badge>}
                </span>
              </div>
              <div className="mt-3">
                <CategoryChecks
                  name={g.guardian_name}
                  value={g.categories}
                  onChange={(categories) => (categories.length > 0 ? patch(g, { categories }) : undefined)}
                />
              </div>
              <Button variant={g.active ? "danger" : "secondary"} className="mt-3" onClick={() => patch(g, { active: !g.active })}>
                {g.active ? "연결 해제" : "다시 연결"}
              </Button>
            </Sheet>
          </li>
        ))}
      </ul>
      <Sheet className="mt-3 flex flex-col gap-3">
        <h3 className="font-semibold">보호자 초대</h3>
        <CategoryChecks name="새 보호자" value={inviteScope} onChange={setInviteScope} />
        <Button
          variant="secondary"
          disabled={inviteScope.length === 0}
          onClick={() =>
            run(async () =>
              setCreated(
                await postJson<InviteCreated>("/org/invites", {
                  role: "guardian",
                  recipient_id: recipientId,
                  categories: inviteScope,
                }),
              ),
            )
          }
        >
          보호자 초대 코드 만들기
        </Button>
        {created && <NewInviteCode invite={created} who="보호자" />}
      </Sheet>
    </section>
  );
}

/** 기록 내보내기(CSV)와 열람·정정·내보내기 이력 */
function RecordsSection({ recipientId }: { recipientId: string }) {
  const [log, setLog] = useState<AuditEntry[] | null>(null);
  const load = useCallback(() => {
    api<AuditEntry[]>(`/recipients/${recipientId}/audit`)
      .then(setLog)
      .catch(() => setLog([]));
  }, [recipientId]);
  useEffect(load, [load]);

  return (
    <section aria-label="기록 내보내기와 이력" className="mt-8">
      <h2 className="mb-2 text-lg font-bold">기록 내보내기와 이력</h2>
      <a
        href={`/api/recipients/${recipientId}/export`}
        download
        onClick={() => setTimeout(load, 800)}
        className="inline-flex min-h-12 items-center rounded-xl border border-line bg-sheet px-5 font-semibold hover:border-pine"
      >
        확정 기록 내보내기 (CSV)
      </a>
      <p className="mt-2 text-sm text-muted">내보내기도 아래 이력에 남습니다. 파일에는 수급자 이름이 들어가지 않습니다.</p>
      <h3 className="mt-4 mb-2 font-semibold">열람·정정·내보내기 이력</h3>
      {log && log.length === 0 && <p className="text-muted">아직 이력이 없습니다.</p>}
      {log && log.length > 0 && (
        <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-sheet text-sm">
          {log.map((e) => (
            <li key={e.id} className="flex flex-wrap justify-between gap-x-3 px-4 py-2">
              <span>
                <span className="font-semibold">{AUDIT_LABEL[e.action] ?? e.action}</span> · {e.actor_name}{" "}
                <span className="text-muted">({ROLE_LABEL[e.actor_role]})</span>
              </span>
              <span className="text-muted">{new Date(e.created_at).toLocaleString("ko-KR")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
