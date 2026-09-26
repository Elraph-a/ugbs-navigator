export type Provenance = "real" | "synthetic";

export interface Citation {
  index: number;
  doc_title: string;
  section: string;
  page: number | null;
  source_url: string;
  provenance: Provenance;
  published_date: string;
  publisher: string;
  similarity: number | null;
}

export interface Fee {
  mode: string;
  first_copy: string | null;
  additional: string | null;
}

export interface Service {
  id: string;
  name: string;
  category: string;
  documented: boolean;
  channel: string | null;
  steps: string[];
  fees: Fee[];
  fees_note?: string | null;
  eligibility?: string | null;
  turnaround?: string | null;
  turnaround_note?: string | null;
  not_documented_note?: string | null;
  caveat?: string | null;
  data_year?: string | null;
  /** "synthetic" when the project team wrote the procedure. */
  provenance?: Provenance;
}

export interface Office {
  id: string;
  name: string;
  short_name: string;
  description: string;
  location: string | null;
  building: string | null;
  postal_address?: string | null;
  phone: string | null;
  phone_alt?: string | null;
  email: string | null;
  email_note?: string | null;
  hours: string | null;
  hours_note?: string | null;
  url: string | null;
  channel?: string;
}

export interface Section {
  service: Service | null;
  answer: string;
  citations: Citation[];
  refused: boolean;
  /** Set on greetings, thanks and "what can you do" — conversation, not an enquiry. */
  conversational?: string;
  reason?: string;
  provider?: string;
  timing?: {
    turnaround?: string | null;
    turnaround_note?: string | null;
    eligibility?: string | null;
  };
}

export interface TraceStep {
  tool: string;
  result?: unknown;
  for?: string | null;
  confidence?: number;
  passed_gate?: boolean;
  hits?: number;
  routing_confidence?: number;
  detail?: { service_id: string | null; reason: string }[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AnswerResponse {
  /** The standalone question that was searched for — a follow-up, rewritten. */
  question: string;
  /** What the student actually typed. */
  message?: string;
  kind?: "question" | "chat" | "off_topic";
  answer?: string;
  citations?: Citation[];
  declined?: boolean;
  pii_redacted: string[];
  sections: Section[];
  escalated: boolean;
  /** The reply explains a general term; no University document defines it. */
  general?: boolean;
  escalation_reason: string | null;
  office: Office | null;
  category: string | null;
  conversational?: string | null;
  routing_confidence: number;
  retrieval_confidence: number;
  provider: string;
  trace: TraceStep[];
  elapsed_ms: number;
}

/** Unanswered questions sharing one reason — and therefore one action. */
export interface GapGroup {
  key: "unpublished" | "no_match" | "not_held" | "prediction";
  label: string;
  action: string;
  volume: number;
  share_of_gaps: number;
  reason: string;
  categories: string[];
  themes: { theme: string; service_id?: string; volume: number; examples: string[] }[];
  examples: string[];
}

/** The same simulated semester, before and after the synthetic procedures. */
export interface GapLoop {
  questions: number;
  before: { escalated: number; rate: number; gaps: GapGroup[] };
  after: { escalated: number; rate: number; gaps: GapGroup[] };
  closed_by: { service_id: string; service: string; synthetic: boolean; enquiries: number }[];
  rerouted: { from: string; to: string; enquiries: number; example: string }[];
  method: string;
}

export interface Dashboard {
  summary: {
    total: number;
    simulated: number;
    live: number;
    escalated: number;
    categories: number;
    date_range: string[];
  };
  demand_by_category: {
    category: string;
    enquiries: number;
    share: number;
    escalated: number;
    escalation_rate: number;
  }[];
  weekly_demand: {
    weeks: string[];
    categories: string[];
    series: Record<string, number[]>;
    totals: number[];
  };
  busiest_hours: {
    hours: number[];
    counts: number[];
    peak_hour: number | null;
    peak_count?: number;
    weekdays: string[];
    weekday_counts: number[];
  };
  most_asked: {
    question: string;
    volume: number;
    share: number;
    declined: number;
    service: string | null;
    category: string | null;
  }[];
  repeat_rate: {
    distinct: number;
    total: number;
    repeated_share: number;
    top_five_share: number;
  };
  service_health: {
    median_ms: number | null;
    p90_ms: number | null;
    measured: number;
    answered_share: number;
    this_week: number;
    last_week: number;
    change: number | null;
    week: string | null;
    partial_week: boolean;
  };
  knowledge_gaps: GapGroup[];
  gap_loop: GapLoop | null;
  deflection: {
    rate: number;
    answered: number;
    total: number;
    weeks: string[];
    series: number[];
  };
  office_load: {
    office_id: string;
    office: string;
    enquiries: number;
    share: number;
  }[];
  source_freshness: {
    answers_with_dated_sources: number;
    answers_citing_stale_sources: number;
    stale_share: number;
    stale_before: number;
    by_year: Record<string, number>;
  };
  forecast: {
    weeks: string[];
    values: number[];
    method: string;
    basis_weeks: number;
    caveat?: string;
  };
}
