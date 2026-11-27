"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { MAX_AUDIO_BYTES, uploadOrQueue } from "@/lib/upload";
import { QUEUE_CHANGED } from "./app-shell";
import { useUser } from "./auth-gate";
import { BackLink } from "./recipient-view";
import { Button, Notice, PageTitle, Sheet } from "./ui";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/mp4"];

export function Recorder() {
  const { id: recipientId } = useParams<{ id: string }>();
  const user = useUser();
  const router = useRouter();
  const [consent, setConsent] = useState(false);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fileKey, setFileKey] = useState(0); // 바꾸면 파일 선택 칸이 비워진다
  const [message, setMessage] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const previewUrl = useMemo(() => (audio ? URL.createObjectURL(audio) : null), [audio]);
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  async function start() {
    setMessage(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t));
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setAudio(new Blob(chunks, { type: rec.mimeType }));
      };
      rec.start();
      recorderRef.current = rec;
      setAudio(null);
      setRecording(true);
    } catch {
      setMessage({ tone: "error", text: "마이크를 쓸 수 없습니다. 브라우저의 마이크 권한을 허용하거나 음성 파일을 올려 주세요." });
    }
  }

  function stop() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  async function submit() {
    if (!audio) return;
    if (audio.size > MAX_AUDIO_BYTES) {
      setMessage({ tone: "error", text: "10MB 이하 음성만 올릴 수 있습니다. 녹음을 나눠 주세요." });
      return;
    }
    setBusy(true);
    setMessage(null);
    const now = new Date();
    const upload = {
      id: crypto.randomUUID(),
      userId: user.id,
      recipientId,
      visitedOn: now.toLocaleDateString("sv-SE"), // YYYY-MM-DD, 기기 시간대 기준
      recordedAt: now.toISOString(),
      audio,
      lastError: null,
    };
    const result = await uploadOrQueue(upload);
    if (result.kind === "uploaded") {
      router.push(`/records/${upload.id}`);
      return;
    }
    setBusy(false);
    if (result.kind === "queued") {
      window.dispatchEvent(new Event(QUEUE_CHANGED));
      setAudio(null);
      setFileKey((k) => k + 1);
      setMessage({ tone: "info", text: "연결이 끊겨 이 기기에 저장했습니다. 다시 연결되면 자동으로 올라갑니다." });
    } else {
      setMessage({ tone: "error", text: result.message });
    }
  }

  return (
    <>
      <BackLink href={`/recipients/${recipientId}`}>기록 목록</BackLink>
      <PageTitle sub="방문 중 들은 말과 본 것을 말로 남기면 AI가 초안을 만듭니다.">방문 기록</PageTitle>

      <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-line bg-sheet p-4">
        <input
          type="checkbox"
          className="mt-1 size-6 shrink-0 accent-pine"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        <span>수급자(또는 보호자)에게 녹음해서 기록에 쓴다는 것을 알렸습니다.</span>
      </label>

      <Sheet className="mt-4 flex flex-col gap-4">
        {recording ? (
          <Button variant="danger" onClick={stop} className="min-h-16 text-xl">
            <span aria-hidden className="size-4 bg-risk" />
            녹음 멈추기
          </Button>
        ) : (
          <Button onClick={start} disabled={!consent || busy} className="min-h-16 text-xl">
            <span aria-hidden className="size-4 rounded-full bg-current" />
            {audio ? "다시 녹음" : "녹음 시작"}
          </Button>
        )}
        {recording && (
          <p className="flex items-center justify-center gap-2 font-semibold text-risk" role="status">
            <span aria-hidden className="size-2.5 animate-pulse rounded-full bg-risk" />
            녹음 중
          </p>
        )}
        <label className="flex flex-col gap-1.5 text-muted">
          또는 음성 파일 올리기
          <input
            key={fileKey}
            type="file"
            accept="audio/*"
            disabled={!consent || recording || busy}
            className="text-sm file:mr-3 file:min-h-11 file:rounded-lg file:border file:border-line file:bg-paper file:px-3 file:text-ink"
            onChange={(e) => {
              setMessage(null);
              setAudio(e.target.files?.[0] ?? null);
            }}
          />
        </label>
        {previewUrl && <audio controls src={previewUrl} className="w-full" />}
        <Button onClick={submit} disabled={!consent || !audio || recording || busy}>
          {busy ? "올리는 중…" : "기록 올리기"}
        </Button>
        {!consent && <p className="text-sm text-muted">위의 알림 확인에 체크하면 녹음할 수 있습니다.</p>}
      </Sheet>

      {message && (
        <div className="mt-4">
          <Notice tone={message.tone}>{message.text}</Notice>
        </div>
      )}
    </>
  );
}
