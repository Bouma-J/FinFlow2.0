export interface ParameterDefinition {
  key: string;
  label: string;
  type: "boolean" | "choice" | "integer" | "decimal";
  choices: { value: string; label: string }[];
  default: string | number | boolean;
  operational: boolean;
}

export type ParameterValues = Record<string, string | number | boolean>;
export interface CustomFieldDefinition { id: string; label: string; type: "text" | "number" | "boolean" | "date" | "choice"; required: boolean; choices: string[] }
export interface FormConfiguration { client_fields: CustomFieldDefinition[]; analysis_fields: CustomFieldDefinition[]; analysis_sections: { id: string; visible: boolean }[] }
export interface KycConfiguration { required_fields: string[]; required_documents: string[]; check_expiry: boolean; validity_days: number }
export interface ClientReferenceEntry { code: string; label: string; active: boolean; cbs_code: string }
export type ClientReferences = Record<"civility" | "marital_status" | "id_document_type" | "legal_form", ClientReferenceEntry[]>;
export interface EligibilityRule {
  id: string;
  criterion: string;
  operator: "gte" | "lte" | "eq" | "in" | "not_in";
  value: string | boolean | string[];
  effect: "ALERT" | "BLOCK_SUBMIT" | "BLOCK_APPROVE" | "BLOCK_SETUP";
  missing: "FAIL" | "IGNORE";
}
export interface ScoreCriterion {
  metric: string;
  direction: "HIGH" | "LOW";
  bad: string;
  good: string;
  weight: string;
}
export interface ScoringGrid {
  engine: "LEGACY" | "CUSTOM";
  missing_data: "RENORMALIZE" | "ZERO" | "BLOCK_SUBMIT";
  criteria: ScoreCriterion[];
  risk_cutoffs: string[];
}
export type PricingRateKey = "interest_rate" | "fees_rate" | "mandatory_savings_rate";
export interface PricingRate { default: string | null; min: string | null; max: string | null; negotiable: boolean }
export interface PricingBand {
  id: string; min_amount: string | null; max_amount: string | null; min_months: number | null; max_months: number | null;
  interest_rate: string | null; fees_rate: string | null; mandatory_savings_rate: string | null;
}
export interface PricingCharge {
  code: string; label: string; mode: "PERCENT" | "AMOUNT"; value: string;
  min_amount: string | null; max_amount: string | null; tax_rate: string;
}
export interface PricingTariff {
  engine: "LEGACY" | "CONFIGURED"; currency: string;
  interest_rate: PricingRate; fees_rate: PricingRate; mandatory_savings_rate: PricingRate;
  allow_manual_fees: boolean; max_total_fees_pct: string | null; processing_tax_rate: string;
  bands: PricingBand[]; charges: PricingCharge[];
}
export interface ConfigurationOverrides {
  exposure?: { rules?: import("./exposure").ExposureRules };
  simulation?: { conventions?: import("./simulation").SimulationConventions };
  forms?: Partial<FormConfiguration>;
  kyc?: Partial<KycConfiguration>;
  references?: Partial<ClientReferences>;
  policy: ParameterValues;
  thresholds: ParameterValues;
  analysis: {
    required_fields?: string[];
    required_detail_tables?: string[];
    minimum_bank_statement_months?: number;
  };
  eligibility?: { rules?: EligibilityRule[] };
  scoring?: { grid?: ScoringGrid };
  pricing?: { tariff?: PricingTariff };
}

export interface ConfigurationProfile {
  locked_keys: string[];
  id: string;
  code: string;
  name: string;
  version: number;
  status: "DRAFT" | "REVIEW" | "PUBLISHED" | "RETIRED";
  product: string | null;
  product_label: string;
  agency: string | null;
  agency_label: string;
  client_type: string;
  individual_profile: string;
  effective_from: string | null;
  overrides: ConfigurationOverrides;
  reason: string;
  updated_at: string;
  updated_by_display: string;
  published_by_display: string;
  published_at: string | null;
  retirement_reason: string;
}

export interface ConfigurationCatalogue {
  default_exposure: import("./exposure").ExposureRules;
  default_simulation: import("./simulation").SimulationConventions;
  default_forms: FormConfiguration;
  default_kyc: KycConfiguration;
  default_references: ClientReferences;
  form_sections: { id: string; label: string; can_hide: boolean }[];
  kyc_fields: { key: string; label: string }[];
  kyc_documents: { key: string; label: string }[];
  policy: ParameterDefinition[];
  thresholds: ParameterDefinition[];
  analysis_fields: { key: string; label: string }[];
  detail_tables: string[];
  precedence: string[];
  locked_rules: string[];
  modules: { key: string; label: string; available: boolean }[];
  eligibility_criteria: { key: string; label: string; type: "number" | "boolean" | "text"; clients?: string[]; choices: { value: string; label: string }[] }[];
  score_metrics: { key: string; label: string; source: string; clients?: string[] }[];
  default_grid: ScoringGrid;
  default_tariff: PricingTariff;
}

export interface EffectiveConfiguration {
  financing_object_required?: boolean;
  exposure?: { rules: import("./exposure").ExposureRules };
  simulation?: { conventions: import("./simulation").SimulationConventions };
  protected_analysis_sections?: string[];
  forms?: FormConfiguration;
  kyc?: KycConfiguration;
  references?: ClientReferences;
  locked_keys?: Record<string, string>;
  ignored_overrides?: { profile: string; key: string }[];
  context: { product: string; agency: string; client_type: string; individual_profile: string };
  policy: ParameterValues;
  thresholds: ParameterValues;
  analysis: Required<ConfigurationOverrides["analysis"]>;
  sources: { id: string; code: string; name: string; version: number }[];
  origins: Record<string, Record<string, string>>;
  fingerprint: string;
  frozen: boolean;
  required_labels?: Record<string, string>;
  eligibility: { rules: EligibilityRule[] };
  scoring: { grid: ScoringGrid };
  pricing: { tariff: PricingTariff; product_defaults: { interest_rate: string; fees_rate: string; currency: string } };
}

export interface RuleEvaluation {
  score: string | number | null;
  score_risk_level?: number | null;
  scoring_engine: "LEGACY" | "CUSTOM";
  scoring_failures: string[];
  score_breakdown: { missing_metrics?: string[]; complete?: boolean; effective_weight?: number };
  checks: { id: string; label: string; actual: string | number | boolean | null; expected: string | boolean | string[];
    operator: string; passed: boolean | null; missing: boolean; effect: string; message: string }[];
}

export interface ConfigurationPreview {
  pricing_evaluation?: { before: import("./types").PricingQuote; after: import("./types").PricingQuote };
  matches: boolean;
  before: EffectiveConfiguration;
  after: EffectiveConfiguration;
  changes: { section: string; key: string; before: unknown; after: unknown }[];
  impact: { editable_matching: number; frozen_matching: number; note: string };
  evaluation?: { reference: string; before: RuleEvaluation; after: RuleEvaluation; note: string };
}

export const DETAIL_TABLE_LABELS: Record<string, string> = {
  products: "Fiches produits et ventes", stocks: "Inventaire des stocks",
  debts: "Engagements et dettes", cashflow: "Plan de trésorerie", history: "Historique financier",
};
