import { useMutation } from "@tanstack/react-query";
import { ClipboardCheck, Search, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { isFinflowAdmin } from "@/auth/routePerms";
import {
  Badge,
  EmptyState,
  PageHeader,
  Spinner,
  formatMoney,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

type ProbeRow = Record<string, unknown> & {
  echeance?: number | string;
  date?: string;
  montant_capital?: string;
  montant_interet?: string;
  montant_total?: string;
  statut?: string;
  numero_demande?: string;
  numero_pret?: string;
  compte_pret?: string;
  nom_adherent?: string;
  date_demande?: string;
  date_effet?: string;
  date_solde?: string | null;
  montant_pret?: string;
  encours?: string;
  impaye?: string;
  impaye_interet?: string;
  penalite?: string;
  jours_retard?: number;
  observations?: string;
  raw?: Record<string, unknown>;
};

type ProbeResult = {
  request?: { refDemande?: string; codeAdherent?: string };
  kind?: "schedule" | "loans" | "empty" | "unknown";
  kind_label?: string;
  message?: string;
  response_code?: number | string;
  num_demande?: string;
  ref_demande?: string;
  num_contrat?: string;
  montant?: string;
  currency?: string;
  settled?: boolean;
  outstanding?: string;
  days_overdue?: number;
  overdue_amount?: string;
  rows_count?: number;
  rows?: ProbeRow[];
  log_id?: string;
  raw?: Record<string, unknown>;
};

const LOAN_FIELD_LABELS: Record<string, string> = {
  numeroDemande: "N° demande",
  numeroPret: "N° prêt",
  comptePret: "Compte prêt",
  nomAdherent: "Adhérent",
  dateDemande: "Date demande",
  dateEffet: "Date d'effet",
  dateSolde: "Date de solde",
  datePerte: "Date de perte",
  montantPret: "Montant du prêt",
  encours: "Encours",
  impaye: "Impayé",
  impayeInteret: "Impayé intérêts",
  penalite: "Pénalité",
  totalDU: "Total dû",
  nbreJrsRetard: "Jours de retard",
  observations: "Observations",
  libelleRetard: "Libellé retard",
};

const MONEY_RAW_KEYS = new Set([
  "montantPret",
  "encours",
  "impaye",
  "impayeInteret",
  "penalite",
  "totalDU",
]);

function money(value: string | number | null | undefined, currency: string) {
  if (value == null || value === "") return "—";
  return formatMoney(value, currency || "XOF");
}

function displayRawValue(
  key: string,
  value: unknown,
  currency: string,
): string {
  if (value == null || value === "") return "—";
  if (MONEY_RAW_KEYS.has(key)) return money(value as string | number, currency);
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ScheduleTable({
  rows,
  currency,
}: {
  rows: ProbeRow[];
  currency: string;
}) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Date</th>
            <th>Capital</th>
            <th>Intérêt</th>
            <th>Total</th>
            <th>Statut</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              <td>{row.echeance ?? idx + 1}</td>
              <td>{row.date || "—"}</td>
              <td>{money(row.montant_capital, currency)}</td>
              <td>{money(row.montant_interet, currency)}</td>
              <td>{money(row.montant_total, currency)}</td>
              <td>{row.statut || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function fetchProbe(refDemande: string, codeAdherent: string) {
  return (
    await api.post<ProbeResult>("/cbs-connectors/probe-situation/", {
      refDemande,
      codeAdherent,
    })
  ).data;
}

function CreditDetailModal({
  loan,
  codeAdherent,
  parentRefDemande,
  currency,
  onClose,
}: {
  loan: ProbeRow;
  codeAdherent: string;
  parentRefDemande: string;
  currency: string;
  onClose: () => void;
}) {
  const raw = (
    loan.raw && typeof loan.raw === "object" ? loan.raw : {}
  ) as Record<string, unknown>;

  const [loading, setLoading] = useState(true);
  const [scheduleResult, setScheduleResult] = useState<ProbeResult | null>(
    null,
  );
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  async function loadSchedule() {
    const refs = [
      String(loan.numero_demande || raw.numeroDemande || "").trim(),
      String(loan.numero_pret || raw.numeroPret || "").trim(),
      parentRefDemande.trim(),
    ].filter((v, i, arr) => v && arr.indexOf(v) === i);

    if (!refs.length) {
      setLoading(false);
      setScheduleError(
        "Aucune référence disponible pour charger l'échéancier.",
      );
      return;
    }

    setLoading(true);
    setScheduleError(null);
    setScheduleResult(null);

    let lastError: unknown = null;
    let lastResult: ProbeResult | null = null;

    for (const ref of refs) {
      try {
        const data = await fetchProbe(ref, codeAdherent);
        lastResult = data;
        if (data.kind === "schedule") {
          setScheduleResult(data);
          setLoading(false);
          return;
        }
      } catch (err) {
        lastError = err;
      }
    }

    if (lastResult) {
      setScheduleResult(lastResult);
      setScheduleError(null);
    } else if (lastError) {
      setScheduleError(
        apiErrorMessage(
          lastError,
          "Impossible de charger l'échéancier CBS.",
        ),
      );
    }
    setLoading(false);
  }

  useEffect(() => {
    void loadSchedule();
    // Une fois à l'ouverture du modal pour ce prêt
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loan.numero_pret, loan.numero_demande]);

  const detailEntries = Object.entries(LOAN_FIELD_LABELS)
    .map(([key, label]) => ({
      key,
      label,
      value: displayRawValue(key, raw[key], currency),
    }))
    .filter((e) => raw[e.key] !== undefined);

  const extraEntries = Object.entries(raw)
    .filter(([key]) => !(key in LOAN_FIELD_LABELS))
    .map(([key, value]) => ({
      key,
      label: key,
      value: displayRawValue(key, value, currency),
    }));

  const scheduleRows =
    scheduleResult?.kind === "schedule" ? scheduleResult.rows || [] : [];

  return (
    <div
      className="modal-backdrop modal-backdrop--top"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="modal-card modal-card--xl cbs-situation-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cbs-loan-detail-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="cbs-situation-modal__header">
          <div>
            <h3 id="cbs-loan-detail-title">Détail du crédit</h3>
            <p className="muted small" style={{ margin: "4px 0 0" }}>
              <code>
                {String(loan.numero_pret || raw.numeroPret || "—")}
              </code>
              {loan.numero_demande || raw.numeroDemande
                ? ` · demande ${String(loan.numero_demande || raw.numeroDemande)}`
                : ""}
            </p>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            aria-label="Fermer"
          >
            <X size={16} />
          </button>
        </header>

        <div className="cbs-situation-modal__body">
          <h4 style={{ margin: "0 0 10px", fontSize: "0.95rem" }}>
            Informations crédit
          </h4>
          <dl className="def-list two" style={{ marginBottom: 20 }}>
            {[...detailEntries, ...extraEntries].map((entry) => (
              <div key={entry.key}>
                <dt>{entry.label}</dt>
                <dd>
                  {String(entry.key).toLowerCase().includes("numero") ||
                  String(entry.key).toLowerCase().includes("compte") ? (
                    <code className="small">{entry.value}</code>
                  ) : (
                    entry.value
                  )}
                </dd>
              </div>
            ))}
          </dl>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              marginBottom: 10,
            }}
          >
            <h4 style={{ margin: 0, fontSize: "0.95rem" }}>Échéancier</h4>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={loading}
              onClick={() => void loadSchedule()}
            >
              {loading ? "Chargement…" : "Actualiser"}
            </button>
          </div>

          {loading && (
            <div className="cbs-situation-modal__loading">
              <Spinner />
              <p className="muted">Chargement de l&apos;échéancier CBS…</p>
            </div>
          )}

          {!loading && scheduleError && (
            <div className="notice-error" role="alert" style={{ marginBottom: 12 }}>
              {scheduleError}
            </div>
          )}

          {!loading && scheduleRows.length > 0 && (
            <ScheduleTable rows={scheduleRows} currency={currency} />
          )}

          {!loading && !scheduleError && scheduleRows.length === 0 && (
            <p className="muted">
              Le CBS n&apos;a pas renvoyé d&apos;échéancier (format{" "}
              <code>echeance</code> / <code>statut</code>) pour ce crédit.
              {scheduleResult?.kind_label
                ? ` Réponse : ${scheduleResult.kind_label}`
                : ""}
              {scheduleResult?.rows_count != null
                ? ` (${scheduleResult.rows_count} ligne(s)).`
                : "."}
            </p>
          )}
        </div>

        <footer className="cbs-situation-modal__footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Fermer
          </button>
        </footer>
      </div>
    </div>
  );
}

export function AdminCbsSituationProbePage() {
  const { activeTenant, user } = useAuth();
  const canManage = isFinflowAdmin(user);
  const needsTenant = Boolean(user?.is_group_level) && !activeTenant;

  const [refDemande, setRefDemande] = useState("");
  const [codeAdherent, setCodeAdherent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [selectedLoan, setSelectedLoan] = useState<ProbeRow | null>(null);

  const probe = useMutation({
    mutationFn: async () =>
      (
        await api.post<ProbeResult>("/cbs-connectors/probe-situation/", {
          refDemande: refDemande.trim(),
          codeAdherent: codeAdherent.trim(),
        })
      ).data,
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setShowRaw(false);
      setSelectedLoan(null);
    },
    onError: (err) => {
      setResult(null);
      setSelectedLoan(null);
      setError(
        apiErrorMessage(
          err,
          "Impossible d'interroger la situation crédit CBS.",
        ),
      );
    },
  });

  if (!canManage) {
    return (
      <EmptyState message="Écran réservé aux administrateurs filiale et groupe." />
    );
  }
  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={ClipboardCheck}
          title="Vérification de situation"
          subtitle="Sélectionnez une filiale"
        />
        <p className="muted">
          Choisissez une filiale dans la barre supérieure pour utiliser le
          connecteur CBS actif.
        </p>
      </div>
    );
  }

  const currency = result?.currency || "XOF";

  return (
    <div className="page-shell">
      <PageHeader
        icon={ClipboardCheck}
        title="Vérification de situation"
        subtitle="Appel Perfect crd/situation — refDemande + code adhérent"
      />

      <form
        className="card"
        style={{ padding: 20, marginBottom: 20 }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setError(null);
          probe.mutate();
        }}
      >
        <div className="form-grid two-col">
          <label className="field">
            <span>refDemande</span>
            <input
              value={refDemande}
              onChange={(e) => setRefDemande(e.target.value)}
              placeholder="Ex. CR-2026-00002"
              required
              autoComplete="off"
            />
          </label>
          <label className="field">
            <span>codeAdherent</span>
            <input
              value={codeAdherent}
              onChange={(e) => setCodeAdherent(e.target.value)}
              placeholder="Ex. AG0100027"
              required
              autoComplete="off"
            />
          </label>
        </div>
        <div className="form-actions" style={{ marginTop: 12 }}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={
              probe.isPending || !refDemande.trim() || !codeAdherent.trim()
            }
          >
            <Search size={16} />
            {probe.isPending ? "Interrogation…" : "Consulter"}
          </button>
        </div>
      </form>

      {error && (
        <div className="notice-error" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {probe.isPending && !result && (
        <div className="card" style={{ padding: 32, textAlign: "center" }}>
          <Spinner />
          <p className="muted" style={{ marginTop: 8 }}>
            Appel CBS en cours…
          </p>
        </div>
      )}

      {result && (
        <div className="card" style={{ padding: 20 }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              alignItems: "center",
              marginBottom: 16,
            }}
          >
            <Badge
              value={result.settled ? "SETTLED" : "OPEN"}
              label={result.settled ? "Soldé" : "Non soldé"}
              tone={result.settled ? "success" : "warning"}
            />
            <Badge
              value={result.kind || "unknown"}
              label={result.kind_label || result.kind || "—"}
              tone="info"
            />
            {result.response_code != null && (
              <Badge
                value={String(result.response_code)}
                label={`Code ${String(result.response_code)}`}
                tone="muted"
              />
            )}
            {result.message && (
              <span className="muted small">{result.message}</span>
            )}
          </div>

          <dl className="def-list two" style={{ marginBottom: 20 }}>
            <div>
              <dt>N° demande</dt>
              <dd>
                <code>{result.num_demande || "—"}</code>
              </dd>
            </div>
            <div>
              <dt>Réf. demande</dt>
              <dd>
                <code>{result.ref_demande || "—"}</code>
              </dd>
            </div>
            <div>
              <dt>N° contrat</dt>
              <dd>
                <code>{result.num_contrat || "—"}</code>
              </dd>
            </div>
            <div>
              <dt>Montant</dt>
              <dd>{money(result.montant, currency)}</dd>
            </div>
            <div>
              <dt>Encours calculé</dt>
              <dd>{money(result.outstanding, currency)}</dd>
            </div>
            <div>
              <dt>Impayé / retard</dt>
              <dd>
                {money(result.overdue_amount, currency)}
                {result.days_overdue != null
                  ? ` · ${result.days_overdue} j`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Devise</dt>
              <dd>{result.currency || "—"}</dd>
            </div>
            <div>
              <dt>Lignes</dt>
              <dd>{result.rows_count ?? 0}</dd>
            </div>
          </dl>

          {result.kind === "schedule" && (
            <>
              <h3 style={{ margin: "0 0 10px", fontSize: "1rem" }}>
                Échéancier
              </h3>
              <ScheduleTable rows={result.rows || []} currency={currency} />
            </>
          )}

          {result.kind === "loans" && (
            <>
              <h3 style={{ margin: "0 0 6px", fontSize: "1rem" }}>
                Prêts renvoyés par Vision
              </h3>
              <p className="muted small" style={{ marginBottom: 10 }}>
                Cliquez sur une ligne pour afficher le détail et tenter de
                charger l&apos;échéancier.
              </p>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>N° demande</th>
                      <th>N° prêt</th>
                      <th>Compte</th>
                      <th>Adhérent</th>
                      <th>Montant</th>
                      <th>Encours</th>
                      <th>Impayé</th>
                      <th>Retard</th>
                      <th>Observation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.rows || []).map((row, idx) => (
                      <tr
                        key={idx}
                        tabIndex={0}
                        role="button"
                        onClick={() => setSelectedLoan(row)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setSelectedLoan(row);
                          }
                        }}
                        style={{ cursor: "pointer" }}
                        title="Voir le détail du crédit"
                      >
                        <td>
                          <code className="small">
                            {row.numero_demande || "—"}
                          </code>
                        </td>
                        <td>
                          <code className="small">
                            {row.numero_pret || "—"}
                          </code>
                        </td>
                        <td className="small">{row.compte_pret || "—"}</td>
                        <td>{row.nom_adherent || "—"}</td>
                        <td>{money(row.montant_pret, currency)}</td>
                        <td>{money(row.encours, currency)}</td>
                        <td>{money(row.impaye, currency)}</td>
                        <td>
                          {row.jours_retard != null
                            ? `${row.jours_retard} j`
                            : "—"}
                        </td>
                        <td>{row.observations || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {(result.kind === "empty" || result.kind === "unknown") && (
            <p className="muted">
              {result.kind === "empty"
                ? "Aucune ligne dans datas."
                : "Format datas non reconnu — consultez le JSON brut."}
            </p>
          )}

          <div style={{ marginTop: 16 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowRaw((v) => !v)}
            >
              {showRaw ? "Masquer le JSON brut" : "Afficher le JSON brut"}
            </button>
            {showRaw && (
              <pre
                style={{
                  marginTop: 10,
                  maxHeight: 420,
                  overflow: "auto",
                  fontSize: 12,
                  background: "var(--surface-2, #f6f7f8)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                {JSON.stringify(result.raw ?? result, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {selectedLoan && (
        <CreditDetailModal
          loan={selectedLoan}
          codeAdherent={codeAdherent.trim()}
          parentRefDemande={refDemande.trim()}
          currency={currency}
          onClose={() => setSelectedLoan(null)}
        />
      )}
    </div>
  );
}
