"use client";

import { useCallback, useEffect, useState, type SubmitEvent } from "react";

import { api, ApiError, postJson } from "@/lib/api";
import { ROLE_LABEL, timeOnly } from "@/lib/labels";
import type { Message, VisitSession } from "@/lib/types";
import { useUser } from "./auth-gate";
import { Button, Notice } from "./ui";

function message(err: unknown): string {
  return err instanceof ApiError ? err.message : "연결을 확인하고 다시 눌러 주세요.";
}

/** 요양보호사의 방문 시작·종료. 보호자 화면에는 시각만 나간다 (위치는 수집하지 않는다). */
export function VisitBar({ recipientId }: { recipientId: string }) {
  const user = useUser();
  const [sessions, setSessions] = useState<VisitSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<VisitSession[]>(`/recipients/${recipientId}/visits`)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [recipientId]);
  useEffect(load, [load]);

  async function act(path: "start" | "end") {
    setBusy(true);
    setError(null);
    try {
      await postJson(`/recipients/${recipientId}/visits/${path}`, {});
      load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  if (!sessions) return null;
  const open = sessions.find((s) => s.caregiver_id === user.id && s.ended_at === null);
  return (
    <div className="mb-3 flex flex-col gap-2">
      {open ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-pine bg-pine/5 px-4 py-2">
          <span role="status">
            <span className="font-semibold">방문 중</span>{" "}
            <span className="text-muted">{timeOnly(open.started_at)}부터</span>
          </span>
          <Button variant="secondary" disabled={busy} onClick={() => act("end")}>
            방문 종료
          </Button>
        </div>
      ) : (
        <Button variant="secondary" disabled={busy} onClick={() => act("start")}>
          방문 시작
        </Button>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}

/** 수급자별 업무 메시지 (기관 담당자 ↔ 담당 요양보호사). 보호자는 볼 수 없다. */
export function Messages({ recipientId }: { recipientId: string }) {
  const user = useUser();
  const [list, setList] = useState<Message[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Message[]>(`/recipients/${recipientId}/messages`)
      .then(setList)
      .catch(() => setList([]));
  }, [recipientId]);

  async function send(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    setError(null);
    try {
      const sent = await postJson<Message>(`/recipients/${recipientId}/messages`, {
        body: String(new FormData(formEl).get("body") ?? ""),
      });
      setList((l) => [...(l ?? []), sent]);
      formEl.reset();
    } catch (err) {
      setError(message(err));
    }
  }

  if (!list) return null;
  return (
    <section aria-label="업무 메시지">
      <h2 className="mb-2 text-lg font-bold">업무 메시지</h2>
      <p className="mb-2 text-sm text-muted">센터와 담당 요양보호사만 봅니다. 보호자에게는 보이지 않습니다.</p>
      {list.length === 0 ? (
        <p className="text-muted">아직 메시지가 없습니다.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {list.map((m) => (
            <li
              key={m.id}
              className={`max-w-[85%] rounded-lg border px-3 py-2 ${m.author_id === user.id ? "self-end border-pine/30 bg-pine/5" : "self-start border-line bg-sheet"}`}
            >
              <p className="text-xs text-muted">
                {m.author_name} · {ROLE_LABEL[m.author_role]} · {new Date(m.created_at).toLocaleString("ko-KR")}
              </p>
              <p>{m.body}</p>
            </li>
          ))}
        </ol>
      )}
      <form onSubmit={send} className="mt-3 flex gap-2">
        <input
          name="body"
          aria-label="메시지"
          required
          maxLength={500}
          placeholder="예: 내일 방문은 10시로 바뀌었습니다"
          className="min-h-12 min-w-0 flex-1 rounded-xl border border-line bg-sheet px-4 focus:border-pine focus:outline-none"
        />
        <Button type="submit" variant="secondary">
          보내기
        </Button>
      </form>
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </section>
  );
}
