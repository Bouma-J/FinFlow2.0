import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Calculator,
  CalendarClock,
  FileDown,
  Info,
  PiggyBank,
  Play,
  RotateCcw,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/api/client";
import {
  CREDIT_LABELS,
  type CbsCatalogItem,
  type CreditProduct, type Agency,
  type Paginated,
  type SimulationResult,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Card, PageHeader, formatMoney as displayMoney } from "@/components/ui";
import { useTenantBranding } from "@/hooks/useTenantBranding";
import { exportSimulationPdf } from "@/utils/exportSimulationPdf";
import { PricingQuoteSummary } from "@/components/PricingQuoteSummary";
import { apiErrorMessage } from "@/utils/apiError";

function formatDueDate(value: string) {
  if (!value) return "—";
  // Dates ISO (YYYY-MM-DD) : éviter le décalage fuseau de Date.parse
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (m) {
    return `${m[3]}/${m[2]}/${m[1]}`;
  }
  return new Date(value).toLocaleDateString("fr-FR");
}

const PERIODICITY_FALLBACK = Object.keys(CREDIT_LABELS.periodicity);
/** Mécanismes proposés à la saisie (CONSTANT conservé en lecture seule historique). */
const MECHANISM_FALLBACK = ["DEGRESSIVE", "IN_FINE", "BULLET"] as const;

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const DEFAULT_FORM = {
  product: "", agency: "", client_type: "", individual_profile: "", fees_rate: "", currency: "XOF",
  amount: "1000000",
  annual_rate: "12.5",
  months: "12",
  periodicity: "MONTHLY",
  mechanism: "DEGRESSIVE",
  include_savings: false,
  savings_rate: "5",
  simulation_date: todayISO(),
  first_due_date: "",
};

type SimForm = typeof DEFAULT_FORM;

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: "ok" | "warn";
}) {
  return (
    <div className={`metric${tone ? ` metric-${tone}` : ""}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

function num(v: string | number | null | undefined) {
  if (v === null || v === undefined || v === "") return 0;
  return typeof v === "number" ? v : Number(v);
}

/** Affiche les espaces milliers pendant la saisie (ex. 1 000 000). */
function formatAmountInput(raw: string) {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return "";
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
}

function parseAmountInput(display: string) {
  return display.replace(/\D/g, "");
}

export function SimulatorPage() {
  const [form, setForm] = useState<SimForm>(DEFAULT_FORM);
  const { tenantName, branding } = useTenantBranding();
  const { activeTenant } = useAuth();
  const products = useQuery({ queryKey: ["simulator-products", activeTenant], queryFn: async () => (await api.get<Paginated<CreditProduct>>("/credit-products/", { params: { is_active: true, page_size: 200 } })).data });
  const agencies = useQuery({ queryKey: ["simulator-agencies", activeTenant], queryFn: async () => (await api.get<Paginated<Agency>>("/agencies/", { params: { page_size: 200 } })).data });

  const { data: periodicities } = useQuery({
    queryKey: ["loan-periodicities", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/loan-periodicities/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });
  const { data: repaymentMethods } = useQuery({
    queryKey: ["repayment-methods", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/repayment-methods/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });

  const periodicityOptions = useMemo(() => {
    const rows = periodicities?.results ?? [];
    if (!rows.length) {
      return PERIODICITY_FALLBACK.map((key) => ({
        value: key,
        label: CREDIT_LABELS.periodicity[key] || key,
      }));
    }
    return rows.map((r) => ({
      value: r.code,
      label: r.cbs_code ? `${r.label} (${r.cbs_code})` : r.label,
    }));
  }, [periodicities]);

  const mechanismOptions = useMemo(() => {
    const rows = repaymentMethods?.results ?? [];
    if (!rows.length) {
      return MECHANISM_FALLBACK.map((key) => ({
        value: key,
        label: CREDIT_LABELS.repayment_mechanism[key] || key,
      }));
    }
    return rows.map((r) => ({
      value: r.code,
      label: r.cbs_code ? `${r.label} → ${r.cbs_code}` : r.label,
    }));
  }, [repaymentMethods]);

  const sim = useMutation({
    mutationFn: async () => {
      const savingsRate = form.include_savings ? (form.savings_rate || null) : "0";
      const payload: Record<string, string | number | null> = {
        product: form.product || null, agency: form.agency || null, client_type: form.client_type,
        individual_profile: form.individual_profile, fees_rate: form.fees_rate || null, currency: form.currency,
        amount: form.amount,
        annual_rate: form.annual_rate || null,
        months: Number(form.months),
        periodicity: form.periodicity,
        mechanism: form.mechanism,
        savings_rate: savingsRate,
        simulation_date: form.simulation_date || todayISO(),
      };
      if (form.first_due_date) {
        payload.first_due_date = form.first_due_date;
      }
      return (
        await api.post<SimulationResult>("/credit-applications/simulate/", payload)
      ).data;
    },
  });

  useEffect(() => { setForm({ ...DEFAULT_FORM, simulation_date: todayISO() }); sim.reset(); }, [activeTenant]);

  function submit(e: FormEvent) {
    e.preventDefault();
    sim.mutate();
  }

  function reset() {
    setForm({ ...DEFAULT_FORM, simulation_date: todayISO() });
    sim.reset();
  }

  const result = sim.data;
  function formatMoney(value: Parameters<typeof displayMoney>[0], currency = result?.parameters?.currency ?? form.currency) { return displayMoney(value, currency); }
  const resultPeriodicity = result?.parameters?.periodicity ?? form.periodicity;
  const resultMechanism = result?.parameters?.mechanism ?? form.mechanism;
  const hasSavings = Boolean(result && num(result.total_savings) > 0);
  const periodLabel =
    periodicityOptions.find((o) => o.value === resultPeriodicity)?.label ||
    CREDIT_LABELS.periodicity[resultPeriodicity] || resultPeriodicity;
  const mechanismLabel =
    mechanismOptions.find((o) => o.value === resultMechanism)?.label ||
    CREDIT_LABELS.repayment_mechanism[resultMechanism] || resultMechanism;

  const installmentLabel = useMemo(() => {
    if (resultMechanism === "BULLET") return "Échéance unique (institution)";
    if (resultMechanism === "IN_FINE") return "1ʳᵉ échéance (intérêts)";
    return `Échéance institution (${periodLabel.toLowerCase()})`;
  }, [resultMechanism, periodLabel]);

  function exportPdf() {
    if (!result) return;
    exportSimulationPdf(result, {
      amount: result.parameters?.amount ?? form.amount,
      annualRate: result.parameters?.annual_rate ?? form.annual_rate,
      months: result.parameters?.months ?? form.months,
      periodicityLabel: periodicityOptions.find((item) => item.value === result.parameters?.periodicity)?.label ?? periodLabel,
      mechanismLabel: mechanismOptions.find((item) => item.value === result.parameters?.mechanism)?.label ?? mechanismLabel,
      savingsRate: result.parameters?.savings_rate ?? (form.include_savings ? form.savings_rate : 0),
      firstDueDate: result.parameters?.first_due_date ?? undefined,
      simulationDate: result.parameters?.simulation_date ?? form.simulation_date,
      currency: result.parameters?.currency ?? form.currency,
      tenantName,
      brandPrimary: branding?.brand_primary,
      brandSecondary: branding?.brand_secondary,
      brandAccent: branding?.brand_accent,
    });
  }

  return (
    <div className="page-shell simulator-page">
      <PageHeader
        icon={Calculator}
        title="Simulateur d'amortissement"
        subtitle="Moteur partagé avec les dossiers de crédit et conventions de la filiale"
        actions={
          result ? (
            <button type="button" className="btn btn-ghost" onClick={exportPdf}>
              <FileDown size={16} />
              Exporter PDF
            </button>
          ) : undefined
        }
      />

      <div className="detail-row">
        <Card title="Paramètres du crédit">
          <form onSubmit={submit} className="stack">
            <div className="form-grid two-col">
              <label className="field"><span>Produit (optionnel)</span><select value={form.product} onChange={(e) => {
                const product = products.data?.results.find((row) => row.id === e.target.value);
                setForm({ ...form, product: e.target.value, currency: product?.currency ?? "XOF", annual_rate: product ? "" : DEFAULT_FORM.annual_rate, fees_rate: "", client_type: product?.client_type === "ALL" ? "" : product?.client_type ?? "", individual_profile: "", include_savings: Boolean(product), savings_rate: "" });
              }}><option value="">Simulation libre</option>{products.data?.results.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
              <label className="field"><span>Agence (optionnelle)</span><select value={form.agency} onChange={(e) => setForm({ ...form, agency: e.target.value })}><option value="">Agence de l'utilisateur / sans agence</option>{agencies.data?.results.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
              <label className="field"><span>Type de clientèle</span><select value={form.client_type} onChange={(e) => setForm({ ...form, client_type: e.target.value, individual_profile: "" })}><option value="">Contexte générique / produit</option><option value="INDIVIDUAL">Personne physique</option><option value="CORPORATE">Personne morale</option><option value="PROFESSIONAL">Groupement</option></select></label>
              {form.client_type === "INDIVIDUAL" && <label className="field"><span>Profil particulier</span><select value={form.individual_profile} onChange={(e) => setForm({ ...form, individual_profile: e.target.value })}><option value="">Tous profils</option><option value="SALARIE">Salarié</option><option value="INDEPENDANT">Indépendant / AGR</option><option value="MIXTE">Mixte</option></select></label>}
              <label className="field"><span>Frais de dossier (%)</span><input type="number" min={0} max={100} step="0.001" value={form.fees_rate} placeholder="Selon le barème, sinon zéro" onChange={(e) => setForm({ ...form, fees_rate: e.target.value })} /></label>
              <label className="field">
                <span>Montant du crédit ({form.currency})</span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  required
                  value={formatAmountInput(form.amount)}
                  onChange={(e) =>
                    setForm({ ...form, amount: parseAmountInput(e.target.value) })
                  }
                />
              </label>
              <label className="field">
                <span>Taux d'intérêt annuel (%)</span>
                <input
                  type="number"
                  min={0}
                  step="0.001"
                  required={!form.product}
                  placeholder="Taux du barème / produit"
                  value={form.annual_rate}
                  onChange={(e) =>
                    setForm({ ...form, annual_rate: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Durée (mois)</span>
                <input
                  type="number"
                  min={1}
                  max={600}
                  required
                  value={form.months}
                  onChange={(e) => setForm({ ...form, months: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Périodicité</span>
                <select
                  value={form.periodicity}
                  onChange={(e) =>
                    setForm({ ...form, periodicity: e.target.value })
                  }
                >
                  {periodicityOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Mécanisme de remboursement</span>
                <select
                  value={form.mechanism}
                  onChange={(e) =>
                    setForm({ ...form, mechanism: e.target.value })
                  }
                >
                  {mechanismOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Date de simulation</span>
                <input
                  type="date"
                  required
                  value={form.simulation_date}
                  onChange={(e) =>
                    setForm({ ...form, simulation_date: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Date de 1ʳᵉ échéance (optionnel)</span>
                <input
                  type="date"
                  value={form.first_due_date}
                  min={form.simulation_date || undefined}
                  onChange={(e) =>
                    setForm({ ...form, first_due_date: e.target.value })
                  }
                />
              </label>
            </div>

            <div
              className={`simulator-savings${form.include_savings ? " is-on" : ""}`}
            >
              <label className="checkbox-inline simulator-savings-toggle">
                <input
                  type="checkbox"
                  checked={form.include_savings}
                  onChange={(e) =>
                    setForm({ ...form, include_savings: e.target.checked })
                  }
                />
                <PiggyBank size={16} />
                <span>Inclure l'épargne obligatoire</span>
              </label>

              {form.include_savings && (
                <div className="simulator-savings-fields">
                  <label className="field">
                    <span>Taux d'épargne obligatoire (%)</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step="0.001"
                      required={!form.product}
                      placeholder="Selon le barème, sinon zéro"
                      value={form.savings_rate}
                      onChange={(e) =>
                        setForm({ ...form, savings_rate: e.target.value })
                      }
                    />
                  </label>
                  <p className="muted small">
                    L'épargne est calculée sur le capital avec le taux effectif et
                    les arrondis du serveur. Son montant figure séparément dans
                    le tableau après simulation, hors coût du crédit.
                  </p>
                </div>
              )}
            </div>

            <div className="simulator-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sim.isPending}
              >
                <Play size={16} />
                {sim.isPending ? "Calcul…" : "Simuler l'échéancier"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={reset}
                disabled={sim.isPending}
              >
                <RotateCcw size={16} />
                Réinitialiser
              </button>
            </div>

            {sim.isError && (
              <p className="form-error">
                {apiErrorMessage(sim.error, "Impossible de calculer l'échéancier. Vérifiez les paramètres.")}
              </p>
            )}
          </form>
        </Card>

        <Card
          title={
            <span className="simulator-card-title">
              <CalendarClock size={18} />
              Synthèse
            </span>
          }
        >
          {!result ? (
            <p className="muted">
              Renseignez les paramètres puis lancez la simulation pour obtenir
              l'échéancier prévisionnel.
            </p>
          ) : (
            <>
              <div className="simulator-meta">
                <span>
                  {mechanismLabel} · {periodLabel} · {result.schedule.length}{" "}
                  échéance{result.schedule.length > 1 ? "s" : ""}
                </span>
              </div>
              <div className="metric-grid">
                <Metric
                  label={installmentLabel}
                  value={formatMoney(result.installment ?? result.monthly_payment)}
                />
                {hasSavings && (
                  <Metric
                    label="1ʳᵉ échéance client (avec épargne)"
                    value={formatMoney(result.client_total_first)}
                  />
                )}
                <Metric
                  label="Nombre d'échéances"
                  value={result.schedule.length}
                />
                <Metric
                  label="Intérêts totaux"
                  value={formatMoney(result.total_interest)}
                  tone="warn"
                />
                {hasSavings && (
                  <Metric
                    label="Épargne totale"
                    value={formatMoney(result.total_savings)}
                  />
                )}
                {hasSavings && (
                  <Metric
                    label="Total institution"
                    value={formatMoney(
                      result.total_institution ??
                        num(result.total_repayment) - num(result.total_savings),
                    )}
                  />
                )}
                <Metric
                  label={
                    hasSavings
                      ? "Total à rembourser (client)"
                      : "Total à rembourser"
                  }
                  value={formatMoney(result.total_repayment)}
                  tone="ok"
                />
              </div>
              <div className="metric-grid">
                <Metric label="Frais et taxes sur frais" value={formatMoney(result.total_fees ?? 0, result.parameters?.currency)} />
                <Metric label="Intérêts + frais (hors épargne)" value={formatMoney(result.total_cost_excluding_savings ?? result.total_interest, result.parameters?.currency)} />
                <Metric label="Flux client total, frais et épargne compris" value={formatMoney(result.total_client_outflow ?? result.total_repayment, result.parameters?.currency)} />
              </div>
              {result.pricing_quote && <PricingQuoteSummary quote={result.pricing_quote} />}
            </>
          )}
        </Card>

        {result && (
          <Card
            title={
              <span className="simulator-schedule-head">
                <span className="simulator-card-title">
                  <CalendarClock size={18} />
                  Tableau d'amortissement
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={exportPdf}
                >
                  <FileDown size={15} />
                  Exporter PDF
                </button>
              </span>
            }
          >
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>N°</th>
                    <th>Date</th>
                    <th className="num">Capital</th>
                    <th className="num">Intérêt</th>
                    {hasSavings && <th className="num">Épargne</th>}
                    <th className="num">Échéance institution</th>
                    {hasSavings && <th className="num">Total client</th>}
                    <th className="num">Capital restant</th>
                  </tr>
                </thead>
                <tbody>
                  {result.schedule.map((row) => (
                    <tr key={row.number}>
                      <td>{row.number}</td>
                      <td>{formatDueDate(row.due_date)}{row.nominal_due_date && row.nominal_due_date !== row.due_date && <span className="muted small"> · nominale {formatDueDate(row.nominal_due_date)}</span>}</td>
                      <td className="num">{formatMoney(row.principal)}</td>
                      <td className="num">{formatMoney(row.interest)}</td>
                      {hasSavings && (
                        <td className="num">{formatMoney(row.savings)}</td>
                      )}
                      <td className="num">
                        {formatMoney(row.institution_due ?? num(row.principal) + num(row.interest))}
                      </td>
                      {hasSavings && (
                        <td className="num">{formatMoney(row.total)}</td>
                      )}
                      <td className="num">{formatMoney(row.balance)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}>Totaux</td>
                    <td className="num">
                      {formatMoney(
                        result.schedule.reduce((s, r) => s + num(r.principal), 0),
                      )}
                    </td>
                    <td className="num">{formatMoney(result.total_interest)}</td>
                    {hasSavings && (
                      <td className="num">{formatMoney(result.total_savings)}</td>
                    )}
                    <td className="num">
                      {formatMoney(
                        result.total_institution ??
                          num(result.total_repayment) - num(result.total_savings),
                      )}
                    </td>
                    {hasSavings && (
                      <td className="num">{formatMoney(result.total_repayment)}</td>
                    )}
                    <td className="num">—</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        )}

        <div className="notice-info simulator-basis">
          <Info size={18} />
          <div>
            <strong>Conventions de calcul</strong>
            {result?.pricing_quote?.simulation_conventions?.engine === "CONFIGURED" ? <p>Les conventions effectives figurent avec le devis. Les intérêts utilisent les périodes définies par les dates choisies ; la première période peut être irrégulière. La dernière échéance solde le capital après arrondis. Les dates nominales et ajustées peuvent différer selon le calendrier conservé. La concordance de ces conditions avec le CBS doit être vérifiée.</p> : <ul>
              <li>
                Intérêts jour / jour : taux journalier = taux annuel ÷ 365
                (ACT/365).
              </li>
              <li>
                Dégressif (CBS) : échéance institution constante ; intérêts ↓,
                capital ↑. Le 1ʳᵉ intérêt porte sur une période théorique
                pleine depuis la date de simulation (ex. +1 mois), même si la
                1ʳᵉ échéance est anticipée ou reportée.
              </li>
              <li>
                Montants (capital, intérêts, épargne, échéance) arrondis à la
                dizaine de F CFA.
              </li>
              <li>
                Échéances intermédiaires tombant un week-end reportées au lundi
                (1ʳᵉ et dernière échéance inchangées).
              </li>
              <li>
                Épargne obligatoire : colonne séparée ; l'échéance institution =
                capital + intérêts (hors épargne).
              </li>
            </ul>}
          </div>
        </div>
      </div>
    </div>
  );
}
