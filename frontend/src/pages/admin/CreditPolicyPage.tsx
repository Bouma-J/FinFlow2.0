import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditInstructionPolicy, Paginated, Tenant } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

const EXTRA_DEFAULTS = {
  require_credit_contracts: true, require_credit_signed_contracts: false,
  require_surety_contracts: true, require_setup_request: false,
  require_setup_four_eyes: false, require_final_review: true,
  setup_execution_role: "OPERATIONS" as const, require_setup_authorizer_separation: false,
  recheck_kyc_on_setup: true, require_verified_documents: false,
  risk_mode: "RECOMMENDATION" as const, approval_validity_days: 0, max_analysis_age_days: 0,
};

const EXTRA_FLAGS = [
  ["require_credit_contracts", "Exiger un contrat de crédit avant mise en place"],
  ["require_credit_signed_contracts", "Exiger un contrat de crédit signé"],
  ["require_surety_contracts", "Exiger les contrats de cautionnement"],
  ["require_setup_request", "Exiger une demande formelle de mise en place"],
  ["require_setup_four_eyes", "Exiger une validation à quatre yeux de la mise en place"],
  ["require_final_review", "Exiger le contrôle final avant transmission au CBS"],
  ["require_setup_authorizer_separation", "Séparer l'auteur et l'autorisateur de la mise en place"],
  ["recheck_kyc_on_setup", "Revérifier le KYC avant mise en place"],
  ["require_verified_documents", "Exiger la vérification des documents"],
] as const satisfies readonly (readonly [keyof CreditInstructionPolicy, string])[];

const EMPTY: CreditInstructionPolicy = {
  ...EXTRA_DEFAULTS,
  id: "",
  collateral_coverage_mode: "ALERT",
  require_field_visit: false,
  allow_unfavorable_analysis_submit: true,
  require_product_checklist: false,
  match_product_client_type: false,
  kyc_gate: "ON_SUBMIT",
  product_bounds_gate: "ON_SUBMIT",
  amount_approved_mode: "ALLOW",
  show_readiness_checklist: true,
  enable_cancel_status: false,
  allow_collateral_during_approval: false,
  require_surety_signed_contracts: true,
  require_formalization_before_disbursement: false,
};

export function AdminCreditPolicyPage() {
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const [form, setForm] = useState<CreditInstructionPolicy>(EMPTY);

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () =>
      (await api.get<Paginated<Tenant>>("/tenants/")).data,
    enabled: !!user?.is_group_level,
  });

  const policy = useQuery({
    queryKey: ["credit-instruction-policy", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<CreditInstructionPolicy>(
          "/credit-instruction-policy/current/",
        )
      ).data,
    enabled: !needsTenant,
  });

  useEffect(() => {
    if (policy.data) setForm({ ...EMPTY, ...policy.data });
  }, [policy.data]);

  const scopeLabel = user?.is_group_level
    ? tenants.data?.results.find((t) => t.id === activeTenant)?.name ??
      "filiale sélectionnée"
    : user?.tenant_branding?.name ?? "votre filiale";

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={SlidersHorizontal}
          title="Politique crédit"
          subtitle="Sélectionnez une filiale"
        />
        <p className="muted">
          Choisissez une filiale dans la barre supérieure pour paramétrer sa
          politique d&apos;instruction.
        </p>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={SlidersHorizontal}
        title="Politique d'instruction crédit"
        subtitle={`Règles de soumission et de validation — ${scopeLabel}`}
      />

      {policy.isLoading ? (
        <Spinner />
      ) : policy.isError ? (
        <ErrorState
          message="Impossible de charger la politique crédit."
          onRetry={() => policy.refetch()}
        />
      ) : !policy.data ? (
        <Spinner />
      ) : (
        <><p className="muted">Consultation seule. Les changements de politique sont préparés et validés par deux utilisateurs distincts dans le <Link to="/admin/configuration">Centre de configuration</Link>. Les valeurs ci-dessous correspondent au socle applicable sans ciblage produit ou clientèle.</p><fieldset disabled style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}><div className="tenant-compose-form" aria-disabled="true">
          <div className="tenant-compose-head">
            <h2>
              <ClipboardCheck size={18} style={{ verticalAlign: "-3px" }} />{" "}
              Garde-fous paramétrables
            </h2>
            <p className="muted">
              Adaptez la rigueur du processus sans modifier le code. Les
              valeurs par défaut conservent le comportement historique
              (souple).
            </p>
          </div>

          <section className="tenant-form-block">
            <header className="tenant-form-block-head">
              <div>
                <h3 className="tenant-form-block-title">Soumission</h3>
                <p className="tenant-form-block-desc">
                  Contrôles appliqués avant l&apos;entrée en circuit.
                </p>
              </div>
            </header>
            <div className="tenant-form-block-body form-grid two-col">
              <label className="field">
                <span>Couverture des garanties</span>
                <select
                  value={form.collateral_coverage_mode}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      collateral_coverage_mode: e.target
                        .value as CreditInstructionPolicy["collateral_coverage_mode"],
                    })
                  }
                >
                  <option value="ALERT">Alerte uniquement</option>
                  <option value="BLOCK_SUBMIT">Bloquer la soumission</option>
                  <option value="BLOCK_APPROVE">
                    Bloquer l&apos;approbation finale
                  </option>
                </select>
              </label>
              <label className="field">
                <span>Exigence KYC</span>
                <select
                  value={form.kyc_gate}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      kyc_gate: e.target
                        .value as CreditInstructionPolicy["kyc_gate"],
                    })
                  }
                >
                  <option value="ON_SUBMIT">À la soumission</option>
                  <option value="ON_CREATE">Dès la création du dossier</option>
                </select>
              </label>
              <label className="field">
                <span>Bornes produit (montant / durée)</span>
                <select
                  value={form.product_bounds_gate}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      product_bounds_gate: e.target
                        .value as CreditInstructionPolicy["product_bounds_gate"],
                    })
                  }
                >
                  <option value="ON_SUBMIT">À la soumission</option>
                  <option value="ON_SAVE">À chaque enregistrement</option>
                </select>
              </label>
              <label className="field">
                <span>Montant approuvé</span>
                <select
                  value={form.amount_approved_mode}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      amount_approved_mode: e.target
                        .value as CreditInstructionPolicy["amount_approved_mode"],
                    })
                  }
                >
                  <option value="ALLOW">Saisissable dès l&apos;instruction</option>
                  <option value="FORBID">
                    Uniquement à la décision du circuit
                  </option>
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_field_visit}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_field_visit: e.target.checked,
                    })
                  }
                />
                <span>Visite terrain obligatoire avant soumission</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.allow_unfavorable_analysis_submit}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      allow_unfavorable_analysis_submit: e.target.checked,
                    })
                  }
                />
                <span>Autoriser la soumission si analyse défavorable</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_product_checklist}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_product_checklist: e.target.checked,
                    })
                  }
                />
                <span>Exiger les pièces obligatoires du produit</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.match_product_client_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      match_product_client_type: e.target.checked,
                    })
                  }
                />
                <span>Contrôler cohérence type client / produit</span>
              </label>
            </div>
          </section>

          <section className="tenant-form-block">
            <header className="tenant-form-block-head">
              <div>
                <h3 className="tenant-form-block-title">Circuit &amp; UI</h3>
                <p className="tenant-form-block-desc">
                  Comportement pendant et après la validation.
                </p>
              </div>
            </header>
            <div className="tenant-form-block-body form-grid two-col">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.show_readiness_checklist}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      show_readiness_checklist: e.target.checked,
                    })
                  }
                />
                <span>Afficher la checklist de readiness sur le dossier</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.allow_collateral_during_approval}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      allow_collateral_during_approval: e.target.checked,
                    })
                  }
                />
                <span>
                  Autoriser garanties / cautions pendant le circuit
                </span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.enable_cancel_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      enable_cancel_status: e.target.checked,
                    })
                  }
                />
                <span>Autoriser l&apos;annulation formelle (CANCELLED)</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_surety_signed_contracts}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_surety_signed_contracts: e.target.checked,
                    })
                  }
                />
                <span>
                  Exiger un contrat de cautionnement signé avant mise en place
                </span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_formalization_before_disbursement}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_formalization_before_disbursement:
                        e.target.checked,
                    })
                  }
                />
                <span>
                  Exiger la formalisation des garanties (hypothèque / gage /
                  nantissement) avant mise en place
                </span>
              </label>
            </div>
          </section>

          <section className="card"><div className="card-body stack">
            <h3>Décision et mise en place CBS</h3>
            <p className="muted small">Après l'approbation du crédit, l'administration crédit effectue le contrôle final et autorise la mise en place. Cette autorisation préalable est obligatoire.</p>
            <label className="field"><span>Responsable de la transmission au CBS</span><select value={form.setup_execution_role} onChange={(event) => setForm({ ...form, setup_execution_role: event.target.value as CreditInstructionPolicy["setup_execution_role"] })}><option value="OPERATIONS">Opérations</option><option value="CREDIT_ADMIN">Administrateur crédit</option></select></label>
            {EXTRA_FLAGS.map(([key, label]) => <label className="checkbox" key={key}>
              <input type="checkbox" checked={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.checked })} /><span>{label}</span>
            </label>)}
            <label className="field"><span>Détermination du risque</span><select value={form.risk_mode} onChange={(event) => setForm({ ...form, risk_mode: event.target.value as CreditInstructionPolicy["risk_mode"] })}>
              <option value="RECOMMENDATION">Avis de l'analyste</option><option value="SCORE">Score financier</option><option value="CONSERVATIVE">Le plus prudent du score et de l'avis</option>
            </select></label>
            <div className="form-grid two-col">
              <label className="field"><span>Validité de l'accord en jours (0 : sans limite)</span><input type="number" min="0" value={form.approval_validity_days} onChange={(event) => setForm({ ...form, approval_validity_days: Number(event.target.value) })} /></label>
              <label className="field"><span>Ancienneté maximale de l'analyse en jours (0 : sans limite)</span><input type="number" min="0" value={form.max_analysis_age_days} onChange={(event) => setForm({ ...form, max_analysis_age_days: Number(event.target.value) })} /></label>
            </div>
            <p className="muted small">Un retour positif du CBS confirme la mise en place du dossier. Le versement effectif des fonds est réalisé dans le CBS.</p>
          </div></section>
        </div></fieldset></>
      )}
    </div>
  );
}
