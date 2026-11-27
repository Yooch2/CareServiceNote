import { errorDetail } from "./api";
import { listPending, removePending, savePending, type PendingUpload } from "./offline-queue";

export const MAX_AUDIO_BYTES = 10 * 1024 * 1024;

export type UploadResult =
  | { kind: "uploaded" }
  | { kind: "queued" }
  | { kind: "rejected"; message: string };

const EXT: Record<string, string> = {
  "audio/webm": "webm",
  "audio/ogg": "ogg",
  "audio/mp4": "m4a",
  "audio/wav": "wav",
};

function send(u: PendingUpload): Promise<Response> {
  const form = new FormData();
  const ext = EXT[u.audio.type.split(";")[0]] ?? "webm";
  form.append("audio", u.audio, `record.${ext}`);
  form.append("recipient_id", u.recipientId);
  form.append("visited_on", u.visitedOn);
  form.append("recorded_at", u.recordedAt);
  return fetch(`/api/records/${u.id}`, { method: "PUT", body: form, credentials: "same-origin" });
}

/** 올리고, 네트워크 오류나 서버 오류(5xx)면 기기에 저장한다. 같은 id라 나중에 다시 보내도 중복되지 않는다. */
export async function uploadOrQueue(u: PendingUpload): Promise<UploadResult> {
  let res: Response;
  try {
    res = await send(u);
  } catch {
    await savePending(u);
    return { kind: "queued" };
  }
  if (res.ok) return { kind: "uploaded" };
  if (res.status >= 500) {
    await savePending(u);
    return { kind: "queued" };
  }
  return { kind: "rejected", message: await errorDetail(res) };
}

/** 대기 중인 녹음을 다시 보내고 남은 목록을 돌려준다. 4xx는 다시 보내도 같으니 사유를 남겨 사용자가 정리하게 한다. */
export async function flushPending(userId: string): Promise<PendingUpload[]> {
  // ponytail: 탭 두 개가 동시에 보내도 같은 id라 서버가 중복을 막는다. 잠금은 두지 않음.
  for (const u of await listPending(userId)) {
    let res: Response;
    try {
      res = await send(u);
    } catch {
      break; // 아직 오프라인
    }
    if (res.ok) await removePending(u.id);
    else if (res.status === 401) break;
    else if (res.status < 500) await savePending({ ...u, lastError: await errorDetail(res) });
  }
  return listPending(userId);
}
