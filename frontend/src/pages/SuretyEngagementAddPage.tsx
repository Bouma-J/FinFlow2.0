import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, HandCoins, Plus, Search, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditApplication, Surety } from "@/api/types";
import { SuretyAutocomplete } from "@/components/SuretyAutocomplete";
import { SuretyForm } from "@/components/SuretyForm";
import { Card, ErrorState, PageHeader, Spinner, formatMoney } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

export function SuretyEngagementAddPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [surety, setSurety] = useState("");
  const [suretyLabel, setSuretyLabel] = useState("");
  const [selectedSurety, setSelectedSurety] = useState<Surety | null>(null);
  const [creating, setCreating] = useState(false);
  const [amount, setAmount] = useState("");
  const [engagementType, setEngagementType] = useState<"SIMPLE" | "SOLIDAIRE">(
    "SOLIDAIRE",
  );
  const [signedDate, setSignedDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: app, isLoading, isError, refetch } = useQuery({
    queryKey: ["credit-application", id],
    queryFn: async () =>
      (await api.get<CreditApplication>(`/credit-applications/${id}/`)).data,
    enabled: !!id,
  });

  const mutation = useMutation({
    mutationFn: async () =>
      (
        await api.post("/surety-engagements/", {
          surety,
          application: id,
          amount,
          engagement_type: engagementType,
          signed_date: signedDate || null,
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["surety-engagements", id] });
      qc.invalidateQueries({ queryKey: ["sureties"] });
      navigate(`/dossiers/${id}`);
    },
    onError: (e: unknown) => {
      setError(
        apiErrorMessage(e, "Enregistrement impossible. Vérifiez les champs."),
      );
    },
  });

  if (isLoading) return <Spinner />;
  if (isError || !app)
    return (
      <ErrorState
        message="Impossible de charger le dossier de crédit."
        onRetry={() => refetch()}
      />
    );

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!surety) {
      setError("Veuillez sélectionner ou créer une caution.");
      return;
    }
    if (!amount) {
      setError("Veuillez renseigner le montant engagé.");
      return;
    }
    mutation.mutate();
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={HandCoins}
        title="Ajouter une caution"
        subtitle={`Dossier ${app.reference} — ${app.client_display}`}
        actions={
          <Link className="btn btn-ghost" to={`/dossiers/${id}`}>
            <ArrowLeft />
            Retour au dossier
          </Link>
        }
      />

      {creating ? (
        <>
          <div className="notice-info">
            <Plus size={16} />
            <span>
              Renseignez la nouvelle caution. Elle sera automatiquement
              sélectionnée pour l&apos;engagement.
            </span>
          </div>
          <SuretyForm
            onSuccess={(s) => {
              setSurety(s.id);
              setSuretyLabel(s.display_name);
              setSelectedSurety(s);
              setCreating(false);
            }}
            onCancel={() => setCreating(false)}
          />
        </>
      ) : (
        <form className="stack" onSubmit={submit}>
          <Card
            title={
              <>
                <HandCoins size={17} /> Caution
              </>
            }
          >
            {surety ? (
              <div className="picked-row">
                <span className="picked-chip">
                  <Check size={15} />
                  {suretyLabel || "Caution sélectionnée"}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setSurety("");
                    setSuretyLabel("");
                    setSelectedSurety(null);
                  }}
                >
                  <X size={14} />
                  Changer
                </button>
              </div>
            ) : (
              <>
                <label className="field">
                  <span>
                    <Search
                      size={13}
                      style={{ verticalAlign: "-2px", marginRight: 4 }}
                    />
                    Caution existante
                  </span>
                  <SuretyAutocomplete
                    value={surety}
                    onChange={(sid, label, s) => {
                      setSurety(sid);
                      setSuretyLabel(label);
                      setSelectedSurety(s ?? null);
                    }}
                  />
                </label>
                <div className="or-divider">
                  <span>ou</span>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setCreating(true)}
                >
                  <Plus size={15} />
                  Créer une nouvelle caution
                </button>
              </>
            )}
            {selectedSurety && (
              <dl className="def-list two" style={{ marginTop: 14 }}>
                <div>
                  <dt>Plafond</dt>
                  <dd>{formatMoney(selectedSurety.commitment_ceiling)}</dd>
                </div>
                <div>
                  <dt>Déjà engagé</dt>
                  <dd>{formatMoney(selectedSurety.total_committed)}</dd>
                </div>
                <div>
                  <dt>Disponible</dt>
                  <dd>{formatMoney(selectedSurety.available_ceiling)}</dd>
                </div>
              </dl>
            )}
          </Card>

          {surety && (
            <Card
              title={
                <>
                  <HandCoins size={17} /> Engagement
                </>
              }
            >
              <div className="form-grid two-col">
                <label className="field">
                  <span>
                    Montant engagé (XOF) <em className="req"> *</em>
                  </span>
                  <input
                    type="number"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Type d&apos;engagement</span>
                  <select
                    value={engagementType}
                    onChange={(e) =>
                      setEngagementType(
                        e.target.value as "SIMPLE" | "SOLIDAIRE",
                      )
                    }
                  >
                    <option value="SOLIDAIRE">Caution solidaire</option>
                    <option value="SIMPLE">Caution simple</option>
                  </select>
                </label>
                <label className="field">
                  <span>Date de signature</span>
                  <input
                    type="date"
                    value={signedDate}
                    onChange={(e) => setSignedDate(e.target.value)}
                  />
                </label>
              </div>
              <p className="muted small" style={{ marginTop: 10 }}>
                La caution solidaire peut être poursuivie pour la totalité ;
                la caution simple est poursuivie après le débiteur principal.
                Le contrat de cautionnement pourra être généré depuis la fiche
                caution ou le dossier.
              </p>
            </Card>
          )}

          {error && <div className="form-error">{error}</div>}
          <div className="page-actions">
            <Link className="btn btn-ghost" to={`/dossiers/${id}`}>
              Annuler
            </Link>
            <button
              className="btn btn-primary"
              disabled={mutation.isPending || !surety}
            >
              {mutation.isPending ? "Enregistrement…" : "Rattacher la caution"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
