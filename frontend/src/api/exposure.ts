export interface ExposureRules {
  enabled: boolean; currency: string; gate: "ALERT" | "SUBMIT" | "APPROVE" | "SETUP";
  include_pending: boolean; client_limit: string | null; group_limit: string | null;
  maximum_age_days: number; require_verified_snapshot: boolean; use_cbs_client_limit: boolean;
}
export interface ExposureObservation {
  id: string; client: string; currency: string; as_of: string; drawn_principal: string;
  undrawn_commitments: string; guarantees_given: string; source_reference: string;
  evidence: string; completeness_confirmed: boolean; note: string; status: "DRAFT" | "VERIFIED" | "REVOKED";
  created_by: string; updated_by: string | null; verified_by: string | null; verified_at: string | null;
}
export interface ExposureAssessment {
  enabled: boolean; gate: string; currency: string; client_total: string | null; group_total: string | null;
  client_limit: string | null; group_limit: string | null; failures: string[]; complete: boolean; restricted: boolean; note: string;
  has_linked_group: boolean;
  members: { client: string; observation: string | null; as_of: string | null; source_reference: string;
    external_total: string | null; pending_total: string; other_pending_total: string; current_application_amount: string | null;
    total: string | null; local_initial_principal: string; issues: string[] }[];
}
export interface BorrowerGroup {
  id: string; code: string; name: string; reason: string; clients: string[]; clients_detail: { id: string; name: string }[]; is_active: boolean;
}
