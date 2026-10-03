export interface SafetyConcern {
  id: string;
  product_name: string;
  reporting_period: string;
  name: string;
  category: string;
  description: string;
  search_method: string;
  search_config?: string;
  requires_secondary_assessment: boolean;
  secondary_assessment_instructions?: string;
}

export interface MatchDetail {
  matched_field: string;
  matched_term: string;
  pt_code?: string | null;
  reference_source: string;
  evidence: string;
  source_file?: string | null;
  source_sheet?: string | null;
  source_row?: number | null;
}

export interface CandidateCaseRow {
  case_number: string;
  country: string;
  report_type: string;
  product_name?: string;
  reporting_period?: string;
  age?: string;
  sex?: string;
  is_serious: boolean;
  listedness?: string;
  outcome: string;
  initial_receipt_date: string;
  matches: MatchDetail[];
  matched_terms?: string[];
  evidence?: string[];
  assessment_status: "CANDIDATE" | "RELEVANT" | "NOT_RELEVANT" | "NEEDS_REVIEW";
  exclusion_reason?: string | null;
  reviewer_notes?: string | null;
  secondary_result?: string | null;
}

export interface SearchSummary {
  search_run_id?: string;
  concern_id: string;
  concern_name: string;
  category: string;
  search_method: string;
  reporting_period: string;
  total_event_matches: number;
  distinct_candidate_cases: number;
  relevant_cases_count: number;
  not_relevant_cases_count: number;
  needs_review_cases_count: number;
  candidate_pending_count: number;
  cases: CandidateCaseRow[];
}

export interface ExplodedEvent {
  id: number;
  position: number;
  raw_verbatim: string;
  normalized_term: string;
  preferred_term?: string | null;
  pt_code?: string | null;
  soc?: string | null;
  event_onset?: string | null;
  outcome?: string | null;
  seriousness?: string | null;
  listedness?: string | null;
  causality?: string | null;
  is_matched: boolean;
  match_reason?: string | null;
  source_lineage?: {
    file: string;
    sheet: string;
    row: number;
  };
}

export interface CaseProductItem {
  id: number;
  product_name_raw: string;
  brand_name?: string | null;
  active_substance?: string | null;
  role: string;
  daily_dose?: string | null;
  form?: string | null;
  duration?: string | null;
  indication_pt?: string | null;
  is_suspect: boolean;
}

export interface CaseDetail {
  case_number: string;
  overview: {
    product_name: string;
    reporting_period?: string | null;
    data_lock_point?: string | null;
    country: string;
    report_type: string;
    initial_receipt_date: string;
    is_serious: boolean;
    seriousness_raw: string;
    listedness: string;
    case_outcome: string;
    primary_soc: string;
    primary_event_flag?: string | null;
    previous_submission?: string | null;
    healthcare_prof?: string | null;
    case_classification: string;
    follow_up: string;
    suspect_products?: string[];
    concomitant_products?: string[];
  };
  patient: {
    age: string;
    sex: string;
    relevant_history?: string | null;
    death_cause?: string | null;
  };
  products: CaseProductItem[];
  events: ExplodedEvent[];
  narrative?: string | null;
  comments?: string | null;
  source_lineage: {
    file: string;
    sheet: string;
    row: number;
  };
  assessment?: {
    status: string;
    exclusion_reason?: string | null;
    reviewer_notes?: string | null;
    secondary_assessment_result?: string | null;
    reviewer_id: string;
    updated_at?: string | null;
  } | null;
  audit_trail: Array<{
    timestamp: string;
    user_id: string;
    action: string;
    previous_state?: string | null;
    new_state?: string | null;
  }>;
  matches: Array<{
    field: string;
    term: string;
    pt_code?: string | null;
    source: string;
    evidence: string;
    source_file?: string | null;
    source_sheet?: string | null;
    source_row?: number | null;
  }>;
}

export interface DatasetInfo {
  id: string;
  product_name: string;
  reporting_period?: string | null;
  data_lock_point?: string | null;
  filename: string;
  cases: number;
  events: number;
  type: string;
  created_at?: string | null;
}

export interface IngestionStatus {
  total_cases: number;
  total_exploded_events: number;
  total_smq_terms: number;
  total_safety_concerns: number;
  ingested_files: string[];
  products: string[];
  datasets?: DatasetInfo[];
}

export interface UploadResult {
  status: string;
  message: string;
  file_name: string;
  file_type: string;
  product_name?: string;
  cases_ingested?: number;
  events_exploded?: number;
  products_linked?: number;
  terms_loaded?: number;
  total_cases_in_db?: number;
  total_events_in_db?: number;
  total_smq_terms?: number;
}

export interface Section161RiskItem {
  concern_id: string;
  risk_term: string;
  category: string;
  search_method: string;
  search_criteria: string;
  number_of_relevant_cases: number;
  candidate_case_count: number;
  excluded_count: number;
  needs_review_count: number;
  pending_count?: number;
  requires_secondary_assessment: boolean;
}

export interface Section161CategoryGroup {
  category_name: string;
  risks: Section161RiskItem[];
}

export interface Section161ReportData {
  title: string;
  product_name: string;
  reporting_period: string;
  intro_text: string;
  total_relevant_cases: number;
  total_candidate_cases: number;
  table_sections: Section161CategoryGroup[];
}
