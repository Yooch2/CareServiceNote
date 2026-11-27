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

export interface Draft {
  items: DraftItem[];
  missing_topics: Topic[];
}

export interface RecordItem {
  id: string;
  category: Category;
  content: string;
  evidence: string | null;
  speaker_uncertain: boolean;
  risk_tag: RiskTag | null;
  origin: "ai" | "ai_edited" | "human";
  position: number;
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
}
