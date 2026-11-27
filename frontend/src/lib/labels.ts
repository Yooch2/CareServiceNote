import type { Category, RecordItem, RecordStatus, RiskTag, Topic } from "./types";

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
  gemini_key_missing: "AI 서비스 설정이 빠져 있습니다.",
  gemini_unreachable: "AI 서비스에 연결하지 못했습니다.",
  llm_unreachable: "AI 서비스에 연결하지 못했습니다.",
  local_stt_unavailable: "음성 인식 기능을 사용할 수 없습니다.",
};

export function errorMessage(code: string | null): string {
  return (code && ERROR_MESSAGE[code]) || "자동 정리 중 문제가 생겼습니다.";
}
