export type Category = "remark" | "observation" | "followup";
export type RiskTag = "fall" | "medication" | "pain";
export type Topic = "meal" | "toileting" | "sleep" | "mood";
export type RecordStatus =
  | "queued"
  | "transcribing"
  | "classifying"
  | "draft_ready"
  | "failed"
  | "confirmed";

export interface User {
  id: string;
  login_id: string;
  display_name: string;
}

export interface Recipient {
  id: string;
  name: string;
  created_at: string;
}

export interface Segment {
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface DraftItem {
  category: Category;
  content: string;
  evidence: string | null;
  evidence_found: boolean;
  segment_index: number | null;
  speaker_uncertain: boolean;
  risk_tag: RiskTag | null;
}

export interface OpenFollowupDraft {
  item_id: string;
  content: string;
  visited_on: string;
}

export interface FollowupResultDraft {
  item_id: string;
  result: string;
  evidence: string | null;
  evidence_found: boolean;
  segment_index: number | null;
}

export interface Draft {
  items: DraftItem[];
  missing_topics: Topic[];
  // 1단계에서 만들어진 초안에는 없다
  open_followups?: OpenFollowupDraft[];
  followup_results?: FollowupResultDraft[];
}

export type Origin = "ai" | "ai_edited" | "human";

export interface Check {
  result: string;
  origin: Origin;
  record_id: string;
  visited_on: string;
}

export interface FollowupCheck {
  followup_item_id: string;
  followup_content: string;
  followup_record_id: string;
  followup_visited_on: string;
  result: string;
  evidence: string | null;
  origin: Origin;
}

export interface RecordItem {
  id: string;
  category: Category;
  content: string;
  evidence: string | null;
  speaker_uncertain: boolean;
  risk_tag: RiskTag | null;
  origin: Origin;
  position: number;
  check: Check | null;
}

export interface VisitRecord {
  id: string;
  recipient_id: string;
  visited_on: string;
  recorded_at: string;
  status: RecordStatus;
  error_code: string | null;
  transcript: string | null;
  transcript_segments: Segment[] | null;
  approximate_times: boolean;
  draft: Draft | null;
  items: RecordItem[];
  followup_checks: FollowupCheck[];
  has_audio: boolean;
  created_at: string;
  confirmed_at: string | null;
}

export interface RecordSummary {
  id: string;
  visited_on: string;
  status: RecordStatus;
  is_mine: boolean;
  created_at: string;
}

export interface ConfirmItem {
  draft_index: number | null;
  category: Category;
  content: string;
  evidence: string | null;
  speaker_uncertain: boolean;
  risk_tag: RiskTag | null;
}

export interface ConfirmBody {
  items: ConfirmItem[];
  dismissed_draft_indexes: number[];
  followup_checks: { item_id: string; result: string; evidence: string | null }[];
  dismissed_followup_items: string[];
}

export type Days = 7 | 14 | 30;

export interface SummaryRef {
  item_id: string;
  record_id: string;
  visited_on: string;
}

export interface HandoverSummary {
  sentences: { text: string; items: SummaryRef[] }[];
  created_at: string;
  stale: boolean;
}

export interface Handover {
  days: Days;
  last_visit_on: string | null;
  open_followups: {
    item_id: string;
    content: string;
    evidence: string | null;
    record_id: string;
    visited_on: string;
  }[];
  risk_items: {
    item_id: string;
    category: Category;
    content: string;
    risk_tag: RiskTag;
    record_id: string;
    visited_on: string;
  }[];
  recent_checks: {
    followup_item_id: string;
    followup_content: string;
    result: string;
    origin: Origin;
    record_id: string;
    visited_on: string;
  }[];
  completion: { due: number; checked: number };
  summary: HandoverSummary | null;
}

export interface SearchHit {
  record_id: string;
  visited_on: string;
  kind: "item" | "check" | "transcript";
  category: Category | null;
  text: string;
  item_id: string | null;
}
