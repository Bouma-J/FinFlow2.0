export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface TenantBranding {
  id: string;
  code: string;
  name: string;
  logo_url: string | null;
  brand_primary: string;
  brand_secondary: string;
  brand_accent: string;
  brand_sidebar: string;
  brand_sidebar_text: string;
}

export type DataScope = "OWN" | "AGENCY" | "TENANT";

export interface AgencySummary {
  id: string;
  code: string;
  name: string;
}

export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  tenant: string | null;
  agency: string | null;
  agencies_detail: AgencySummary[];
  data_scope: DataScope;
  is_group_level: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  mfa_enabled: boolean;
  must_change_password: boolean;
  roles: string[];
  capabilities: string[];
  permissions: string[];
  tenant_branding: TenantBranding | null;
  /** Feature flags serveur (ex. SMS désactivé tant que provider absent). */
  features?: { sms?: boolean };
}

export interface Permission {
  id: number;
  name: string;
  codename: string;
  app_label: string;
  model: string;
  label: string;
}

export interface Agency {
  id: string;
  tenant: string;
  code: string;
  name: string;
  region: string;
  address: string;
  is_active: boolean;
  manager_last_name: string;
  manager_first_name: string;
  manager_phone: string;
  manager_display_name?: string;
  cbs_point_of_service_id?: string;
}

export interface TenantOfficer {
  id?: string;
  title: string;
  last_name: string;
  first_name: string;
  phone: string;
  ordering?: number;
}

export interface RoleOption {
  id: number;
  name: string;
  tenant?: string;
  permission_count?: number;
  user_count?: number;
  pack_code?: string;
}

export interface Role extends RoleOption {
  permissions: number[];
  permissions_detail: Permission[];
  user_count: number;
  capabilities: string[];
  pack_code: string;
}

export interface BusinessCapability {
  code: string;
  label: string;
  permission: string;
}

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  tenant: string | null;
  agency: string | null;
  agencies_detail: AgencySummary[];
  data_scope: DataScope;
  is_group_level: boolean;
  is_staff: boolean;
  is_active: boolean;
  must_change_password?: boolean;
  employee_id: string;
  cbs_id?: string;
  phone: string;
  groups: RoleOption[];
}

export interface Delegation {
  max_amount?: string | null;
  product?: string | null;
  agency?: string | null;
  step_kind?: string;
  approval_required?: boolean;
  approved_by?: string | null;
  approved_at?: string | null;
  id: string;
  delegator: string;
  delegator_display: string;
  delegate: string;
  delegate_display: string;
  reason: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
  is_currently_valid: boolean;
  created_at: string;
}

export interface DelegationColleague {
  id: string;
  username: string;
  display_name: string;
}

export interface AfterSalesHubModuleCounts {
  open: number;
  in_approval?: number;
  total?: number;
  followups_due?: number;
  broken_promises_30d?: number;
  unassigned?: number;
}

export interface AfterSalesHub {
  modules: {
    main_levee?: AfterSalesHubModuleCounts;
    dation?: AfterSalesHubModuleCounts;
    formalisation?: AfterSalesHubModuleCounts;
    collection?: AfterSalesHubModuleCounts;
  };
  recent: Array<{
    kind: "MAIN_LEVEE" | "DATION" | "FORMALISATION" | "COLLECTION" | string;
    id: string;
    reference: string;
    status: string;
    status_display: string;
    client_name: string;
    detail_path: string;
    updated_at: string | null;
  }>;
  as_of: string;
}

export interface WorkflowStep {
  committee_quorum?: number;
  id: string;
  definition: string;
  name: string;
  order: number;
  required_group: number | null;
  mode: string;
  step_kind: string;
  min_amount: string | null;
  max_amount: string | null;
  min_risk_level: number | null;
  sla_hours: number | null;
  allow_return: boolean;
  sla_mode: "CALENDAR" | "BUSINESS";
  committee_enabled: boolean;
  committee_majority: "SIMPLE" | "QUALIFIED" | "UNANIMOUS";
  committee_majority_numerator: number;
  committee_majority_denominator: number;
  committee_abstentions: "INCLUDE" | "EXCLUDE";
  committee_record_required: boolean;
  committee_pv_required: boolean;
}

export interface BusinessCalendar {
  id: string;
  code: string;
  name: string;
  timezone: string;
  working_days: number[];
  opening_time: string;
  closing_time: string;
  holidays: string[];
  is_active: boolean;
  updated_at: string;
}

export interface DecisionGaps {
  label: string;
  ranges: { from: string; to: string | null }[];
}

export interface WorkflowDefinition {
  id: string;
  code: string;
  name: string;
  target_type: string;
  version: number;
  is_active: boolean;
  is_used: boolean;
  execution_mode: "LEGACY_ORDER" | "EXPLICIT_MODE";
  business_calendar: string | null;
  /** Tranches de montant sans étape décisionnelle, `null` si le circuit est sain. */
  decision_gaps: DecisionGaps | null;
  /** Critères de sélection du circuit (optionnels, combinables). */
  min_amount: string | null;
  max_amount: string | null;
  product: string | null;
  product_label: string | null;
  product_category: string | null;
  product_category_label: string | null;
  specificity_score: number;
  steps: WorkflowStep[];
}

export interface ProductCategory {
  id: string;
  code: string;
  label: string;
  description: string;
  is_active: boolean;
}

export interface CbsCatalogItem {
  id: string;
  code: string;
  label: string;
  description?: string;
  cbs_code: string;
  purpose_type?: string;
  periods_per_year?: number;
  sort_order?: number;
  is_active: boolean;
}

export interface CbsRefSyncBucket {
  fetched: number;
  created: number;
  updated: number;
  linked: number;
  unchanged: number;
  unmatched: Array<{ id: string; code: string; libelle: string }>;
  error: string | null;
}

export interface CbsRefSyncReport {
  connector_id: string;
  scopes: string[];
  results: Partial<
    Record<
      | "currencies"
      | "periodicities"
      | "financing_objects"
      | "service_points"
      | "managers"
      | "financing_sources"
      | "decision_motifs"
      | "professions",
      CbsRefSyncBucket
    >
  >;
}

export interface NotificationSettings {
  id: string;
  enabled: boolean;
  notify_on_step: boolean;
  notify_on_completion: boolean;
  notify_on_rejection: boolean;
  notify_on_return: boolean;
  notify_collection_email: boolean;
  notify_collection_sms: boolean;
  notify_collection_transfer: boolean;
  notify_collection_dialogue: boolean;
  from_email: string;
  reply_to: string;
  cc_tenant_email: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_username: string;
  /** Write-only à l'enregistrement ; jamais renvoyé par l'API. */
  smtp_password?: string;
  smtp_password_configured: boolean;
  smtp_configured: boolean;
  effective_from_email: string;
  updated_at: string;
}

export interface CreditInstructionPolicy {
  require_credit_contracts: boolean;
  require_credit_signed_contracts: boolean;
  require_surety_contracts: boolean;
  require_setup_request: boolean;
  require_setup_four_eyes: boolean;
  risk_mode: "RECOMMENDATION" | "SCORE" | "CONSERVATIVE";
  approval_validity_days: number;
  max_analysis_age_days: number;
  require_final_review: boolean;
  setup_execution_role: "CREDIT_ADMIN" | "OPERATIONS";
  require_setup_authorizer_separation: boolean;
  recheck_kyc_on_setup: boolean;
  require_verified_documents: boolean;
  id: string;
  collateral_coverage_mode: "ALERT" | "BLOCK_SUBMIT" | "BLOCK_APPROVE";
  require_field_visit: boolean;
  allow_unfavorable_analysis_submit: boolean;
  require_product_checklist: boolean;
  match_product_client_type: boolean;
  kyc_gate: "ON_SUBMIT" | "ON_CREATE";
  product_bounds_gate: "ON_SUBMIT" | "ON_SAVE";
  amount_approved_mode: "ALLOW" | "FORBID";
  show_readiness_checklist: boolean;
  enable_cancel_status: boolean;
  allow_collateral_during_approval: boolean;
  require_surety_signed_contracts: boolean;
  require_formalization_before_disbursement: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CreditReadinessCheck {
  key: string;
  label: string;
  ok: boolean;
  blocking: boolean;
  message: string;
}

export interface CreditSetupState {
  failures: string[];
  authorization_failures: string[];
  authorization_valid: boolean;
  review_current: boolean;
  can_transmit: boolean;
  execution_role: "CREDIT_ADMIN" | "OPERATIONS";
  execution_role_display: string;
  review: {
    status?: "VALIDATED" | "TO_COMPLETE";
    reviewed_at?: string; reviewed_by_display?: string; comment?: string;
    complement_request?: { requested_by_display?: string; requested_at?: string; comment?: string };
  };
  authorization: {
    status?: "AUTHORIZED" | "REVOKED";
    authorized_by?: string;
    authorized_by_display?: string;
    authorized_at?: string;
    comment?: string;
    revocation_reason?: string;
  };
  approval: {
    captured_at?: string;
    application?: Record<string, unknown>;
    documents?: { id: string; name: string; version: number; verification_status: string }[];
    contracts?: { id: string; template_name: string; status: string }[];
  };
}

export interface CreditReadiness {
  cbs_mapping_ready?: boolean;
  ready: boolean;
  show_checklist: boolean;
  checks: CreditReadinessCheck[];
  policy: Omit<
    CreditInstructionPolicy,
    "id" | "created_at" | "updated_at"
  >;
}

export interface NotificationLog {
  id: string;
  kind: string;
  kind_display: string;
  status: string;
  status_display: string;
  subject: string;
  recipients: string[];
  body_preview: string;
  error_message: string;
  workflow_instance_id: string | null;
  approval_task_id: string | null;
  created_at: string;
}

export interface CbsConnector {
  id: string;
  name: string;
  protocol: string;
  base_url: string;
  is_active: boolean;
  timeout_seconds: number;
  max_retries: number;
  mapping_rules?: Record<string, unknown>;
  created_at: string;
}

export interface IntegrationLog {
  id: string;
  connector: string;
  operation: string;
  direction: string;
  idempotency_key: string;
  status: string;
  attempts: number;
  external_reference: string;
  error_message: string;
  created_at: string;
}

export interface ReleaseFee {
  id: string;
  fee_type: string;
  fee_type_display: string;
  label: string;
  amount: string;
  payer: string;
  payer_display: string;
  fee_date: string | null;
  recoverable: boolean;
  notes: string;
  created_at: string;
}

export interface GuaranteeReleaseRequest {
  id: string;
  reference: string;
  guarantee: string;
  guarantee_reference: string;
  application: string | null;
  loan: string | null;
  agency: string | null;
  cbs_loan_reference: string;
  cbs_client_id?: string;
  cbs_settled: boolean | null;
  cbs_outstanding: string | null;
  cbs_currency: string;
  cbs_checked_at: string | null;
  cbs_raw: Record<string, unknown>;
  request_date?: string | null;
  release_fees?: string | null;
  fees?: ReleaseFee[];
  fees_client_total?: string | null;
  fees_institution_total?: string | null;
  acte_status?: string;
  acte_status_display?: string;
  acte_generated_at?: string | null;
  acte_signed_at?: string | null;
  acte_generated_url?: string | null;
  acte_signed_url?: string | null;
  has_client_demande?: boolean;
  has_generated_acte?: boolean;
  has_signed_acte?: boolean;
  can_deposit_signed_acte?: boolean;
  status: string;
  status_display: string;
  comment: string;
  completed_at: string | null;
  client_display: string;
  created_at: string;
  updated_at: string;
}

export interface ReleaseClientCredit {
  application_id: string;
  application_reference: string;
  application_status: string;
  application_status_display: string;
  product_label: string;
  amount: string;
  currency: string;
  loan_id: string | null;
  loan_status: string | null;
  loan_status_display: string | null;
  disbursed_at: string | null;
  cbs_loan_reference: string;
  cbs_settled: boolean | null;
  cbs_outstanding: string | null;
  cbs_currency: string;
  cbs_error: string | null;
  cbs_status_label: string;
}

export interface ReleaseClientContext {
  client_id: string;
  client_display: string;
  cbs_client_id: string;
  guarantees: Guarantee[];
  credits: ReleaseClientCredit[];
}

export interface DationAsset {
  id: string;
  source: "EXISTING_GUARANTEE" | "ADDITIONAL" | string;
  source_display: string;
  asset_type?: string;
  asset_type_display?: string;
  guarantee: string | null;
  guarantee_reference: string | null;
  guarantee_type_display: string | null;
  description: string;
  value: string | null;
  notes?: string;
  created_at: string;
}

export interface DationFee {
  id: string;
  asset: string | null;
  fee_type: string;
  fee_type_display: string;
  label: string;
  amount: string;
  payer: "CLIENT" | "INSTITUTION" | string;
  payer_display: string;
  fee_date: string | null;
  recoverable: boolean;
  notes: string;
  created_at: string;
}

export interface DationSettlement {
  assets_total: string;
  claim: string;
  fees_client_total: string;
  fees_institution_total: string;
  claim_to_cover: string;
  coverage_gap: string;
  residual_balance: string;
  surplus_amount: string;
  covers_claim: boolean | null;
}

export interface DationRequest {
  id: string;
  reference: string;
  client: string;
  client_display: string;
  application: string | null;
  application_reference?: string | null;
  collection_case_id?: string | null;
  agency: string | null;
  cbs_client_id: string;
  cbs_total_outstanding: string | null;
  cbs_currency: string;
  cbs_checked_at: string | null;
  cbs_raw: Record<string, unknown>;
  asset_description: string;
  asset_value: string | null;
  assets?: DationAsset[];
  fees?: DationFee[];
  assets_total_value?: string | null;
  fees_client_total?: string | null;
  fees_institution_total?: string | null;
  claim_to_cover?: string | null;
  residual_balance?: string | null;
  surplus_amount?: string | null;
  require_full_coverage?: boolean;
  settlement_notes?: string;
  covers_claim?: boolean | null;
  coverage_gap?: string | null;
  settlement?: DationSettlement;
  status: string;
  status_display: string;
  comment: string;
  resulting_guarantee: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FormalizationFee {
  id: string;
  fee_type: string;
  fee_type_display: string;
  label: string;
  amount: string;
  payer: "CLIENT" | "INSTITUTION" | string;
  payer_display: string;
  fee_date: string | null;
  recoverable: boolean;
  notes: string;
  created_at: string;
}

export interface FormalizationComposeCredit {
  application_id: string;
  application_reference: string;
  application_status: string;
  application_status_display: string;
  product_label: string;
  amount: string;
  currency: string;
  guarantees_count: number;
}

export interface FormalizationComposeContext {
  client_id: string;
  client_display: string;
  application_id: string | null;
  application_reference: string | null;
  credits: FormalizationComposeCredit[];
  guarantees: (Guarantee & {
    formalization_busy?: boolean;
    process_busy?: GuaranteeProcessBusy | null;
  })[];
}

export interface GuaranteeFormalizationRequest {
  id: string;
  reference: string;
  guarantee: string;
  guarantee_reference: string;
  client?: string | null;
  client_display: string;
  application: string | null;
  application_reference?: string | null;
  agency: string | null;
  status: string;
  status_display: string;
  legal_stage: string;
  legal_stage_display: string;
  notary_name: string;
  notary_reference: string;
  sent_to_notary_at: string | null;
  expected_return_date: string | null;
  registration_number: string;
  registration_date: string | null;
  registration_authority: string;
  acte_file_url?: string | null;
  acte_signed_file_url?: string | null;
  registration_proof_url?: string | null;
  fees?: FormalizationFee[];
  fees_client_total?: string | null;
  fees_institution_total?: string | null;
  comment: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GedDocument {
  verification_status?: "PENDING" | "VERIFIED" | "REJECTED";
  verified_by?: string | null;
  verified_at?: string | null;
  verification_comment?: string;
  id: string;
  category: string;
  category_label: string;
  category_code?: string;
  name: string;
  file: string;
  file_url?: string | null;
  mime_type: string;
  size_bytes: number;
  sha256?: string;
  version?: number;
  issue_date?: string | null;
  expiry_date?: string | null;
  content_type?: number | string | null;
  object_id: string;
  related_type?: string;
  related_kind?: string;
  related_label?: string;
  /** Chemin SPA fourni par l'API (préféré aux heuristiques front). */
  related_path?: string | null;
  uploaded_by?: string | null;
  uploaded_by_name?: string;
  created_at: string;
}

export interface Tenant {
  id: string;
  code: string;
  name: string;
  country: string;
  zone: string;
  currency: string;
  timezone: string;
  is_active: boolean;
  address: string;
  phone: string;
  email: string;
  logo: string | null;
  logo_url: string | null;
  brand_primary: string;
  brand_secondary: string;
  brand_accent: string;
  brand_sidebar: string;
  brand_sidebar_text: string;
  officers?: TenantOfficer[];
  created_at?: string;
  updated_at?: string;
}

export interface ClientPhone {
  id: string;
  number: string;
  label: string;
}

export interface Client {
  custom_fields?: Record<string, unknown>;
  id: string;
  reference: string;
  client_type: "INDIVIDUAL" | "PROFESSIONAL" | "CORPORATE";
  display_name: string;
  agency: string | null;
  // Personne physique
  civility: string;
  first_name: string;
  last_name: string;
  birth_date: string | null;
  birth_country: string;
  country: string;
  marital_status: string;
  nationality: string;
  profession: string;
  id_document_type: string;
  national_id: string;
  id_document_issue_date: string | null;
  id_document_expiry_date: string | null;
  id_document_scan: string | null;
  photo: string | null;
  spouse_last_name: string;
  spouse_first_name: string;
  spouse_phone: string;
  spouse_profession: string;
  father_last_name: string;
  father_first_name: string;
  mother_last_name: string;
  mother_first_name: string;
  // Personne morale
  company_name: string;
  sigle: string;
  legal_form: string;
  ifu: string;
  rccm: string;
  ifu_scan: string | null;
  rccm_scan: string | null;
  manager_last_name: string;
  manager_first_name: string;
  manager_phone: string;
  manager_email: string;
  manager_address: string;
  manager_id_document_type: string;
  manager_id_document_number: string;
  manager_id_document_issue_date: string | null;
  manager_id_document_expiry_date: string | null;
  manager_id_document_scan: string | null;
  manager_position: string;
  manager_birth_date: string | null;
  manager_birth_country: string;
  manager_birth_city: string;
  // Communs
  phone: string;
  email: string;
  address: string;
  city: string;
  postal_box: string;
  head_office: string;
  phones?: ClientPhone[];
  // Core Banking (mapping 1:1 situation adhérent)
  cbs_client_id: string;
  cbs_account_number: string;
  cbs_full_name: string;
  cbs_order_number: string;
  cbs_profession_id: string;
  cbs_nationality_id: string;
  cbs_sector_id: string;
  cbs_client_type_id: string;
  cbs_zone_id: string;
  cbs_savings_product_id: string;
  cbs_signature_count: number | null;
  cbs_distance: string | null;
  cbs_registration_date: string | null;
  cbs_creation_date: string | null;
  cbs_credit_limit: string | null;
  cbs_est_valide: boolean | null;
  cbs_point_of_service_id: string;
  cbs_point_of_service_name: string;
  cbs_external_id: string;
  cbs_context: string;
  cbs_message: string;
  cbs_synced_at: string | null;
  cbs_situation?: Record<string, unknown>;
  kyc_status: "PENDING" | "VALIDATED" | "REJECTED" | "EXPIRED";
  kyc_validated_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const CLIENT_LABELS = {
  civility: {
    MR: "Monsieur",
    MRS: "Madame",
    MISS: "Mademoiselle",
  } as Record<string, string>,
  marital_status: {
    SINGLE: "Célibataire",
    MARRIED: "Marié(e)",
    DIVORCED: "Divorcé(e)",
    WIDOWED: "Veuf/Veuve",
  } as Record<string, string>,
  id_document_type: {
    PASSPORT: "Passeport",
    CNI: "Carte nationale d'identité",
    DRIVING_LICENSE: "Permis de conduire",
    CONSULAR_CARD: "Carte consulaire",
  } as Record<string, string>,
  legal_form: {
    SARL: "SARL",
    SA: "SA",
    ASSOCIATION: "Association",
    INDIVIDUAL: "Entreprise individuelle",
    SASU: "SASU",
    SAS: "SAS",
    EURL: "EURL",
    SNC_SCS: "SNC / SCS",
  } as Record<string, string>,
  client_type: {
    INDIVIDUAL: "Personne physique",
    PROFESSIONAL: "Groupement",
    CORPORATE: "Personne morale",
  } as Record<string, string>,
};

export interface SuretyPhone {
  id: string;
  number: string;
  label: string;
}

export interface Surety {
  id: string;
  surety_type: "PHYSICAL" | "MORAL";
  display_name: string;
  name: string;
  first_name: string;
  last_name: string;
  birth_date: string | null;
  birth_country: string;
  activity: string;
  estimated_income: string | null;
  id_document_type: string;
  national_id: string;
  id_document_issue_date: string | null;
  id_document_expiry_date: string | null;
  id_document_scan: string | null;
  photo: string | null;
  // Entreprise
  company_name: string;
  legal_form: string;
  ifu: string;
  rccm: string;
  ifu_scan: string | null;
  rccm_scan: string | null;
  city: string;
  // Gérant
  manager_last_name: string;
  manager_first_name: string;
  manager_phone: string;
  manager_email: string;
  manager_address: string;
  manager_id_document_type: string;
  manager_id_document_number: string;
  manager_id_document_issue_date: string | null;
  manager_id_document_expiry_date: string | null;
  manager_id_document_scan: string | null;
  manager_position: string;
  manager_birth_date: string | null;
  manager_birth_country: string;
  manager_birth_city: string;
  // Coordonnées
  identifier: string;
  phone: string;
  email: string;
  address: string;
  phones?: SuretyPhone[];
  documents?: { id: string; title: string; file: string | null; created_at?: string }[];
  /** Client cautionné (engagements ouverts) — liste. */
  client_display?: string | null;
  /** Montant du crédit lié (dernier engagement ouvert) — liste. */
  credit_amount?: string | null;
  credit_currency?: string | null;
  /** Montant cautionné (engagement ouvert / total engagé) — liste. */
  guaranteed_amount?: string | null;
  commitment_ceiling: string;
  total_committed: string;
  available_ceiling: string;
  is_active: boolean;
  engagements?: SuretyEngagement[];
  created_at: string;
}

export interface CreditProduct {
  id: string;
  code: string;
  label: string;
  description?: string;
  category?: string | null;
  category_label?: string | null;
  client_type?: "INDIVIDUAL" | "PROFESSIONAL" | "CORPORATE" | "ALL";
  currency: string;
  amount_min: string;
  amount_max: string;
  duration_min_months?: number;
  duration_max_months?: number;
  interest_rate: string;
  processing_fee_rate?: string;
  requires_guarantee?: boolean;
  cbs_product_code?: string;
  cbs_repayment_product_code?: string;
  cbs_credit_product?: string | null;
  cbs_repayment_product?: string | null;
  is_active: boolean;
}

export interface CbsProductReference {
  id: string;
  connector: string;
  kind: "CREDIT" | "REPAYMENT";
  cbs_code: string;
  label: string;
  currency: string;
  source_reference: string;
  is_active: boolean;
  verification_status: "PENDING" | "VERIFIED";
  verified_at: string | null;
  verified_by: string | null;
  updated_at: string;
}

export interface StockPhoto {
  id: string;
  image: string;
  caption: string;
}

export interface ChecklistItem {
  label: string;
  provided: boolean;
}

export interface CreditDocument {
  id: string;
  application: string;
  file: string;
  label: string;
  created_at: string;
}

export interface CreditApplicationFee {
  id?: string;
  label: string;
  mode: "PERCENT" | "AMOUNT" | string;
  mode_display?: string;
  value: string;
  sort_order?: number;
}

export interface FeesBreakdownLine {
  source?: "TARIFF" | "MANUAL";
  tax_amount?: string;
  base_excluding_tax?: string;
  tax_rate?: string;
  id: string | null;
  label: string;
  mode: "PERCENT" | "AMOUNT" | string;
  value: string;
  amount: string | null;
  is_dossier: boolean;
}

export interface FeesBreakdown {
  total_taxes?: string;
  base_amount: string | null;
  lines: FeesBreakdownLine[];
  total: string | null;
  /** Indicatif : base − total frais (prélèvement effectué par le CBS). */
  net_after_fees?: string | null;
}

export interface PricingQuote {
  simulation_conventions?: import("./simulation").SimulationConventions;
  engine: "LEGACY" | "CONFIGURED"; currency: string; band: string | null;
  rates: { interest_rate: string; fees_rate: string; mandatory_savings_rate: string };
  defaults: { interest_rate: string; fees_rate: string; mandatory_savings_rate: string };
  failures: string[]; fees: FeesBreakdown; configuration_fingerprint: string;
}

export interface CreditApplication {
  id: string;
  reference: string;
  client: string;
  client_display: string;
  client_reference: string;
  client_type: string;
  product: string;
  product_label: string;
  agency: string | null;
  agency_display?: string;
  // Conditions
  amount_requested: string;
  amount_proposed: string | null;
  interest_rate: string | null;
  fees_rate: string | null;
  mandatory_savings_rate: string | null;
  extra_fees?: CreditApplicationFee[];
  fees_breakdown?: FeesBreakdown | null;
  pricing_quote?: PricingQuote;
  periodicity: string;
  periodicity_label?: string;
  duration_months: number;
  first_due_date: string | null;
  last_due_date: string | null;
  repayment_mechanism: string;
  repayment_mechanism_label?: string;
  purpose_type: string;
  financing_object?: string | null;
  purpose: string;
  request_letter_scan: string | null;
  currency: string;
  currency_label?: string;
  cbs_refs?: {
    financing_object?: { id?: string; code?: string; label?: string; cbs_code?: string };
    credit_product?: { id?: string; cbs_code?: string; label?: string; source_reference?: string };
    repayment_product?: { id?: string; cbs_code?: string; label?: string; source_reference?: string };
    errors?: Array<{ field: string; message: string }>;
    periodicity?: { code?: string; label?: string; cbs_code?: string };
    repayment_method?: { code?: string; label?: string; cbs_code?: string };
    currency?: { code?: string; label?: string; cbs_code?: string };
    product_cbs_code?: string;
    product_repayment_cbs_code?: string;
    manager_cbs_id?: string;
    client_adherent_id?: string;
    point_of_service_id?: string;
    warnings?: string[];
    ready_for_cbs?: boolean;
  };
  // Plan de financement
  project_total_cost: string | null;
  personal_contribution: string | null;
  financed_quota: string | null;
  // Activité (contexte opérationnel)
  activity_start_date: string | null;
  exact_address: string;
  clientele: string;
  tax_regime: string;
  avg_client_payment_days: number | null;
  avg_supplier_payment_days: number | null;
  stock_photos?: StockPhoto[];
  // Environnement commercial
  catchment_area: string;
  // Patrimoine
  premises_status: string;
  // Demandeur & emploi
  employer_name: string;
  contract_type: string;
  salary_domiciliation: boolean;
  dependents_count: number | null;
  // Relation bancaire
  client_account_number: string;
  relationship_start_date: string | null;
  avg_monthly_credit_movements: string | null;
  // Assurance
  has_credit_insurance: boolean;
  insurance_company: string;
  insurance_policy_number?: string;
  insurance_expiry_date?: string | null;
  insurance_premium: string | null;
  // Conditions particulières
  special_conditions: string;
  suspensive_conditions: string;
  // Conformité
  beneficial_owner: string;
  is_pep: boolean;
  funds_origin: string;
  // Complétude documentaire
  document_checklist: ChecklistItem[];
  documents?: CreditDocument[];
  // Suivi
  amount_approved: string | null;
  status: string;
  status_display: string;
  risk_level: number | null;
  submitted_at: string | null;
  submitted_by: string | null;
  submitted_by_display: string | null;
  disbursed_at?: string | null;
  disbursement_requested_at?: string | null;
  disbursement_requested_by?: string | null;
  setup_authorization?: CreditSetupState["authorization"];
  cbs_demande_number?: string;
  cbs_demande_ref?: string;
  cbs_contract_number?: string;
  cbs_operation_date?: string | null;
  created_by: string | null;
  created_by_display: string | null;
  collection_case_id?: string | null;
  collection_stage?: string;
  collection_stage_display?: string;
  loan_id?: string | null;
  created_at: string;
}

export interface FinancialDocument {
  id: string;
  file: string;
  label: string;
}

export interface FinancialAnalysisFlags {
  // Particulier
  debt_ratio_ok?: boolean | null;
  debt_ratio_stress_ok?: boolean | null;
  disposable_ok?: boolean | null;
  living_wage_ok?: boolean | null;
  quota_ok?: boolean | null;
  // Entreprise
  dscr_ok?: boolean | null;
  dscr_stress_ok?: boolean | null;
  leverage_ok?: boolean | null;
  gearing_ok?: boolean | null;
  autonomy_ok?: boolean | null;
  current_ratio_ok?: boolean | null;
  interest_coverage_ok?: boolean | null;
  // Commun
  guarantee_ok?: boolean | null;
  // Groupement
  capacity_ok?: boolean | null;
  members_ok?: boolean | null;
  solidarity_ok?: boolean | null;
  contributors_ok?: boolean | null;
  capacity_stress_ok?: boolean | null;
}

export interface AnalysisScoreComponent {
  key: string;
  label: string;
  score: number | null;
  weight: number;
  raw_value?: string | null;
  bad?: string;
  good?: string;
  direction?: "HIGH" | "LOW";
}

export interface AnalysisScoreBreakdown {
  engine?: "LEGACY" | "CUSTOM";
  risk_cutoffs?: string[];
  missing_data?: "RENORMALIZE" | "ZERO" | "BLOCK_SUBMIT";
  missing_metrics?: string[];
  effective_weight?: number;
  total: number | null;
  components: AnalysisScoreComponent[];
}

export type AnalysisMetrics = {
  flags: Record<string, boolean | null>;
} & Record<string, unknown>;

export type AnalysisThresholds = Record<string, number>;

export type AnalysisDetails = Record<string, string | Record<string, string>[] | undefined>;

export interface FinancialAnalysis {
  calculation_context?: {
    calculated_at: string; amount: number | null; amount_label: string; currency: string;
    periodicity: string; duration_months: number; mechanism: string; frozen: boolean;
    legacy?: boolean; captured_at?: string | null; application_status?: string;
    sources: { name: string; version: number }[]; rates: Record<string, string>;
  };
  recorded_indicators?: { updated_at: string } & Record<string, unknown>;
  custom_field_definitions?: import("@/api/configuration").CustomFieldDefinition[];
  custom_fields?: Record<string, unknown>;
  analysis_details?: AnalysisDetails;
  id: string;
  application: string;
  author_role: string;
  is_reference?: boolean;
  created_by: string | null;
  created_by_display: string;
  can_edit: boolean;
  client_type: string;
  client_type_source: string;
  /** Profil particulier : salarié / indépendant / mixte. */
  individual_profile?: "" | "SALARIE" | "INDEPENDANT" | "MIXTE";
  reference_period: string;
  analysis_date: string | null;
  // Cadre et fiabilité de l'analyse
  information_quality: string;
  financial_statement_date: string | null;
  bank_statement_months: number | null;
  financial_documents_verified: boolean;
  field_visit_confirmed: boolean;
  stock_count_verified: boolean;
  cash_position_verified: boolean;
  verification_comment: string;
  primary_repayment_source: string;
  // Endettement consolidé & centrale des risques
  active_loans_count: number;
  credit_bureau_checked: boolean;
  credit_bureau_date: string | null;
  has_payment_incidents: boolean;
  max_days_late: number | null;
  incidents_comment: string;
  prior_loans_count: number;
  prior_repayment_rate: string | null;
  prior_max_delay_days: number | null;
  // Particulier — charges informelles & stabilité
  tontine_expense: string;
  social_contributions: string;
  family_support_expense: string;
  net_salary: string;
  salary_deductions: string;
  employment_seniority_months: number | null;
  informal_income_weight: string | null;
  employment_type: string;
  employer_name: string;
  employer_sector: string;
  salary_paid_through_bank: boolean;
  salary_verified: boolean;
  variable_income: string;
  pension_income: string;
  other_monthly_obligations: string;
  personal_savings: string;
  personal_real_estate_value: string;
  personal_vehicle_value: string;
  personal_productive_assets: string;
  // Entreprise — court terme & N-1
  short_term_debt: string;
  turnover_prev: string;
  net_result_prev: string;
  // Indicateurs calculés (contre-analyse)
  debt_ratio_stress: string | null;
  dscr_stress: string | null;
  guarantee_coverage: string | null;
  metrics: AnalysisMetrics;
  thresholds: AnalysisThresholds;
  // Synthèse & scoring
  score_breakdown: AnalysisScoreBreakdown;
  strengths: string;
  weaknesses: string;
  recommended_conditions: string;
  // Analyse sectorielle
  sector: string;
  sub_sector: string;
  value_chain_position: string;
  market_dynamic: string;
  seasonality_level: string;
  competition_intensity: string;
  supplier_dependency: string;
  client_concentration: string;
  input_price_sensitivity: string;
  fx_exposure: string;
  regulatory_sensitivity: string;
  climate_sensitivity: string;
  sector_risk_level: string;
  sector_outlook: string;
  sector_comment: string;
  // Analyse environnementale & sociale (E&S)
  es_category: string;
  exclusion_list_ok: boolean;
  env_permit_required: boolean;
  env_permit_obtained: boolean;
  permit_reference: string;
  eia_required: boolean;
  eia_done: boolean;
  es_regulatory_compliance: boolean;
  waste_management: string;
  resource_use: string;
  chemicals_pesticides: string;
  nuisances_emissions: string;
  working_conditions: string;
  occupational_safety: string;
  child_forced_labor_risk: string;
  community_impact: string;
  land_resettlement_risk: string;
  jobs_created: number | null;
  jobs_maintained: number | null;
  jobs_women: number | null;
  jobs_youth: number | null;
  workforce_count?: number | null;
  es_mitigation_plan: string;
  es_action_required: boolean;
  es_insurance: boolean;
  es_risk_level: string;
  es_comment: string;
  // Particulier — revenus
  salary_income: string;
  spouse_income: string;
  rental_income: string;
  other_activity_income: string;
  other_income: string;
  // Particulier — charges
  rent_expense: string;
  food_expense: string;
  utilities_expense: string;
  transport_expense: string;
  education_expense: string;
  health_expense: string;
  other_household_expenses: string;
  // Entreprise — exploitation
  turnover: string;
  cogs: string;
  op_rent: string;
  op_salaries: string;
  op_utilities: string;
  op_transport: string;
  op_telecom: string;
  op_taxes: string;
  op_maintenance: string;
  op_other: string;
  depreciation: string;
  financial_charges: string;
  other_operating_income: string;
  // Entreprise — bilan
  stock_value: string;
  receivables: string;
  cash_available: string;
  fixed_assets: string;
  supplier_debt: string;
  ongoing_credit_balance: string;
  cash_in_hand: string;
  bank_balance: string;
  other_current_assets: string;
  land_building_value: string;
  equipment_value: string;
  vehicle_value: string;
  other_fixed_assets: string;
  tax_social_debt: string;
  other_current_debt: string;
  long_term_debt: string;
  shareholder_debt: string;
  // Commun — endettement existant
  existing_debt_institution: string;
  existing_debt_initial_amount: string;
  existing_debt_monthly: string;
  // Trésorerie prévisionnelle
  projected_monthly_inflows: string;
  projected_monthly_outflows: string;
  projected_monthly_surplus: string | null;
  cashflow_comment: string;
  // Activité génératrice de revenus / groupement
  has_side_activity?: boolean;
  activity_turnover?: string;
  activity_expenses?: string;
  activity_comment?: string;
  activity_name?: string;
  activity_business_age_months?: number | null;
  activity_sales_days?: number | null;
  activity_purchases?: string;
  activity_stock_value?: string;
  activity_receivables?: string;
  activity_cash_available?: string;
  activity_fixed_assets?: string;
  activity_supplier_debt?: string;
  activity_is_formal?: boolean;
  activity_records_available?: boolean;
  members_count?: number | null;
  active_contributing_members?: number | null;
  solidarity_commitment?: boolean;
  collective_contributions?: string;
  collective_savings?: string;
  collective_other_income?: string;
  collective_operating_expenses?: string;
  group_activity_turnover?: string;
  group_activity_expenses?: string;
  group_comment?: string;
  group_age_months?: number | null;
  members_with_arrears?: number | null;
  group_records_verified?: boolean;
  collective_savings_locked?: boolean;
  // Indicateurs calculés
  new_installment: string | null;
  repayment_capacity: string | null;
  collective_capacity?: string | null;
  debt_ratio: string | null;
  dscr: string | null;
  // Dérivées
  total_income: string;
  total_household_charges: string;
  disposable_income: string;
  dependents_count: number | null;
  disposable_per_capita: string | null;
  gross_margin: string;
  total_operating_expenses: string;
  ebe: string;
  net_result: string;
  cash_flow: string;
  total_assets: string;
  total_debts: string;
  equity: string;
  bfr: string;
  gross_margin_pct: string | null;
  net_margin_pct: string | null;
  // Décision
  internal_score: string | null;
  recommendation: string;
  comment: string;
  flags: FinancialAnalysisFlags;
  documents: FinancialDocument[];
  created_at: string;
  updated_at: string;
}

export const FINANCE_LABELS = {
  reference_period: {
    MONTHLY: "Mensuelle",
    QUARTERLY: "Trimestrielle",
    ANNUAL: "Annuelle",
  } as Record<string, string>,
  recommendation: {
    FAVORABLE: "Favorable",
    CONDITIONAL: "Favorable sous conditions",
    UNFAVORABLE: "Défavorable",
  } as Record<string, string>,
  risk_level: {
    LOW: "Faible",
    MEDIUM: "Moyen",
    HIGH: "Élevé",
  } as Record<string, string>,
  quality_level: {
    GOOD: "Satisfaisante",
    IMPROVE: "À améliorer",
    BAD: "Problématique",
  } as Record<string, string>,
  sector: {
    AGRICULTURE: "Agriculture / élevage / pêche",
    COMMERCE: "Commerce / négoce",
    INDUSTRY: "Industrie / transformation",
    CONSTRUCTION: "BTP / construction",
    TRANSPORT: "Transport / logistique",
    SERVICES: "Services",
    CRAFTS: "Artisanat",
    ICT: "TIC / numérique",
    TOURISM: "Tourisme / hôtellerie / restauration",
    HEALTH: "Santé",
    EDUCATION: "Éducation",
    ENERGY: "Énergie / mines",
    OTHER: "Autre",
  } as Record<string, string>,
  value_chain_position: {
    INPUTS: "Intrants / approvisionnement",
    PRODUCTION: "Production",
    PROCESSING: "Transformation",
    DISTRIBUTION: "Distribution / commerce",
    SERVICES: "Services",
  } as Record<string, string>,
  market_dynamic: {
    GROWTH: "En croissance",
    MATURE: "Mature / stable",
    DECLINE: "En déclin",
  } as Record<string, string>,
  es_category: {
    A: "A — Risque élevé",
    B: "B — Risque moyen",
    C: "C — Risque faible",
  } as Record<string, string>,
};

export const CREDIT_LABELS = {
  periodicity: {
    DAILY: "Journalier",
    WEEKLY: "Hebdomadaire",
    BIMONTHLY: "Bimensuelle",
    MONTHLY: "Mensuelle",
    QUARTERLY: "Trimestrielle",
    SEMIANNUAL: "Semestrielle",
    ANNUAL: "Annuelle",
  } as Record<string, string>,
  repayment_mechanism: {
    DEGRESSIVE: "Amortissement dégressif",
    IN_FINE: "In fine (capital à terme)",
    BULLET: "Remboursement unique (bullet)",
    CONSTANT: "Échéances constantes (historique)",
  } as Record<string, string>,
  tax_regime: {
    SYNTHETIC: "Impôt synthétique",
    REAL: "Régime réel",
    SPECIFIC_EXEMPTION: "Exonérations spécifiques",
    INFORMAL: "Secteur informel",
  } as Record<string, string>,
  catchment_area: {
    LOCAL: "Local",
    NATIONAL: "National",
    EXPORT: "Export",
  } as Record<string, string>,
  premises_status: {
    OWNER: "Propriétaire",
    TENANT: "Locataire",
  } as Record<string, string>,
  purpose_type: {
    WORKING_CAPITAL: "Fonds de roulement",
    EQUIPMENT: "Investissement / équipement",
    STOCK: "Achat de stock",
    REAL_ESTATE: "Immobilier",
    TREASURY: "Trésorerie",
    CONSUMPTION: "Consommation",
    OTHER: "Autre",
  } as Record<string, string>,
  contract_type: {
    CDI: "CDI",
    CDD: "CDD",
    CIVIL_SERVANT: "Fonctionnaire",
    INDEPENDENT: "Indépendant",
    RETIRED: "Retraité",
    OTHER: "Autre",
  } as Record<string, string>,
  risk_class: {
    A: "A — Excellent",
    B: "B — Bon",
    C: "C — Moyen",
    D: "D — Faible",
    E: "E — Très risqué",
  } as Record<string, string>,
};

export interface FieldVisit {
  id: string;
  application: string;
  visit_date: string;
  visited_by: string | null;
  visited_by_display: string | null;
  visitor_role: string;
  can_edit: boolean;
  geo_coordinates: string;
  report: string;
  created_at?: string;
}

export interface SuretyEngagement {
  id: string;
  surety: string;
  surety_display: string;
  surety_activity: string;
  surety_type?: "PHYSICAL" | "MORAL";
  surety_id_document_scan: string | null;
  surety_photo: string | null;
  application: string;
  application_reference?: string | null;
  client_display?: string;
  amount: string;
  engagement_type?: "SIMPLE" | "SOLIDAIRE" | string;
  engagement_type_display?: string;
  signed_date: string | null;
  status: string;
  status_display?: string;
  notes?: string;
  released_at?: string | null;
  called_at?: string | null;
  contract_id?: string | null;
  contract_status?: string | null;
  contract_status_display?: string | null;
  contract_file_url?: string | null;
  contract_signed_file_url?: string | null;
  contract_template_name?: string | null;
  created_at: string;
}

export interface RejectReason {
  id: string;
  code: string;
  label: string;
  description: string;
  is_active: boolean;
}

/** Pièce de check-list catalogue (liée à un produit). */
export interface ProductChecklistItem {
  id: string;
  product: string;
  product_label?: string;
  label: string;
  is_mandatory: boolean;
  order: number;
}

export interface DocumentCategory {
  id: string;
  code: string;
  label: string;
  description: string;
  tracks_expiry: boolean;
  is_active: boolean;
}

export interface AnalysisThresholdConfig {
  id: string;
  max_debt_ratio: string;
  min_dscr: string;
  max_leverage_ratio: string;
  min_living_wage_per_capita: string;
  min_interest_coverage: string;
  max_gearing: string;
  min_financial_autonomy: string;
  min_current_ratio: string;
  min_guarantee_coverage: string;
  stress_pct: string;
  transferable_quota_fraction: string;
  informal_income_weight: string;
  haircut_mortgage: string;
  haircut_vehicle: string;
  haircut_jewelry: string;
  haircut_financial_deposit: string;
  haircut_financial_security: string;
  haircut_other: string;
  created_at?: string;
  updated_at?: string;
}

export interface ApprovalTaskApplication {
  id: string;
  reference: string;
  client_display: string;
  amount_requested: string;
  amount_proposed: string | null;
  currency: string;
}

export interface ApprovalTask {
  is_committee?: boolean;
  committee_quorum?: number;
  committee_majority?: "SIMPLE" | "QUALIFIED" | "UNANIMOUS";
  committee_majority_numerator?: number;
  committee_majority_denominator?: number;
  committee_abstentions?: "INCLUDE" | "EXCLUDE";
  committee_record_required?: boolean;
  committee_pv_required?: boolean;
  sla_mode?: "CALENDAR" | "BUSINESS";
  id: string;
  instance: string;
  step: string;
  step_name: string;
  step_order: number;
  step_kind: string;
  allow_return: boolean;
  status: string;
  opinion: string;
  opinion_display: string;
  decision_comment: string;
  proposed_amount: string | null;
  reject_reason: string | null;
  acted_by: string | null;
  acted_by_display: string | null;
  acted_at: string | null;
  due_at: string | null;
  application: ApprovalTaskApplication | null;
  target_meta?: {
    kind: string;
    id: string;
    reference: string;
    detail_path: string | null;
  } | null;
}

export interface MyDossierRow {
  id: string;
  target_kind?: "CREDIT" | "MAIN_LEVEE" | "DATION" | "FORMALISATION" | string;
  detail_path?: string;
  reference: string;
  client_display: string;
  client_type: "" | "INDIVIDUAL" | "PROFESSIONAL" | "CORPORATE";
  client_type_display: string;
  amount_requested: string;
  amount_proposed: string | null;
  currency: string;
  status: string;
  status_display: string;
  product_label: string;
  created_by_id?: string | null;
  created_by_display: string;
  created_at: string | null;
  definition_name: string;
  instance_status: string;
  current_step_name: string;
  current_step_role?: string;
  current_step_label?: string;
  current_order: number;
  my_task_status: string | null;
  my_step_name: string;
  my_step_order: number | null;
  my_task_due_at: string | null;
  is_actionable: boolean;
  is_treated?: boolean;
}

export interface ApprovalCondition {
  id: string;
  application: string;
  task: string;
  step_name: string;
  description: string;
  status: string;
  issued_by: string | null;
  issued_by_display: string | null;
  issued_at: string;
  lifted_by: string | null;
  lifted_by_display: string | null;
  lifted_at: string | null;
  lift_comment: string;
  validated_by: string | null;
  validated_by_display: string | null;
  validated_at: string | null;
  validation_comment: string;
  can_lift: boolean;
  can_validate: boolean;
  created_at: string;
}

export const WORKFLOW_LABELS = {
  opinion: {
    FAVORABLE: "Favorable",
    FAVORABLE_SOUS_RESERVE: "Favorable sous réserve",
    DEFAVORABLE: "Défavorable",
  } as Record<string, string>,
  step_kind: {
    CONSULTATIVE: "Consultative",
    DECISIONAL: "Décisionnelle",
  } as Record<string, string>,
  target_type: {
    CREDIT: "Dossier de crédit",
    MAIN_LEVEE: "Main levée",
    DATION: "Dation en paiement",
    FORMALISATION: "Formalisation de garantie",
  } as Record<string, string>,
  condition_status: {
    PENDING: "En attente de levée",
    LIFTED: "Levée — en attente de validation",
    VALIDATED: "Validée",
  } as Record<string, string>,
  instance_status: {
    IN_PROGRESS: "En cours",
    AWAITING_CONDITIONS: "En attente de levée des réserves",
    APPROVED: "Approuvé",
    REJECTED: "Rejeté",
    RETURNED: "Retourné pour correction",
    CANCELLED: "Annulé",
  } as Record<string, string>,
};

export interface GuaranteePhoto {
  id: string;
  image: string;
  caption: string;
}

export interface GuaranteeDocument {
  id: string;
  title: string;
  file: string | null;
  created_at?: string;
}

export interface GuaranteeJewelryItem {
  id?: string;
  nature: string;
  weight: string | number | null;
  description: string;
}

export interface GuaranteeMovement {
  id: string;
  guarantee: string;
  movement_type: string;
  movement_type_display?: string;
  movement_date: string;
  value: string | null;
  target_application: string | null;
  comment: string;
}

export interface GuaranteeProcessBusy {
  kind: "DATION" | "FORMALIZATION" | "RELEASE" | string;
  id: string;
  label: string;
  message: string;
}

export interface Guarantee {
  id: string;
  reference: string;
  guarantee_type: string;
  type_display: string;
  pledge_category: string;
  client: string;
  client_display?: string | null;
  application: string | null;
  application_reference?: string | null;
  collection_case_id?: string | null;
  collection_stage_display?: string;
  agency?: string | null;
  agency_name?: string | null;
  belongs_to_applicant?: boolean;
  surety?: string | null;
  surety_display?: string | null;
  description: string;
  owners: string;
  expertise_value: string;
  current_value: string;
  is_insured: boolean;
  insurance_reference: string;
  // Propriétaire
  owner_last_name: string;
  owner_first_name: string;
  owner_marital_status: string;
  matrimonial_regime: string;
  // Hypothèque
  document_type: string;
  document_number: string;
  document_issue_date: string | null;
  document_validity_date?: string | null;
  address: string;
  expertise_date: string | null;
  expertise_firm: string;
  expert_name: string;
  expertise_reference?: string;
  value_to_consider: string | null;
  ltv_ratio: string | null;
  occupancy_status: string;
  document_scan: string | null;
  expertise_report_scan: string | null;
  lease_contract_scan: string | null;
  legal_situation_certificate_scan: string | null;
  // Gage — moyen roulant
  chassis_number: string;
  engine_number: string;
  brand: string;
  model_name: string;
  registration: string;
  power: string;
  first_registration_year: number | null;
  acquisition_date: string | null;
  acquisition_value: string | null;
  resale_value: string | null;
  estimation_date: string | null;
  registration_card_scan: string | null;
  mechanical_expertise_scan: string | null;
  technical_inspection_scan: string | null;
  insurance_scan: string | null;
  purchase_invoice_scan: string | null;
  additional_info: string;
  // Gage — objet de valeur
  raw_material_price: string | null;
  expertise_certificate_scan: string | null;
  origin_certificate_scan: string | null;
  jewelry_items?: GuaranteeJewelryItem[];
  // Garantie financière
  financial_type: string;
  account_number: string;
  balance: string | null;
  remuneration_rate: string | null;
  deposit_maturity_date: string | null;
  isin_code: string;
  volatility_history: string;
  security_discount: string | null;
  pledge_deed_scan: string | null;
  // Suivi
  status: string;
  status_display?: string;
  last_valuation_date: string | null;
  registration_number?: string;
  registration_date?: string | null;
  registration_authority?: string;
  formalized_at?: string | null;
  open_formalization_id?: string | null;
  open_dation_id?: string | null;
  open_release_id?: string | null;
  completed_dation_id?: string | null;
  origin_dation_id?: string | null;
  process_busy?: GuaranteeProcessBusy | null;
  photos?: GuaranteePhoto[];
  documents?: GuaranteeDocument[];
  movements?: GuaranteeMovement[];
  renewed_from?: string | null;
  renewed_from_reference?: string | null;
  created_at?: string;
  updated_at?: string;
}

export const GUARANTEE_LABELS = {
  guarantee_type: {
    MORTGAGE: "Hypothèque",
    PLEDGE: "Gage",
    FINANCIAL: "Garantie financière",
    LIEN: "Nantissement",
    DEPOSIT: "Dépôt de garantie",
    BANK_GUARANTEE: "Garantie bancaire",
    DATION: "Dation en paiement",
    JOINT: "Garantie solidaire",
    OTHER: "Autre",
  } as Record<string, string>,
  pledge_category: {
    VEHICLE: "Moyen roulant",
    VALUABLE: "Objet de valeur",
  } as Record<string, string>,
  document_type: {
    LAND_TITLE: "Titre foncier",
    ATTRIBUTION_CERT: "Attestation d'attribution",
    EXPLOITATION_PERMIT: "Permis d'exploiter",
    BUILDING_PERMIT: "Permis de construire",
    OCCUPANCY_PERMIT: "Permis d'habiter",
    LEASEHOLD: "Bail emphytéotique",
    SURFACE_RIGHT: "Droit de superficie",
    SALES_DEED: "Acte de vente / compromis",
    CADASTRAL_EXTRACT: "Extrait cadastral",
    CUSTOMARY_TITLE: "Titre / certificat coutumier",
    URBAN_CERT: "Certificat d'urbanisme",
    OTHER_REAL_ESTATE: "Autre titre immobilier",
    REGISTRATION_CARD: "Carte grise",
    PURCHASE_INVOICE: "Facture d'achat",
    CUSTOMS_CLEARANCE: "Déclaration en douane",
    TRANSFER_CERT: "Certificat de cession",
    INSURANCE_CERT: "Attestation d'assurance",
    TECH_INSPECTION: "Visite technique",
    OTHER_VEHICLE: "Autre document véhicule",
  } as Record<string, string>,
  matrimonial_regime: {
    COMMUNITY: "Communauté de biens",
    SEPARATION: "Séparation de biens",
  } as Record<string, string>,
  occupancy_status: {
    FREE: "Libre",
    FAMILY_HOME: "Domicile familial",
    DEVELOPER: "Occupé par le promoteur",
    RENTED: "En location",
  } as Record<string, string>,
  financial_type: {
    DAT: "Dépôt à terme (DAT)",
    SAVINGS: "Épargne",
    SECURITY: "Titre",
  } as Record<string, string>,
  marital_status: {
    SINGLE: "Célibataire",
    MARRIED: "Marié(e)",
    DIVORCED: "Divorcé(e)",
    WIDOWED: "Veuf/Veuve",
  } as Record<string, string>,
  status: {
    ACTIVE: "Active",
    RELEASED: "Mainlevée",
    REALIZED: "Réalisée",
    TRANSFERRED: "Transférée",
  } as Record<string, string>,
};

export interface AuditLog {
  id: string;
  user_display: string;
  action: string;
  model_label: string;
  object_id?: string;
  object_repr: string;
  changes?: Record<string, unknown>;
  ip_address: string | null;
  timestamp: string;
}

export interface DashboardData {
  scope: "FILIALE" | "GROUPE";
  filters_applied?: Record<string, string>;
  credits: {
    summary: {
      total: number;
      amount_requested: string | null;
      amount_approved: string | null;
      approved_count: number;
      rejected_count: number;
      returned_count?: number;
      draft_count?: number;
      disbursed_count: number;
      disbursed_amount: string | null;
      pending_count: number;
      in_approval_count: number;
      contract_generated_count?: number;
      disbursement_pending_count?: number;
      disbursement_pending_amount?: string | null;
    };
    by_status: { status: string; count: number; amount: string | null }[];
    by_product: { product: string; count: number; amount: string | null }[];
    by_agency?: {
      agency_id: string;
      agency: string;
      count: number;
      amount: string | null;
    }[];
    monthly: { month: string; count: number; amount: string | number | null }[];
    recent: {
      id: string;
      reference: string;
      client: string;
      product: string;
      amount: string | null;
      status: string;
      created_at: string;
      owner?: string;
      agency?: string;
    }[];
    funnel?: {
      submitted: number;
      in_approval: number;
      approved: number;
      disbursed: number;
      rejected: number;
      returned: number;
      approval_rate_pct: number | null;
      disbursement_rate_pct: number | null;
    };
  };
  portfolio: {
    active_loans: number;
    total_loans: number;
    disbursed_total: string | number | null;
    outstanding: string | number | null;
    overdue_installments: number;
  };
  clients: {
    total: number;
    by_type: { client_type: string; count: number }[];
    new_this_month: number;
    new_period_label?: "month" | "period";
  };
  guarantees: {
    count: number;
    active_count?: number;
    total_current_value: string | null;
    active_value?: string | null;
  };
  contracts?: {
    generated: number;
    signed: number;
    total: number;
  };
  workflow?: {
    pending_tasks: number;
    overdue_tasks?: number;
    my_pending_tasks: number;
    my_overdue_tasks?: number;
    conditions_pending: number;
  };
  risk: {
    by_par_class: { par_class: string; count: number; amount: string | null }[];
    by_stage?: { stage: string; count: number; amount: string | null }[];
    open_cases?: number;
    total_overdue: string | number;
    followups_due?: number;
    pending_promises?: number;
    broken_promises_30d?: number;
  };
  quality?: {
    kyc_pending: number;
    kyc_rejected: number;
    pipeline_without_active_guarantee: number;
  };
  after_sales?: {
    access: {
      main_levee: boolean;
      dation: boolean;
      formalisation: boolean;
      collection: boolean;
    };
    main_levee?: { open: number; in_approval: number };
    dation?: { open: number; in_approval: number };
    formalisation?: { open: number; in_approval: number };
  };
  cbs?: {
    failed: number;
    pending: number;
    retry: number;
  };
}

export interface SimulationScheduleRow {
  number: number;
  due_date: string;
  nominal_due_date?: string;
  principal: string | number;
  interest: string | number;
  savings: string | number;
  institution_due: string | number;
  total: string | number;
  balance: string | number;
}

/** Réponse du moteur partagé de simulation et d'échéanciers. */
export interface SimulationResult {
  simulation_conventions?: import("./simulation").SimulationConventions;
  pricing_quote?: PricingQuote;
  total_fees?: string | number;
  total_cost_excluding_savings?: string | number;
  total_client_outflow?: string | number;
  parameters?: { amount: string | number; annual_rate: string; savings_rate: string; months: number; periodicity: string; mechanism: string; simulation_date: string; first_due_date: string | null; currency: string };
  installment: string | number;
  monthly_payment: string | number;
  client_total_first: string | number;
  total_repayment: string | number;
  total_institution: string | number;
  total_interest: string | number;
  total_savings: string | number;
  schedule: SimulationScheduleRow[];
}

// ------------------------------------------------------------------------- //
// Contrats
// ------------------------------------------------------------------------- //
export interface ContractExtraField {
  key: string;
  label: string;
  type?: "text" | "date" | "number";
}

export interface ContractTemplate {
  id: string;
  code: string;
  name: string;
  category: string;
  category_display: string;
  description: string;
  engine: "DOCX" | "XLSX";
  file: string;
  applies_to: "ANY" | "INDIVIDUAL" | "CORPORATE";
  applies_to_display: string;
  product: string | null;
  product_label: string | null;
  amount_min: string | null;
  amount_max: string | null;
  extra_fields: ContractExtraField[];
  is_required: boolean;
  is_active: boolean;
  ordering: number;
  created_at: string;
}

export interface ApplicableTemplate {
  template: ContractTemplate;
  generated: boolean;
  generated_contract_id: string | null;
}

export interface GeneratedContract {
  id: string;
  application: string;
  template: string | null;
  template_name: string;
  category: string;
  file: string;
  status: "GENERATED" | "SIGNED" | "CANCELLED";
  status_display: string;
  signed_file: string | null;
  signed_at: string | null;
  notes: string;
  extra_values: Record<string, string>;
  created_by_name: string | null;
  created_at: string;
}

export interface VariableCatalogGroup {
  group: string;
  items: [string, string][];
}

export interface VariableCatalog {
  groups: VariableCatalogGroup[];
  loop_help: string;
}

export type CollectionStage =
  | "AMICABLE"
  | "PRECONTENTIOUS"
  | "LITIGATION"
  | "CLOSED";

export type ParClass =
  | "PAR0"
  | "PAR1_30"
  | "PAR31_90"
  | "PAR91_180"
  | "PAR180_PLUS";

export type CollectionActionType =
  | "CALL"
  | "SMS"
  | "EMAIL"
  | "LETTER"
  | "VISIT"
  | "LEGAL"
  | "DATION";

export type PromiseStatus = "PENDING" | "KEPT" | "BROKEN";

export type InstallmentStatus = "PENDING" | "PAID" | "PARTIAL" | "OVERDUE";

export interface CollectionAction {
  id: string;
  case: string;
  action_type: CollectionActionType;
  action_type_display: string;
  action_date: string;
  result: string;
  comment: string;
  next_follow_up_date?: string | null;
  attachment?: string | null;
  attachment_url?: string | null;
  created_by?: string | null;
  created_by_name?: string | null;
  updated_by?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  can_edit?: boolean;
  dialogue?: CollectionDialogueMessage[];
}

export interface PaymentPromise {
  id: string;
  case: string;
  amount: string;
  promised_date: string;
  status: PromiseStatus;
  status_display: string;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at?: string;
  can_edit?: boolean;
}

export type CollectionDialogueKind =
  | "QUESTION"
  | "REQUEST"
  | "RECOMMENDATION"
  | "REPLY";

export interface CollectionDialogueMessage {
  id: string;
  case: string;
  action?: string | null;
  kind: CollectionDialogueKind;
  kind_display: string;
  body: string;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at?: string;
  can_edit?: boolean;
}

export interface CollectionStageHistory {
  id: string;
  from_stage: CollectionStage | "";
  from_stage_display: string;
  to_stage: CollectionStage;
  to_stage_display: string;
  reason: string;
  automatic: boolean;
  changed_by: string | null;
  changed_by_name: string | null;
  created_at: string;
}

export type CollectionTrancheOwner =
  | "GESTIONNAIRE"
  | "COLLECTION"
  | "LEGAL";

export interface CollectionTranche {
  id: string;
  position: number;
  name: string;
  min_days_overdue: number;
  max_days_overdue: number | null;
  owner_kind: CollectionTrancheOwner;
  owner_kind_display: string;
  days_label: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CollectionEscalationRule {
  id: string;
  min_days_overdue: number;
  target_stage: Exclude<CollectionStage, "CLOSED">;
  target_stage_display: string;
  is_active: boolean;
  label: string;
  created_at: string;
  updated_at: string;
}

export interface CollectionGuaranteeLink {
  id: string;
  guarantee_type: string;
  guarantee_type_display: string;
  status: string;
  status_display: string;
  description: string;
  current_value: string;
}

export interface CollectionDationLink {
  id: string;
  reference?: string;
  status: string;
  status_display: string;
  residual_balance?: string | null;
  covers_claim?: boolean | null;
  created_at: string;
}

export interface AgentCollectionDashboard {
  scope?: "mine" | "team";
  assigned_open: number;
  unassigned_open?: number;
  followups_due: number;
  pending_promises: number;
  broken_promises_30d: number;
  repayments_this_month_count: number;
  repayments_this_month_amount: string;
  settled_this_month?: number;
  by_par_class: Record<string, number>;
  by_stage: Record<string, number>;
  due_followups: Array<{
    id: string;
    application_reference: string;
    client_name: string;
    next_action_date: string | null;
    next_action_type: string;
    next_action_note: string;
    days_overdue: number;
    overdue_amount: string;
    par_class: ParClass;
    stage: CollectionStage;
    assigned_to_name?: string | null;
  }>;
  as_of: string;
}

export interface LoanRepayment {
  id: string;
  loan: string;
  amount: string;
  payment_date: string;
  reference: string;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at: string;
}

export interface LoanInstallment {
  id: string;
  number: number;
  due_date: string;
  total_due: string;
  amount_paid: string;
  balance: string;
  status: InstallmentStatus;
  status_display: string;
}

export type LegalPartyType =
  | "LAW_FIRM"
  | "LAWYER"
  | "BAILIFF"
  | "NOTARY"
  | "EXPERT"
  | "OTHER";

export interface LegalParty {
  id: string;
  party_type: LegalPartyType;
  party_type_display: string;
  name: string;
  registration_no: string;
  contact_name: string;
  phone: string;
  email: string;
  address: string;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type LitigationStatus =
  | "PRE_LITIGATION"
  | "FILED"
  | "IN_PROGRESS"
  | "JUDGMENT"
  | "ENFORCEMENT"
  | "APPEAL"
  | "SETTLED"
  | "ABANDONED"
  | "CLOSED"
  | "OPEN"
  | "SUSPENDED";

export type LitigationActionType =
  | "PAYMENT_ORDER"
  | "SUMMONS"
  | "SUMMARY"
  | "ATTACHMENT"
  | "OHADA"
  | "APPEAL"
  | "OTHER";

export type LitigationEventType =
  | "NOTICE"
  | "FILING"
  | "HEARING"
  | "BRIEF"
  | "JUDGMENT"
  | "SERVICE"
  | "SEIZURE"
  | "APPEAL"
  | "SETTLEMENT"
  | "OTHER";

export interface LitigationEvent {
  id: string;
  litigation?: string;
  event_date: string;
  event_time?: string | null;
  event_type: LitigationEventType;
  event_type_display: string;
  location?: string;
  outcome?: string;
  amount?: string | null;
  postponed?: boolean;
  next_date?: string | null;
  performed_by?: string | null;
  performed_by_detail?: LegalParty | null;
  comment: string;
  created_at: string;
  updated_at?: string;
}

export interface LitigationSeizure {
  id: string;
  seizure_type: string;
  seizure_type_display: string;
  status: string;
  status_display: string;
  seizure_date: string | null;
  amount: string | null;
  bailiff: string | null;
  bailiff_detail?: LegalParty | null;
  guarantee: string | null;
  report_reference: string;
  inventory: string;
  notes: string;
  created_at: string;
}

export interface LitigationCost {
  id: string;
  cost_type: string;
  cost_type_display: string;
  label: string;
  amount: string;
  cost_date: string;
  is_paid: boolean;
  recoverable: boolean;
  party: string | null;
  party_detail?: LegalParty | null;
  notes: string;
  created_at: string;
}

export interface LitigationDocument {
  id: string;
  name: string;
  file: string | null;
  category: string;
  mime_type?: string;
  size_bytes?: number;
  created_at: string;
}

export interface LitigationFile {
  id: string;
  case: string;
  application_id?: string | null;
  client_id?: string | null;
  title: string;
  action_type: LitigationActionType | "";
  action_type_display?: string;
  court_name: string;
  court_registry?: string;
  case_reference: string;
  chamber?: string;
  law_firm?: string | null;
  law_firm_detail?: LegalParty | null;
  lawyer_party?: string | null;
  lawyer_party_detail?: LegalParty | null;
  bailiff_party?: string | null;
  bailiff_party_detail?: LegalParty | null;
  lawyer: string;
  bailiff: string;
  mandate_start?: string | null;
  mandate_end?: string | null;
  mandate_fee?: string | null;
  mandate_notes?: string;
  claimed_principal?: string | null;
  claimed_interest?: string | null;
  claimed_penalties?: string | null;
  claimed_costs?: string | null;
  claimed_total?: string | null;
  notice_date?: string | null;
  filing_date: string | null;
  service_date?: string | null;
  first_hearing_date?: string | null;
  hearing_date: string | null;
  hearing_time?: string | null;
  hearing_location?: string;
  judgment_date?: string | null;
  judgment_outcome?: string;
  judgment_outcome_display?: string;
  judgment_amount?: string | null;
  judgment_enforceable?: boolean;
  judgment_served_at?: string | null;
  status: LitigationStatus;
  status_display: string;
  notes: string;
  related_guarantee_ids?: string[];
  events?: LitigationEvent[];
  seizures?: LitigationSeizure[];
  costs?: LitigationCost[];
  can_operate?: boolean;
  created_at: string;
  updated_at: string;
}

export interface HearingAgendaItem {
  id: string;
  case_id: string;
  title: string;
  case_reference: string;
  application_reference: string;
  client_name: string;
  hearing_date: string | null;
  hearing_time: string | null;
  hearing_location: string;
  court_name: string;
  status: string;
  law_firm_name: string;
}

export interface LoanRestructurePreviewRow {
  number: number;
  due_date: string;
  principal: string;
  interest: string;
  savings: string;
  total: string;
  balance: string;
}

export interface LoanRestructurePreview {
  outstanding_principal: string;
  new_duration_months: number;
  new_rate: string;
  rows: LoanRestructurePreviewRow[];
  count: number;
  first_due_date: string | null;
  last_due_date: string | null;
  total_repayment: string;
  cbs_note?: string;
}

export interface LoanRestructure {
  id: string;
  loan?: string;
  case?: string | null;
  origin?: string;
  origin_display?: string;
  request_kind?: string;
  request_kind_display?: string;
  effective_date: string;
  first_due_date?: string | null;
  previous_duration_months: number;
  new_duration_months: number;
  previous_rate: string;
  new_rate: string;
  outstanding_principal: string;
  proposed_schedule?: LoanRestructurePreview | Record<string, unknown>;
  reason: string;
  status: string;
  status_display?: string;
  requested_by?: string | null;
  requested_by_name?: string | null;
  applied_by?: string | null;
  applied_by_name?: string | null;
  decided_at?: string | null;
  decision_comment?: string;
  cbs_note?: string;
  created_at: string;
}

export interface WriteOff {
  id: string;
  amount: string;
  write_off_date: string;
  reason: string;
  status?: string;
  status_display?: string;
  requested_by?: string | null;
  requested_by_name?: string | null;
  approved_by?: string | null;
  approved_by_name?: string | null;
  decided_at?: string | null;
  decision_comment?: string;
  created_at: string;
}

export interface LoanDetail {
  id: string;
  application: string;
  application_reference: string;
  currency: string;
  principal: string;
  interest_rate: string;
  duration_months: number;
  disbursed_at: string;
  first_due_date: string;
  status: string;
  outstanding_principal?: string;
  collection_case_id?: string | null;
  financial_ops_frozen?: boolean;
  financial_ops_frozen_reason?: string;
  restructures?: LoanRestructure[];
  write_offs?: WriteOff[];
}

export interface CollectionCase {
  id: string;
  loan: string;
  loan_status: string;
  loan_principal: string;
  application_id: string;
  application_reference: string;
  product_name?: string;
  client_id?: string | null;
  client_name: string;
  agency_name: string;
  stage: CollectionStage;
  stage_display: string;
  tranche?: string | null;
  tranche_name?: string;
  tranche_owner_kind?: CollectionTrancheOwner | "";
  tranche_owner_kind_display?: string;
  par_class: ParClass;
  par_class_display: string;
  days_overdue: number;
  overdue_amount: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  next_action_date?: string | null;
  next_action_type?: CollectionActionType | "";
  next_action_type_display?: string;
  next_action_note?: string;
  stage_changed_at?: string | null;
  cbs_synced_at?: string | null;
  cbs_sync_error?: string;
  next_due_date?: string | null;
  pending_promises_count?: number;
  guarantees_count?: number;
  outstanding_principal?: string;
  can_operate?: boolean;
  can_comment?: boolean;
  financial_ops_frozen?: boolean;
  financial_ops_frozen_reason?: string;
  blocking_dation?: CollectionDationLink | null;
  can_collect?: boolean;
  created_at: string;
  actions?: CollectionAction[];
  promises?: PaymentPromise[];
  dialogue?: CollectionDialogueMessage[];
  stage_history?: CollectionStageHistory[];
  restructures?: LoanRestructure[];
  write_offs?: WriteOff[];
  litigation?: LitigationFile | null;
  litigations?: LitigationFile[];
  repayments?: LoanRepayment[];
  installments?: LoanInstallment[];
  guarantees?: CollectionGuaranteeLink[];
  dation_requests?: CollectionDationLink[];
  surety_engagements?: SuretyEngagement[];
  core_banking_reference?: string;
}
