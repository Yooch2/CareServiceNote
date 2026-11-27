export type Category = "remark" | "observation" | "followup";
export type RiskTag = "fall" | "medication" | "pain";
export type BodyPart =
  | "head"
  | "neck"
  | "shoulder"
  | "arm"
  | "hand"
  | "chest"
  | "abdomen"
  | "back"
  | "hip"
  | "leg"
  | "knee"
  | "foot";
export type Mood = "good" | "neutral" | "low";
export type Topic = "meal" | "toileting" | "sleep" | "mood";
export type RecordStatus =
  | "queued"
  | "transcribing"
  | "classifying"
  | "draft_ready"
  | "failed"
  | "confirmed";

export type Role = "manager" | "caregiver" | "guardian";
export type ConsentKind = "health_record" | "guardian_share";

export interface User {
  id: string;
  login_id: string;
  display_name: string;
  role: Role;
  org_name: string;
}

export interface Recipient {
  id: string;
  name: string;
  created_at: string;
  consents: ConsentKind[];
  caregiver_names: string[];
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
  body_part?: BodyPart | null; // 3단계까지의 초안에는 없다
}

export interface DraftState {
  meal_level: number | null;
  meal_evidence: string | null;
  mood: Mood | null;
  mood_evidence: string | null;
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
  state?: DraftState;
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
  body_part: BodyPart | null;
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
  meal_level: number | null;
  mood: Mood | null;
  review: { reviewer_name: string; reviewed_at: string } | null;
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
  body_part: BodyPart | null;
}

export interface ConfirmBody {
  items: ConfirmItem[];
  dismissed_draft_indexes: number[];
  followup_checks: { item_id: string; result: string; evidence: string | null }[];
  dismissed_followup_items: string[];
  meal_level: number | null;
  mood: Mood | null;
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

// --- 3단계: 센터 관리 ---

export interface Assignment {
  id: string;
  caregiver_id: string;
  caregiver_name: string;
  started_at: string;
  ended_at: string | null;
  pending_records: number;
}

export interface Consent {
  id: string;
  kind: ConsentKind;
  granted_on: string;
  created_at: string;
  withdrawn_at: string | null;
}

export interface GuardianLink {
  id: string;
  guardian_id: string;
  guardian_name: string;
  categories: Category[];
  active: boolean;
  guardian_active: boolean;
}

export interface RecipientAdmin {
  assignments: Assignment[];
  consents: Consent[];
  guardians: GuardianLink[];
}

export interface Member {
  id: string;
  login_id: string;
  display_name: string;
  role: Role;
  active: boolean;
  recipient_name: string | null;
}

export interface Invite {
  id: string;
  role: "caregiver" | "guardian";
  recipient_name: string | null;
  categories: Category[] | null;
  expires_at: string;
}

export interface InviteCreated {
  id: string;
  code: string;
  expires_at: string;
}

export interface ReviewQueueItem {
  record_id: string;
  recipient_id: string;
  recipient_name: string;
  visited_on: string;
  caregiver_name: string;
  confirmed_at: string;
}

export interface GuardianHome {
  recipient_name: string;
  categories: Category[];
  records: {
    visited_on: string;
    items: { category: Category; content: string }[];
    checks: { followup_content: string; result: string }[];
  }[];
}

// --- 4단계: 알림 · 추이 ---

export type AlertKind = "repeated_discomfort" | "meal_drop" | "urgent";

export interface Alert {
  id: string;
  recipient_id: string;
  kind: AlertKind;
  key: string;
  status: "open" | "resolved";
  evidence: { record_id: string; item_id: string | null; visited_on: string; text: string }[];
  note: string | null;
  created_at: string;
  updated_at: string;
  resolution: "acted" | "false_alarm" | null;
  resolution_note: string | null;
  resolved_at: string | null;
}

export interface OrgAlert extends Alert {
  recipient_name: string;
  created_by_name: string | null;
  resolved_by_name: string | null;
}

export interface TrendPoint {
  record_id: string;
  visited_on: string;
  meal_level: number | null;
  mood: Mood | null;
}
