import type { AlertKind, BodyPart, Category, ConsentKind, Mood, RecordItem, RecordStatus, RiskTag, Role, Topic } from "./types";

export const CATEGORY_ORDER: Category[] = ["remark", "observation", "followup"];

export const CATEGORY_LABEL: Record<Category, string> = {
  remark: "말씀",
  observation: "관찰",
  followup: "다음 확인",
};

export const TOPIC_LABEL: Record<Topic, string> = {
  meal: "식사",
  toileting: "배변",
  sleep: "수면",
  mood: "기분",
};

export const RISK_LABEL: Record<RiskTag, string> = {
  fall: "낙상",
  medication: "복약",
  pain: "통증",
};

export const STATUS_LABEL: Record<RecordStatus, string> = {
  queued: "처리 대기",
  transcribing: "음성을 글로 옮기는 중",
  classifying: "말씀·관찰·다음 확인으로 나누는 중",
  draft_ready: "검토 필요",
  failed: "자동 정리 실패",
  confirmed: "확정",
};

export const ORIGIN_LABEL: Record<RecordItem["origin"], string> = {
  ai: "AI 초안 그대로",
  ai_edited: "AI 초안 수정",
  human: "직접 작성",
};

export const PROCESSING: ReadonlySet<RecordStatus> = new Set([
  "queued",
  "transcribing",
  "classifying",
]);

const ERROR_MESSAGE: Record<string, string> = {
  audio_missing: "음성 파일을 찾지 못했습니다.",
  audio_unreadable: "음성 파일을 읽지 못했습니다.",
  empty_transcript: "녹음에서 말소리를 찾지 못했습니다.",
  invalid_ai_output: "AI가 형식에 맞지 않는 결과를 냈습니다.",
  worker_timeout: "처리 시간이 너무 오래 걸렸습니다.",
  consent_withdrawn: "건강정보 처리 동의가 철회되어 AI 처리를 멈췄습니다.",
  gemini_key_missing: "AI 서비스 설정이 빠져 있습니다.",
  gemini_unreachable: "AI 서비스에 연결하지 못했습니다.",
  llm_unreachable: "AI 서비스에 연결하지 못했습니다.",
  local_stt_unavailable: "음성 인식 기능을 사용할 수 없습니다.",
};

export function errorMessage(code: string | null): string {
  return (code && ERROR_MESSAGE[code]) || "자동 정리 중 문제가 생겼습니다.";
}

export const ROLE_LABEL: Record<Role, string> = {
  manager: "기관 담당자",
  caregiver: "요양보호사",
  guardian: "보호자",
};

export const CONSENT_LABEL: Record<ConsentKind, string> = {
  health_record: "건강정보 처리",
  guardian_share: "보호자 공유",
};

/** 2026-11-27T05:00:00Z → 2026-11-27 (기기 시간대 기준) */
export function dateOnly(iso: string): string {
  return new Date(iso).toLocaleDateString("sv-SE");
}

export const BODY_PART_LABEL: Record<BodyPart, string> = {
  head: "머리",
  neck: "목",
  shoulder: "어깨",
  arm: "팔",
  hand: "손",
  chest: "가슴",
  abdomen: "배",
  back: "허리·등",
  hip: "엉덩이·골반",
  leg: "다리",
  knee: "무릎",
  foot: "발",
};
export const BODY_PARTS = Object.keys(BODY_PART_LABEL) as BodyPart[];

/** 식사량 0~4 */
export const MEAL_LABEL = ["거의 못 드심", "조금", "절반", "대부분", "다 드심"];

export const MOOD_LABEL: Record<Mood, string> = { good: "좋음", neutral: "보통", low: "처짐" };
export const MOODS: Mood[] = ["good", "neutral", "low"];

export function alertTitle(kind: AlertKind, key: string): string {
  if (kind === "repeated_discomfort") return `${BODY_PART_LABEL[key as BodyPart] ?? key} 불편 반복`;
  if (kind === "meal_drop") return "식사량 감소";
  return "긴급 우려";
}

/** 2026-11-27T05:02:00Z → 14:02 (기기 시간대) */
export function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export const AUDIT_LABEL: Record<string, string> = {
  view_record: "기록 열람",
  view_handover: "방문 전 확인 열람",
  search: "검색",
  view_guardian_home: "보호자 화면 열람",
  correct: "정정",
  export: "내보내기",
};
