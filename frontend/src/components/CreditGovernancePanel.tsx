import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import type { CreditSetupState } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { apiErrorMessage } from "@/utils/apiError";

const CHECKS = {
  kyc: "KYC et identité à jour",
  contribution: "Apport propre vérifié ou sans objet",
  collateral: "Garanties et formalités vérifiées ou sans objet",
  terms: "Conditions conformes à l'accord et contrats contrôlés",
  insurance: "Assurance valide et justificatifs contrôlés ou sans objet",
};
type Action = "setup-review" | "authorize-setup" | "revoke-setup-authorization" | "request-setup-complements" | "reexamine";

export function CreditGovernancePanel({ applicationId, status }: { applicationId: string; status: string }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [insurancePolicy, setInsurancePolicy] = useState("");
  const [insuranceExpiry, setInsuranceExpiry] = useState("");
  const isCreditAdmin = !!user?.is_superuser || !!user?.capabilities?.includes("credit_admin");
  const canReview = isCreditAdmin && hasPerm(user, "credits.review_setup_creditapplication");
  const canAuthorize = isCreditAdmin && hasPerm(user, "credits.authorize_setup_creditapplication");
  const canReturn = hasPerm(user, "credits.change_creditapplication");
  const eligible = ["APPROVED", "CONTRACT_GENERATED", "DISBURSEMENT_PENDING"].includes(status);
  const review = useQuery({
    queryKey: ["setup-review", applicationId], enabled: eligible,
    queryFn: async () => (await api.get<CreditSetupState>(`/credit-applications/${applicationId}/setup-review/`)).data,
  });
  const action = useMutation({
    mutationFn: async (kind: Action) => {
      if (!comment.trim()) throw new Error("Précisez les vérifications, le motif de l'autorisation ou de son retrait.");
      return api.post(`/credit-applications/${applicationId}/${kind}/`, {
        comment, reason: comment, checks,
        insurance_policy_number: insurancePolicy || undefined,
        insurance_expiry_date: insuranceExpiry || undefined,
      });
    },
    onSuccess: () => {
      setError("");
      for (const key of ["credit-application", "credit-applications", "credit-readiness", "setup-review", "credit-timeline"])
        qc.invalidateQueries({ queryKey: [key] });
    },
    onError: (cause) => setError(apiErrorMessage(cause, cause instanceof Error ? cause.message : "Opération impossible.")),
  });
  if (!eligible) return null;
  const data = review.data;
  return <section className="card"><div className="card-body stack">
    <h3>Contrôle et autorisation de mise en place</h3>
    <p className="muted small">L'administration crédit contrôle le dossier approuvé, puis autorise sa mise en place. La transmission au CBS est effectuée par le service choisi dans la configuration.</p>
    {review.isLoading && <p className="muted">Chargement du contrôle final…</p>}
    {review.isError && <p className="form-error">Impossible de charger le contrôle. <button type="button" className="btn btn-ghost" onClick={() => review.refetch()}>Réessayer</button></p>}
    {data && <p><strong>Transmission au CBS :</strong> {data.execution_role_display}</p>}
    {data?.approval?.captured_at && <details>
      <summary>Éléments figés à l'accord — {data.approval.captured_at}</summary>
      <dl className="def-list two">{Object.entries({ amount_approved: "Montant accordé", currency: "Devise", duration_months: "Durée en mois", interest_rate: "Taux", periodicity: "Périodicité", decision_date: "Date de décision" }).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{String(data.approval.application?.[key] ?? "—")}</dd></div>)}</dl>
      <p className="subsection-label">Pièces examinées</p>{data.approval.documents?.map((document) => <p key={document.id}>{document.name} — version {document.version} — {document.verification_status}</p>)}
      <p className="subsection-label">Contrats au moment de l'accord</p>{data.approval.contracts?.map((contract) => <p key={contract.id}>{contract.template_name} — {contract.status}</p>)}
    </details>}
    {data?.failures.map((failure) => <p className="form-error" key={failure}>{failure}</p>)}
    {data?.review.reviewed_at && <p>Contrôle par {data.review.reviewed_by_display || "l'administration crédit"} le {new Date(data.review.reviewed_at).toLocaleString("fr-FR")} — {data.review_current ? "à jour" : "à renouveler"}. {data.review.comment}</p>}
    {data?.review.status === "TO_COMPLETE" && <p className="form-error">Compléments demandés par {data.review.complement_request?.requested_by_display} : {data.review.complement_request?.comment}</p>}
    {data?.authorization_valid ? <p><strong>Mise en place autorisée</strong> par {data.authorization.authorized_by_display} le {data.authorization.authorized_at && new Date(data.authorization.authorized_at).toLocaleString("fr-FR")}. {data.authorization.comment}</p> : data?.authorization_failures.map((failure) => <p className="muted" key={failure}>{failure}</p>)}
    {data?.authorization.status === "REVOKED" && <p className="muted">Autorisation retirée : {data.authorization.revocation_reason}</p>}
    {canReview && <>
      {Object.entries(CHECKS).map(([key, label]) => <label className="checkbox" key={key}><input type="checkbox" checked={checks[key] || false} onChange={(event) => setChecks({ ...checks, [key]: event.target.checked })} /><span>{label}</span></label>)}
      <div className="form-grid two-col"><label className="field"><span>Police d'assurance (compléter si applicable)</span><input value={insurancePolicy} onChange={(event) => setInsurancePolicy(event.target.value)} /></label><label className="field"><span>Fin de couverture (compléter si applicable)</span><input type="date" value={insuranceExpiry} onChange={(event) => setInsuranceExpiry(event.target.value)} /></label></div>
    </>}
    {(canReview || canAuthorize || canReturn) && <>
      <label className="field"><span>Vérifications, références des preuves ou motif de la décision</span><textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} /></label>
      <div className="doc-row">
        {canReview && <button type="button" className="btn btn-primary" disabled={action.isPending || !data} onClick={() => action.mutate("setup-review")}>Valider le contrôle final</button>}
        {canReview && <button type="button" className="btn btn-ghost" disabled={action.isPending} onClick={() => action.mutate("request-setup-complements")}>Demander des compléments</button>}
        {canAuthorize && <button type="button" className="btn btn-primary" disabled={action.isPending || !data?.review_current || !!data?.failures.length} onClick={() => action.mutate("authorize-setup")}>Autoriser la mise en place</button>}
        {canAuthorize && data?.authorization.status === "AUTHORIZED" && <button type="button" className="btn btn-ghost" disabled={action.isPending} onClick={() => action.mutate("revoke-setup-authorization")}>Retirer l'autorisation</button>}
        {canReturn && status !== "DISBURSEMENT_PENDING" && <button type="button" className="btn btn-ghost" disabled={action.isPending} onClick={() => { if (window.confirm("Renvoyer l'accord pour un nouveau circuit et annuler ses contrats actifs ?")) action.mutate("reexamine"); }}>Réexaminer l'accord</button>}
      </div>
    </>}
    <p className="muted small">Le dossier est mis en place après le retour positif du CBS. La mise à disposition effective des fonds est réalisée dans le CBS.</p>
    {error && <p className="form-error">{error}</p>}
  </div></section>;
}
