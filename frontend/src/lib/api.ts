export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** 백엔드 오류 본문에서 사용자에게 보여 줄 문구를 꺼낸다. */
export async function errorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // 본문이 JSON이 아니면 아래 기본 문구
  }
  if (res.status === 422) return "입력값을 확인해 주세요";
  if (res.status >= 500) return "서버에 문제가 생겼습니다. 잠시 후 다시 시도해 주세요";
  return "요청을 처리하지 못했습니다";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("content-type", "application/json");
  const res = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) });
}
