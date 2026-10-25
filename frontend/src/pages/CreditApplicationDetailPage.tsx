import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditExposurePanel } from "@/components/CreditExposurePanel";
import {
  ArrowLeft,
  Ban,
  Banknote,
  Briefcase,
  Cable,
  CalendarClock,
  Check,
  CircleDollarSign,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  Factory,
  Download,
  FilePenLine,
  FileSignature,
  FileText,
  Gavel,
  GitBranch,
  HandCoins,
  History,
  Landmark,
  Leaf,
  LineChart,
  MapPin,
  NotebookPen,
  Paperclip,
  Plus,
  RefreshCw,
  Scale,
  Send,
  ShieldAlert,
  ShieldCheck,
  Store,
  Trash2,
  Unlock,
  Upload,
  UserRound,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import { ANALYSIS_TABLES, FinancialAnalysisDetails } from "@/components/FinancialAnalysisDetails";
import { FinancialAnalysisReadout } from "@/components/FinancialAnalysisReadout";
import { FINANCIAL_SUPPLEMENTS } from "@/components/FinancialAnalysisSupplements";
import {
  CLIENT_LABELS,
  CREDIT_LABELS,
  FINANCE_LABELS,
  GUARANTEE_LABELS,
  type ApplicableTemplate,
  type ApprovalTask,
  type ApprovalCondition,
  type Client,
  type CreditApplication,
  type CreditReadiness,
  type CreditSetupState,
  type DationRequest,
  type FieldVisit,
  type FinancialAnalysis,
  type GeneratedContract,
  type Guarantee,
  type GuaranteeFormalizationRequest,
  type GuaranteeReleaseRequest,
  type LoanDetail,
  type Paginated,
  type SuretyEngagement,
  WORKFLOW_LABELS,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import { RestructureRequestPanel } from "@/components/FinancialDecisionPanels";
import {
  PERM_CLIENTS,
  PERM_GUARANTEES,
  PERM_SURETIES,
  isControlePermanent,
} from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import { ApprovalConditionsCard } from "@/components/ApprovalConditionsCard";
import { CollateralSummaryCard } from "@/components/CollateralSummaryCard";
import { DecisionPanel } from "@/components/DecisionPanel";
import { CreditGovernancePanel } from "@/components/CreditGovernancePanel";
import { RenewGuaranteesPanel } from "@/components/RenewGuaranteesPanel";
import { SuretyEngagementActions } from "@/components/SuretyEngagementActions";
import { Badge, ErrorState, Spinner, formatDate, formatMoney } from "@/components/ui";

/** Réponse normalisée de POST …/cbs-situation/ (Perfect crd/situation). */
type CbsCreditSituation = {
  settled?: boolean;
  outstanding?: string;
  days_overdue?: number;
  overdue_amount?: string;
  currency?: string;
  num_demande?: string;
  ref_demande?: string;
  num_contrat?: string;
  schedule?: Array<Record<string, unknown>>;
  raw?: Record<string, unknown>;
};
interface WorkflowInstance {
  id: string;
  object_id: string;
  status: string;
  current_order: number;
  created_at?: string;
  tasks: {
    id: string;
    step_name: string;
    status: string;
    opinion: string;
    opinion_display: string;
    acted_by_display: string | null;
    decision_comment: string;
    proposed_amount: string | null;
  }[];
}

function lbl(map: Record<string, string>, key: string) {
  return map[key] || key || "—";
}

interface TimelineEvent {
  timestamp: string;
  kind: "CREATION" | "WORKFLOW" | "DECISION";
  event: string;
  actor: string | null;
  comment: string;
  step: string | null;
  opinion?: string | null;
}

const TIMELINE_LABELS: Record<string, string> = {
  CREATED: "Création du dossier",
  SUBMITTED: "Soumis au circuit d'approbation",
  RESUBMITTED: "Re-soumis après correction",
  SETUP_REVIEWED: "Contrôle final validé",
  SETUP_COMPLEMENTS_REQUESTED: "Compléments demandés par l'administration crédit",
  SETUP_AUTHORIZED: "Mise en place autorisée par l'administration crédit",
  SETUP_AUTHORIZATION_REVOKED: "Autorisation de mise en place retirée",
  SETUP_TRANSMITTED: "Mise en place confirmée",
  CANCELLED: "Soumission annulée",
  RETURNED_STEP: "Renvoyé à l'étape précédente",
  RETURNED_SUBMITTER: "Renvoyé au soumissionnaire",
  APPROVED: "Étape approuvée",
  REJECTED: "Dossier rejeté",
  RETURNED: "Dossier renvoyé",
};

const TIMELINE_TONE: Record<string, string> = {
  CREATED: "muted",
  SUBMITTED: "info",
  RESUBMITTED: "info",
  SETUP_REVIEWED: "info",
  SETUP_COMPLEMENTS_REQUESTED: "warning",
  SETUP_AUTHORIZED: "success",
  SETUP_AUTHORIZATION_REVOKED: "warning",
  SETUP_TRANSMITTED: "success",
  CANCELLED: "warning",
  RETURNED_STEP: "warning",
  RETURNED_SUBMITTER: "warning",
  APPROVED: "success",
  REJECTED: "danger",
  RETURNED: "warning",
};

// Extrait un message lisible d'une erreur API (formats DRF variés).
function extractApiError(e: unknown, fallback: string): string {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  const errors =
    data && typeof data === "object" && "errors" in data
      ? (data as { errors: unknown }).errors
      : data;
  if (typeof errors === "string") return errors;
  if (Array.isArray(errors)) return errors.filter(Boolean).join(" ");
  if (errors && typeof errors === "object") {
    const parts: string[] = [];
    for (const value of Object.values(errors as Record<string, unknown>)) {
      if (Array.isArray(value)) parts.push(value.filter(Boolean).join(" "));
      else if (value) parts.push(String(value));
    }
    if (parts.length) return parts.join(" ");
  }
  return fallback;
}

const CBS_SITUATION_FALLBACK =
  "Impossible de consulter la situation du crédit pour le moment. Veuillez réessayer ultérieurement.";

/** Masque les détails techniques (HTTP, stack, URL…) côté UI. */
function friendlyCbsSituationError(e: unknown): string {
  const response = (e as { response?: { status?: number } })?.response;
  const status = response?.status;
  if (
    !response ||
    status === 502 ||
    status === 503 ||
    status === 504 ||
    (typeof status === "number" && status >= 500)
  ) {
    return "Le système bancaire est temporairement inaccessible. Veuillez réessayer dans quelques instants.";
  }
  const raw = extractApiError(e, CBS_SITUATION_FALLBACK).trim();
  const low = raw.toLowerCase();
  const technical =
    /https?:\/\//i.test(raw) ||
    /\bhttp\s*\d{3}\b/i.test(raw) ||
    /traceback|exception|stack|timeout|ssl|socket|errno|crd\/|adh\/|gateway|bearer|oauth|client_secret|requests\.|urllib/i.test(
      low,
    );
  if (!raw || technical) return CBS_SITUATION_FALLBACK;
  return raw;
}

function describeGuarantee(g: Guarantee): string {
  if (g.guarantee_type === "MORTGAGE") {
    return [g.document_number, g.address].filter(Boolean).join(" — ");
  }
  if (g.guarantee_type === "PLEDGE" && g.pledge_category === "VEHICLE") {
    return [g.brand, g.model_name, g.registration].filter(Boolean).join(" ");
  }
  if (g.guarantee_type === "FINANCIAL") {
    const t = g.financial_type
      ? GUARANTEE_LABELS.financial_type[g.financial_type]
      : "";
    return [t, g.account_number].filter(Boolean).join(" — ");
  }
  return "";
}

type DocItem = { label: string; url: string };

const GUARANTEE_DOC_LABELS: Record<string, string> = {
  document_scan: "Scan du document",
  expertise_report_scan: "Rapport d'expertise",
  lease_contract_scan: "Contrat de bail",
  legal_situation_certificate_scan: "Certificat de situation juridique",
  registration_card_scan: "Carte grise",
  mechanical_expertise_scan: "Expertise mécanique",
  technical_inspection_scan: "Visite technique",
  insurance_scan: "Assurance",
  purchase_invoice_scan: "Facture d'achat",
  expertise_certificate_scan: "Certificat d'expertise",
  origin_certificate_scan: "Certificat d'origine / facture",
  pledge_deed_scan: "Acte de nantissement / blocage",
};

function guaranteeDocs(g: Guarantee): DocItem[] {
  const docs: DocItem[] = [];
  for (const [key, label] of Object.entries(GUARANTEE_DOC_LABELS)) {
    const url = (g as unknown as Record<string, unknown>)[key];
    if (typeof url === "string" && url) docs.push({ label, url });
  }
  return docs;
}

function clientDocs(c: Client): DocItem[] {
  const map: [keyof Client, string][] = [
    ["id_document_scan", "Pièce d'identité du client"],
    ["photo", "Photo du client"],
    ["ifu_scan", "IFU"],
    ["rccm_scan", "RCCM"],
    ["manager_id_document_scan", "Pièce d'identité du gérant"],
  ];
  const docs: DocItem[] = [];
  for (const [key, label] of map) {
    const url = c[key];
    if (typeof url === "string" && url) docs.push({ label, url });
  }
  return docs;
}

function DocLink({ label, url }: DocItem) {
  return (
    <a className="doc-chip" href={url} target="_blank" rel="noreferrer">
      <FileText size={15} />
      {label}
    </a>
  );
}

function Row({ term, value }: { term: string; value?: ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <dt>{term}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function SubSection({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="subsection">
      <div className="subsection-title">
        <Icon size={15} />
        {title}
      </div>
      {children}
    </div>
  );
}

// Contexte d'accordéon : permet à chaque ViewSection de savoir si elle est
// dépliée, sans faire descendre les props dans les composants intermédiaires.
const SectionCollapseContext = createContext<{
  isOpen: (id: string) => boolean;
  toggle: (id: string) => void;
} | null>(null);

function ViewSection({
  id,
  icon: Icon,
  title,
  description,
  action,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const ctx = useContext(SectionCollapseContext);
  const collapsible = !!ctx;
  const open = ctx ? ctx.isOpen(id) : true;
  return (
    <section
      id={id}
      className={`card form-section${collapsible ? " collapsible" : ""}${
        collapsible && !open ? " collapsed" : ""
      }`}
    >
      <div
        className="card-title form-section-head"
        {...(collapsible
          ? {
              role: "button",
              tabIndex: 0,
              "aria-expanded": open,
              onClick: () => ctx!.toggle(id),
              onKeyDown: (e: KeyboardEvent) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  ctx!.toggle(id);
                }
              },
            }
          : {})}
      >
        <span className="form-section-icon">
          <Icon size={18} />
        </span>
        <div className="form-section-heading">
          <span className="form-section-title">{title}</span>
          {description && (
            <span className="form-section-desc">{description}</span>
          )}
        </div>
        {action && (
          <div
            className="form-section-action"
            onClick={(e) => e.stopPropagation()}
          >
            {action}
          </div>
        )}
        {collapsible && (
          <ChevronDown size={18} className="form-section-chevron" />
        )}
      </div>
      {open && <div className="card-body">{children}</div>}
    </section>
  );
}

// Scroll-spy : suit la section visible et permet la navigation latérale.
function useScrollSpy(deps: unknown[], initial: string) {
  const [active, setActive] = useState(initial);
  useEffect(() => {
    const els = Array.from(
      document.querySelectorAll<HTMLElement>(".form-section"),
    );
    if (els.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [active, setActive] as const;
}

function scrollToSection(id: string) {
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function pct(value: string | number | null): string {
  if (value === null || value === undefined || value === "") return "—";
  return `${Number(value).toFixed(1)} %`;
}

function mNum(
  metrics: FinancialAnalysis["metrics"] | undefined,
  key: string,
): number | null {
  const v = metrics?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function fPct(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(1)} %`;
}
function fX(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(2)}×`;
}
function fDays(v: number | null): string {
  return v === null ? "—" : `${Math.round(v)} j`;
}
function fRatio(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

function boolTone(
  v: boolean | null | undefined,
): "ok" | "warn" | undefined {
  if (v === null || v === undefined) return undefined;
  return v ? "ok" : "warn";
}

function ScorePanel({
  breakdown,
}: {
  breakdown: NonNullable<FinancialAnalysis["score_breakdown"]>;
}) {
  const total = breakdown.total ?? 0;
  const cutoffs = breakdown.risk_cutoffs;
  const tone = cutoffs ? (total >= Number(cutoffs[1]) ? "ok" : total >= Number(cutoffs[2]) ? "mid" : "low")
    : total >= 70 ? "ok" : total >= 50 ? "mid" : "low";
  return (
    <div className={`score-panel score-${tone}`}>
      <div className="score-badge">
        <span className="score-value">{Math.round(total)}</span>
        <span className="score-max">/100</span>
      </div>
      <div className="score-bars">
        <p className="muted small">{breakdown.engine === "CUSTOM" ? "Grille configurée" : "Grille historique"} · poids disponible : {breakdown.effective_weight ?? 100}. Le score est une aide à la décision, pas une probabilité de défaut.</p>
        {!!breakdown.missing_metrics?.length && <p className="muted small">Indicateurs manquants : {breakdown.missing_metrics.join(", ")}. {breakdown.missing_data === "ZERO" ? "Ils sont notés zéro." : "Le score utilise les indicateurs disponibles."}</p>}
        {breakdown.components.map((c) => (
          <div key={c.key} className="score-bar-row">
            <span className="score-bar-label">
              {c.label}
              <em>({c.weight}%)</em>
              {c.raw_value != null && <small>Valeur : {c.raw_value} · borne défavorable {c.bad} / favorable {c.good}</small>}
            </span>
            <span className="score-bar-track">
              <span
                className="score-bar-fill"
                style={{ width: `${c.score ?? 0}%` }}
              />
            </span>
            <span className="score-bar-num">
              {c.score === null ? "—" : Math.round(c.score)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const PERIODS_PER_YEAR: Record<string, number> = {
  DAILY: 360,
  WEEKLY: 52,
  BIMONTHLY: 24,
  MONTHLY: 12,
  QUARTERLY: 4,
  SEMIANNUAL: 2,
  ANNUAL: 1,
};

interface ScheduleRow {
  number: number;
  dueDate: string;
  principal: number;
  interest: number;
  savings: number;
  total: number;
  balance: number;
}

interface SchedulePreview {
  installment: number;
  count: number;
  totalInterest: number;
  totalSavings: number;
  totalRepayment: number;
  periodLabel: string;
  hasSavings: boolean;
  rows: ScheduleRow[];
}

// Les montants du tableau d'amortissement (intérêt, capital, échéance) sont
// arrondis à la dizaine de F CFA (base CBS / LB SERVICES).
const roundStep = (n: number) => Math.round(n / 10) * 10;

function nextBusinessDay(d: Date): Date {
  const r = new Date(d);
  // 0 = dimanche, 6 = samedi → report au lundi
  while (r.getDay() === 0 || r.getDay() === 6) r.setDate(r.getDate() + 1);
  return r;
}

function addPeriods(base: Date, periodicity: string, n: number): Date {
  const r = new Date(base);
  if (periodicity === "DAILY") r.setDate(r.getDate() + n);
  else if (periodicity === "WEEKLY") r.setDate(r.getDate() + n * 7);
  else if (periodicity === "BIMONTHLY") r.setDate(r.getDate() + n * 15);
  else {
    const m: Record<string, number> = {
      MONTHLY: 1,
      QUARTERLY: 3,
      SEMIANNUAL: 6,
      ANNUAL: 12,
    };
    r.setMonth(r.getMonth() + n * (m[periodicity] ?? 1));
  }
  return r;
}

const DAY_MS = 86_400_000;

function computeSchedulePreview(app: CreditApplication): SchedulePreview | null {
  const approvedLike = [
    "APPROVED",
    "CONTRACT_GENERATED",
    "DISBURSEMENT_PENDING",
    "DISBURSED",
    "CLOSED",
  ];
  const principal = Number(
    (approvedLike.includes(app.status) && app.amount_approved
      ? app.amount_approved
      : null) ||
      app.amount_proposed ||
      app.amount_requested ||
      0,
  );
  const annualRate = Number(app.interest_rate || 0) / 100;
  const perYear = PERIODS_PER_YEAR[app.periodicity];
  const months = Number(app.duration_months || 0);
  const mechanism = (app.repayment_mechanism || "DEGRESSIVE").toUpperCase();
  if (!principal || !perYear || !months) return null;
  const count = Math.max(1, Math.ceil((months / 12) * perYear));
  const periodRate = annualRate / perYear;
  const dailyRate = annualRate / 365;
  const savingsFlat = roundStep(
    principal * (Number(app.mandatory_savings_rate || 0) / 100),
  );

  const origin = new Date();
  origin.setHours(0, 0, 0, 0);
  const firstBase = app.first_due_date
    ? new Date(app.first_due_date)
    : addPeriods(origin, app.periodicity, 1);
  // Convention CBS : 1ʳᵉ période d'intérêts = période théorique pleine
  const firstPeriodDays = Math.max(
    0,
    Math.round(
      (addPeriods(origin, app.periodicity, 1).getTime() - origin.getTime()) /
        DAY_MS,
    ),
  );

  const rows: ScheduleRow[] = [];
  let totalInterest = 0;

  // BULLET : une seule échéance au terme
  if (mechanism === "BULLET") {
    const lastNominal = addPeriods(firstBase, app.periodicity, count - 1);
    const days = Math.round(
      (lastNominal.getTime() - origin.getTime()) / DAY_MS,
    );
    const interest = roundStep(principal * dailyRate * Math.max(days, 0));
    const institution = principal + interest;
    totalInterest = interest;
    rows.push({
      number: 1,
      dueDate: lastNominal.toISOString().slice(0, 10),
      principal,
      interest,
      savings: savingsFlat,
      total: institution + savingsFlat,
      balance: 0,
    });
  } else {
    let payment = 0;
    if (mechanism === "DEGRESSIVE" || mechanism === "CONSTANT") {
      if (periodRate > 0) {
        payment =
          (principal * periodRate) / (1 - Math.pow(1 + periodRate, -count));
      } else {
        payment = principal / count;
      }
      payment = roundStep(payment);
    }

    let balance = principal;
    // CONSTANT legacy : période avant 1re échéance
    let prevNominal =
      mechanism === "DEGRESSIVE"
        ? firstBase
        : addPeriods(firstBase, app.periodicity, -1);
    for (let n = 1; n <= count; n++) {
      const nominal = addPeriods(firstBase, app.periodicity, n - 1);
      const days =
        mechanism === "DEGRESSIVE" && n === 1
          ? firstPeriodDays
          : Math.max(
              0,
              Math.round((nominal.getTime() - prevNominal.getTime()) / DAY_MS),
            );
      const interest = roundStep(balance * dailyRate * days);
      const isLast = n === count;
      let principalPart: number;
      if (mechanism === "IN_FINE") {
        principalPart = isLast ? balance : 0;
      } else {
        // DEGRESSIVE / CONSTANT : échéance constante, capital = annuité − intérêts
        principalPart = isLast ? balance : Math.max(0, payment - interest);
      }
      balance = balance - principalPart;
      const due =
        n === 1 || n === count ? nominal : nextBusinessDay(nominal);
      const institution = principalPart + interest;
      totalInterest += interest;
      rows.push({
        number: n,
        dueDate: due.toISOString().slice(0, 10),
        principal: principalPart,
        interest,
        savings: savingsFlat,
        total: institution + savingsFlat,
        balance: balance < 0 ? 0 : balance,
      });
      prevNominal = nominal;
    }
  }

  const firstInstitution =
    (rows[0]?.principal ?? 0) + (rows[0]?.interest ?? 0);

  return {
    installment: firstInstitution,
    count: rows.length,
    totalInterest,
    totalSavings: savingsFlat * rows.length,
    totalRepayment: rows.reduce((s, row) => s + row.total, 0),
    periodLabel: CREDIT_LABELS.periodicity[app.periodicity] || app.periodicity,
    hasSavings: savingsFlat > 0,
    rows,
  };
}

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

function AnalysisDetail({
  analysis,
  currency,
  appId,
}: {
  analysis: FinancialAnalysis;
  currency: string;
  appId: string;
}) {
  const cur = currency;
  const isCorp = analysis.client_type === "CORPORATE";
  const isGroupement = analysis.client_type === "PROFESSIONAL";
  const flags = analysis.flags;
  const m = analysis.metrics;
  const rl = (v: string) =>
    v ? (FINANCE_LABELS.risk_level[v] ?? v) : undefined;
  const ql = (v: string) =>
    v ? (FINANCE_LABELS.quality_level[v] ?? v) : undefined;
  const hasSector =
    !!analysis.sector ||
    !!analysis.sector_risk_level ||
    !!analysis.sector_comment ||
    !!analysis.market_dynamic ||
    !!analysis.value_chain_position;
  const hasES =
    !!analysis.es_category ||
    !!analysis.es_risk_level ||
    !!analysis.es_comment ||
    !!analysis.es_mitigation_plan ||
    analysis.env_permit_required ||
    analysis.eia_required ||
    !!analysis.jobs_created;

  return (
    <div className="analysis-item">
      <div className="analysis-item-head">
        <div className="analysis-author">
          <UserRound size={15} />
          <div>
            <strong>{analysis.created_by_display || "Auteur inconnu"}</strong>
            {analysis.author_role && (
              <span className="analysis-role">{analysis.author_role}</span>
            )}
            {analysis.is_reference && (
              <Badge value="REFERENCE" label="Référence" />
            )}
          </div>
        </div>
        <div className="analysis-head-right">
          {analysis.recommendation && (
            <Badge
              value={analysis.recommendation}
              label={
                `Avis enregistré : ${FINANCE_LABELS.recommendation[analysis.recommendation] || analysis.recommendation}`
              }
            />
          )}
          {analysis.can_edit && (
            <Link
              className="btn btn-ghost btn-sm"
              to={`/dossiers/${appId}/analyse-financiere/${analysis.id}`}
            >
              <FilePenLine size={14} />
              Modifier
            </Link>
          )}
        </div>
      </div>

      <p className="muted small" style={{ marginTop: 0 }}>
        {isCorp
          ? "Entreprise"
          : isGroupement
            ? "Groupement"
            : "Particulier"}{" "}
        · période{" "}
        {FINANCE_LABELS.reference_period[analysis.reference_period] ||
          analysis.reference_period}
        {analysis.analysis_date
          ? ` · analyse du ${formatDate(analysis.analysis_date)}`
          : ""}
        {` · enregistrée le ${formatDate(analysis.created_at)}`}
      </p>

      <FinancialAnalysisReadout analysis={analysis} currency={cur} />

      <details className="subsection"><summary className="subsection-title">Fiabilité et reconstitution financière</summary>
        <dl className="def-list two">
          <Row term="Fiabilité des informations" value={({ DECLARED: "Déclarées", PARTIALLY_VERIFIED: "Partiellement vérifiées", VERIFIED: "Vérifiées", AUDITED: "Comptes audités" } as Record<string, string>)[analysis.information_quality] || "Non renseignée"} />
          <Row term="Date d'arrêté" value={analysis.financial_statement_date ? formatDate(analysis.financial_statement_date) : undefined} />
          <Row term="Source de remboursement" value={analysis.primary_repayment_source} />
          <Row term="Pièces financières vérifiées" value={analysis.financial_documents_verified ? "Oui" : "Non"} />
          <Row term="Mois de relevés examinés" value={analysis.bank_statement_months ?? undefined} />
          <Row term="Employeur" value={analysis.employer_name} />
          <Row term="Activité" value={analysis.activity_name} />
        </dl>
        {analysis.verification_comment && <p>{analysis.verification_comment}</p>}
        <div className="metric-grid">
          <Metric label="Effort mensuel équivalent du nouveau crédit" value={formatMoney(mNum(m, "installment"), cur)} />
          <Metric label="Ventes reconstituées par produits" value={formatMoney(mNum(m, "reconstituted_sales"), cur)} />
          <Metric label="Stock net inventorié" value={formatMoney(mNum(m, "inventory_net_value"), cur)} />
          <Metric label="Mensualités détaillées" value={formatMoney(mNum(m, "detailed_debt_monthly"), cur)} />
          <Metric label="Mois prévisionnels déficitaires" value={mNum(m, "forecast_deficit_months") ?? "—"} />
          <Metric label="Trésorerie de clôture la plus basse" value={formatMoney(mNum(m, "forecast_lowest_balance"), cur)} />
        </div>
        {analysis.metrics.debt_service_reconciled === false && <p className="form-error">Les mensualités détaillées ne correspondent pas au total déclaré. Rapprocher les engagements avant décision.</p>}
        {Object.entries(analysis.analysis_details || {}).filter(([key, value]) => !(key in FINANCIAL_SUPPLEMENTS) && !key.endsWith("_detail_mode") && typeof value === "string" && value).map(([key, value]) => <div key={key}>
          <p className="subsection-label">{({ business_model: "Modèle économique", seasonality: "Saisonnalité", sales_verification: "Vérification du chiffre d'affaires", stock_risks: "Qualité du stock", receivables_quality: "Qualité des créances", asset_ownership: "Propriété des actifs", household_income_evidence: "Justificatifs des revenus", employment_outlook: "Perspectives de l'emploi", project_cost: "Coût du projet", own_contribution: "Apport propre", financing_plan: "Plan de financement", stress_assumptions: "Hypothèses défavorables", monitoring_plan: "Plan de suivi", bureau_reference: "Référence BIC", bureau_discrepancies: "Écarts BIC", banking_behavior: "Fonctionnement bancaire" } as Record<string, string>)[key] || key}</p>
          <p>{typeof value === "string" ? value : ""}</p>
        </div>)}
        {Object.keys(ANALYSIS_TABLES).map((name) => <FinancialAnalysisDetails key={name} name={name} value={analysis.analysis_details || {}} currency={cur} />)}
      </details>

      {analysis.score_breakdown &&
        analysis.score_breakdown.total !== null &&
        analysis.score_breakdown.total !== undefined && (
          <ScorePanel breakdown={analysis.score_breakdown} />
        )}
      {analysis.score_breakdown?.total === null && !!analysis.score_breakdown.missing_metrics?.length && (
        <p className="form-error">Score non calculable : {analysis.score_breakdown.missing_metrics.join(", ")}. Complétez les indicateurs exigés par la grille.</p>
      )}

      <details className="subsection"><summary className="subsection-title">Ratios approfondis (contre-analyse)</summary>
        <div className="metric-grid">
          {isCorp ? (
            <>
              <Metric label="DSCR global" value={fX(mNum(m, "global_dscr"))} tone={boolTone(flags?.dscr_ok)} />
              <Metric label="Couverture charges fin." value={fX(mNum(m, "interest_coverage"))} tone={boolTone(flags?.interest_coverage_ok)} />
              <Metric label="Autonomie financière" value={fPct(mNum(m, "financial_autonomy"))} tone={boolTone(flags?.autonomy_ok)} />
              <Metric label="Gearing (dettes fin./CP)" value={fRatio(mNum(m, "gearing"))} tone={boolTone(flags?.gearing_ok)} />
              <Metric label="Liquidité générale" value={fRatio(mNum(m, "current_ratio"))} tone={boolTone(flags?.current_ratio_ok)} />
              <Metric label="Liquidité réduite" value={fRatio(mNum(m, "quick_ratio"))} />
              <Metric label="Fonds de roulement (FR)" value={formatMoney(mNum(m, "working_capital"), cur)} />
              <Metric label="Trésorerie nette (TN)" value={formatMoney(mNum(m, "treasury_net"), cur)} />
              <Metric label="BFR (jours de CA)" value={fDays(mNum(m, "bfr_days"))} />
              <Metric label="Délai clients (DSO)" value={fDays(mNum(m, "dso_days"))} />
              <Metric label="Délai fournisseurs (DPO)" value={fDays(mNum(m, "dpo_days"))} />
              <Metric label="Rotation stocks (DIO)" value={fDays(mNum(m, "dio_days"))} />
              <Metric label="Rentabilité financière (ROE)" value={fPct(mNum(m, "roe"))} />
              <Metric label="Rentabilité économique (ROA)" value={fPct(mNum(m, "roa"))} />
              <Metric label="Seuil rentabilité (ventilation validée)" value={formatMoney(mNum(m, "break_even_turnover"), cur)} />
              <Metric label="Croissance du CA" value={fPct(mNum(m, "turnover_growth"))} />
              <Metric label="Croissance du résultat" value={fPct(mNum(m, "result_growth"))} />
            </>
          ) : isGroupement ? (
            <>
              <Metric label="Taux d'endettement global" value={fPct(mNum(m, "debt_ratio"))} tone={boolTone(flags?.debt_ratio_ok)} />
              <Metric label="Revenus collectifs" value={formatMoney(mNum(m, "collective_income"), cur)} />
              <Metric label="Charges collectives" value={formatMoney(mNum(m, "collective_charges"), cur)} />
              <Metric
                label="Capacité nette"
                value={formatMoney(mNum(m, "collective_net_capacity"), cur)}
                tone={boolTone(flags?.capacity_ok)}
              />
              <Metric label="Participation des cotisants" value={fPct(mNum(m, "contribution_concentration"))} />
            </>
          ) : (
            <>
              <Metric label="Taux d'endettement global" value={fPct(mNum(m, "debt_ratio"))} tone={boolTone(flags?.debt_ratio_ok)} />
              <Metric label="Revenu pondéré" value={formatMoney(mNum(m, "weighted_income"), cur)} />
              <Metric label="Taux d'effort (revenu pondéré)" value={fPct(mNum(m, "debt_ratio_weighted"))} />
              <Metric label="Reste à vivre après crédit" value={formatMoney(mNum(m, "residual_after_loan"), cur)} />
              <Metric label="Reste à vivre / personne" value={formatMoney(mNum(m, "disposable_per_capita"), cur)} tone={boolTone(flags?.living_wage_ok)} />
              {Number(analysis.net_salary) > 0 && (
                <>
                  <Metric label="Quotité cessible disponible" value={formatMoney(mNum(m, "transferable_quota_available"), cur)} tone={boolTone(flags?.quota_ok)} />
                </>
              )}
            </>
          )}
          <Metric label="Couverture par garanties" value={fPct(mNum(m, "guarantee_coverage"))} tone={boolTone(flags?.guarantee_ok)} />
          <Metric label="Marge de sécurité" value={formatMoney(mNum(m, "safety_margin"), cur)} />
        </div>
      </details>

      <SubSection icon={ShieldAlert} title="Stress test & sensibilité">
        <div className="metric-grid">
          {isCorp ? (
            <Metric
              label="DSCR sous stress"
              value={analysis.dscr_stress ?? "—"}
              tone={boolTone(flags?.dscr_stress_ok)}
            />
          ) : (
            <Metric
              label="Taux d'endettement sous stress"
              value={pct(analysis.debt_ratio_stress)}
              tone={boolTone(flags?.debt_ratio_stress_ok)}
            />
          )}
        </div>
        <p className="muted small" style={{ marginTop: 8 }}>
          Scénario : baisse de{" "}
          {analysis.thresholds?.stress_pct ?? 20} % des{" "}
          {isCorp ? "ventes" : isGroupement ? "recettes collectives" : "revenus / ventes d'activité"}, charges maintenues. Les hypothèses complémentaires sont détaillées dans les formules.
        </p>
      </SubSection>

      {(analysis.credit_bureau_checked ||
        analysis.has_payment_incidents ||
        analysis.active_loans_count > 0 ||
        analysis.prior_loans_count > 0) && (
        <SubSection icon={History} title="Endettement consolidé & historique">
          <dl className="def-list two">
            <Row term="Crédits actifs (tous prêteurs)" value={analysis.active_loans_count || undefined} />
            <Row
              term="Centrale des risques / BIC"
              value={
                analysis.credit_bureau_checked
                  ? `Consultée${analysis.credit_bureau_date ? ` le ${formatDate(analysis.credit_bureau_date)}` : ""}`
                  : "Non consultée"
              }
            />
            <Row
              term="Incidents de paiement"
              value={analysis.has_payment_incidents ? "Oui" : "Non"}
            />
            <Row
              term="Retard max constaté"
              value={analysis.max_days_late ? `${analysis.max_days_late} j` : undefined}
            />
            <Row term="Crédits antérieurs (interne)" value={analysis.prior_loans_count || undefined} />
            <Row term="Taux de remboursement historique" value={pct(analysis.prior_repayment_rate)} />
            <Row
              term="Retard max historique"
              value={analysis.prior_max_delay_days ? `${analysis.prior_max_delay_days} j` : undefined}
            />
          </dl>
          {analysis.incidents_comment && (
            <p className="prose">{analysis.incidents_comment}</p>
          )}
        </SubSection>
      )}

      {hasSector && (
        <SubSection icon={Factory} title="Analyse sectorielle">
          <dl className="def-list two">
            {analysis.sector && (
              <Row
                term="Secteur"
                value={FINANCE_LABELS.sector[analysis.sector] ?? analysis.sector}
              />
            )}
            <Row term="Sous-secteur / filière" value={analysis.sub_sector || undefined} />
            {analysis.value_chain_position && (
              <Row
                term="Chaîne de valeur"
                value={
                  FINANCE_LABELS.value_chain_position[
                    analysis.value_chain_position
                  ] ?? analysis.value_chain_position
                }
              />
            )}
            {analysis.market_dynamic && (
              <Row
                term="Dynamique du marché"
                value={
                  FINANCE_LABELS.market_dynamic[analysis.market_dynamic] ??
                  analysis.market_dynamic
                }
              />
            )}
            <Row term="Saisonnalité" value={rl(analysis.seasonality_level)} />
            <Row term="Concurrence" value={rl(analysis.competition_intensity)} />
            <Row term="Dépendance fournisseurs" value={rl(analysis.supplier_dependency)} />
            <Row term="Concentration clientèle" value={rl(analysis.client_concentration)} />
            <Row term="Sensibilité prix intrants" value={rl(analysis.input_price_sensitivity)} />
            <Row term="Exposition devises / imports" value={rl(analysis.fx_exposure)} />
            <Row term="Sensibilité réglementaire" value={rl(analysis.regulatory_sensitivity)} />
            <Row term="Sensibilité climatique" value={rl(analysis.climate_sensitivity)} />
            <Row term="Risque sectoriel global" value={rl(analysis.sector_risk_level)} />
          </dl>
          {analysis.sector_outlook && (
            <p className="prose">
              <strong>Perspectives : </strong>
              {analysis.sector_outlook}
            </p>
          )}
          {analysis.sector_comment && (
            <p className="prose">{analysis.sector_comment}</p>
          )}
        </SubSection>
      )}

      {hasES && (
        <SubSection
          icon={Leaf}
          title="Analyse environnementale & sociale (E&S)"
        >
          <dl className="def-list two">
            {analysis.es_category && (
              <Row
                term="Catégorie E&S"
                value={
                  FINANCE_LABELS.es_category[analysis.es_category] ??
                  analysis.es_category
                }
              />
            )}
            <Row
              term="Liste d'exclusion"
              value={analysis.exclusion_list_ok ? "Conforme" : "Non conforme"}
            />
            <Row
              term="Conformité réglementaire E&S"
              value={analysis.es_regulatory_compliance ? "Oui" : "Non"}
            />
            <Row
              term="Autorisation environnementale"
              value={
                analysis.env_permit_required
                  ? analysis.env_permit_obtained
                    ? `Obtenue${analysis.permit_reference ? ` (${analysis.permit_reference})` : ""}`
                    : "Requise — non obtenue"
                  : "Non requise"
              }
            />
            <Row
              term="Étude d'impact (EIE)"
              value={
                analysis.eia_required
                  ? analysis.eia_done
                    ? "Réalisée"
                    : "Requise — non réalisée"
                  : "Non requise"
              }
            />
            <Row term="Gestion des déchets" value={ql(analysis.waste_management)} />
            <Row term="Usage eau / énergie" value={ql(analysis.resource_use)} />
            <Row term="Produits chimiques / pesticides" value={ql(analysis.chemicals_pesticides)} />
            <Row term="Nuisances / pollution" value={ql(analysis.nuisances_emissions)} />
            <Row term="Conditions de travail" value={ql(analysis.working_conditions)} />
            <Row term="Sécurité & santé au travail" value={ql(analysis.occupational_safety)} />
            <Row term="Risque travail enfants / forcé" value={rl(analysis.child_forced_labor_risk)} />
            <Row term="Impact communautés" value={ql(analysis.community_impact)} />
            <Row term="Enjeux fonciers / réinstallation" value={rl(analysis.land_resettlement_risk)} />
            <Row
              term="Emplois créés"
              value={
                analysis.jobs_created !== null
                  ? `${analysis.jobs_created}${
                      analysis.jobs_women !== null || analysis.jobs_youth !== null
                        ? ` (dont ${analysis.jobs_women ?? 0} F / ${analysis.jobs_youth ?? 0} jeunes)`
                        : ""
                    }`
                  : undefined
              }
            />
            <Row
              term="Emplois maintenus"
              value={
                analysis.jobs_maintained !== null
                  ? String(analysis.jobs_maintained)
                  : undefined
              }
            />
            <Row
              term="Plan d'action E&S exigé"
              value={analysis.es_action_required ? "Oui" : "Non"}
            />
            <Row
              term="Assurances E&S"
              value={analysis.es_insurance ? "Oui" : "Non"}
            />
            <Row term="Risque E&S global" value={rl(analysis.es_risk_level)} />
          </dl>
          {analysis.es_mitigation_plan && (
            <p className="prose">
              <strong>Plan d'atténuation (PGES) : </strong>
              {analysis.es_mitigation_plan}
            </p>
          )}
          {analysis.es_comment && (
            <p className="prose">{analysis.es_comment}</p>
          )}
        </SubSection>
      )}

      {(analysis.strengths ||
        analysis.weaknesses ||
        analysis.recommended_conditions) && (
        <SubSection icon={NotebookPen} title="Synthèse structurée">
          {analysis.strengths && (
            <div className="synthesis-block synthesis-ok">
              <strong>Points forts</strong>
              <p className="prose">{analysis.strengths}</p>
            </div>
          )}
          {analysis.weaknesses && (
            <div className="synthesis-block synthesis-warn">
              <strong>Points de vigilance</strong>
              <p className="prose">{analysis.weaknesses}</p>
            </div>
          )}
          {analysis.recommended_conditions && (
            <div className="synthesis-block">
              <strong>Conditions / recommandations</strong>
              <p className="prose">{analysis.recommended_conditions}</p>
            </div>
          )}
        </SubSection>
      )}

      {(analysis.existing_debt_institution ||
        Number(analysis.existing_debt_monthly) > 0 ||
        Number(analysis.ongoing_credit_balance) > 0) && (
        <SubSection icon={Landmark} title="Endettement existant">
          <dl className="def-list two">
            <Row term="Institution" value={analysis.existing_debt_institution} />
            <Row
              term="Montant initial"
              value={
                Number(analysis.existing_debt_initial_amount) > 0
                  ? formatMoney(analysis.existing_debt_initial_amount, cur)
                  : undefined
              }
            />
            <Row
              term="Mensualité"
              value={
                Number(analysis.existing_debt_monthly) > 0
                  ? formatMoney(analysis.existing_debt_monthly, cur)
                  : undefined
              }
            />
            <Row
              term="Encours restant"
              value={
                Number(analysis.ongoing_credit_balance) > 0
                  ? formatMoney(analysis.ongoing_credit_balance, cur)
                  : undefined
              }
            />
          </dl>
        </SubSection>
      )}

      {analysis.comment && (
        <SubSection icon={NotebookPen} title="Avis de l'analyste">
          <p className="prose">{analysis.comment}</p>
        </SubSection>
      )}

      {analysis.documents.length > 0 && (
        <SubSection icon={Paperclip} title="Pièces justificatives">
          <div className="doc-row">
            {analysis.documents.map((d) => (
              <DocLink key={d.id} label={d.label || "Document"} url={d.file} />
            ))}
          </div>
        </SubSection>
      )}
    </div>
  );
}

function FinancialAnalysesSection({
  analyses,
  currency,
  appId,
  canContribute,
  loading,
  error,
  onRetry,
}: {
  analyses: FinancialAnalysis[];
  currency: string;
  appId: string;
  canContribute: boolean;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  return (
    <ViewSection
      id="sec-financial"
      icon={LineChart}
      title="Analyses financières"
      description={
        analyses.length > 1
          ? `${analyses.length} analyses réalisées au fil du circuit.`
          : undefined
      }
      action={
        canContribute ? (
          <Link
            className="btn btn-ghost btn-sm"
            to={`/dossiers/${appId}/analyse-financiere`}
          >
            <Plus size={14} />
            Ajouter une analyse
          </Link>
        ) : undefined
      }
    >
      {error ? <div role="alert"><p className="form-error">Impossible de charger les analyses financières.</p><button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>Réessayer</button></div> : loading ? <p className="muted">Chargement des analyses financières…</p> : analyses.length === 0 ? (
        <p className="muted small">Aucune analyse financière enregistrée.</p>
      ) : (
        <div className="analysis-list">
          {analyses.map((a) => (
            <AnalysisDetail
              key={a.id}
              analysis={a}
              currency={currency}
              appId={appId}
            />
          ))}
        </div>
      )}
    </ViewSection>
  );
}

function FieldVisitsCard({
  appId,
  canAdd,
}: {
  appId: string;
  canAdd: boolean;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [visitDate, setVisitDate] = useState("");
  const [report, setReport] = useState("");
  const [geoCoordinates, setGeoCoordinates] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: visits } = useQuery({
    queryKey: ["field-visits", appId],
    queryFn: async () =>
      (
        await api.get<Paginated<FieldVisit>>("/field-visits/", {
          params: { application: appId },
        })
      ).data,
    enabled: !!appId,
  });

  const addMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post("/field-visits/", {
          application: appId,
          visit_date: visitDate,
          report,
          geo_coordinates: geoCoordinates.trim(),
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["field-visits", appId] });
      setOpen(false);
      setVisitDate("");
      setReport("");
      setGeoCoordinates("");
      setError(null);
    },
    onError: () => setError("Enregistrement de la visite impossible."),
  });

  function save() {
    if (!visitDate) {
      setError("La date de visite est obligatoire.");
      return;
    }
    setError(null);
    addMutation.mutate();
  }

  return (
    <ViewSection id="sec-visits" icon={MapPin} title="Visites terrain">
      {visits && visits.results.length > 0 ? (
        <div className="visit-list">
          {visits.results.map((v) => (
            <div key={v.id} className="visit-item">
              <div className="visit-item-head">
                <div className="analysis-author">
                  <UserRound size={15} />
                  <div>
                    <strong>{v.visited_by_display || "Auteur inconnu"}</strong>
                    {v.visitor_role && (
                      <span className="analysis-role">{v.visitor_role}</span>
                    )}
                  </div>
                </div>
                <span className="visit-date">
                  <MapPin size={14} /> {formatDate(v.visit_date)}
                </span>
              </div>
              {v.report && <p className="prose">{v.report}</p>}
              {v.geo_coordinates?.trim() && (
                <a
                  className="muted small"
                  href={`https://maps.google.com/?q=${encodeURIComponent(v.geo_coordinates.trim())}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <MapPin size={12} /> {v.geo_coordinates.trim()}
                </a>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted small">Aucune visite terrain enregistrée.</p>
      )}

      {canAdd && !open && (
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
          <Plus size={15} />
          Ajouter une visite
        </button>
      )}

      {canAdd && open && (
        <div className="stack" style={{ marginTop: 12 }}>
          <div className="form-grid two-col">
            <label className="field">
              <span>
                Date de visite <em className="req"> *</em>
              </span>
              <input
                type="date"
                value={visitDate}
                onChange={(e) => setVisitDate(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Coordonnées géographiques</span>
              <input
                value={geoCoordinates}
                onChange={(e) => setGeoCoordinates(e.target.value)}
                placeholder="ex. 5.359952, -4.008256"
              />
            </label>
          </div>
          <label className="field">
            <span>Compte rendu</span>
            <textarea
              rows={3}
              value={report}
              onChange={(e) => setReport(e.target.value)}
            />
          </label>
          {error && <div className="form-error">{error}</div>}
          <div className="page-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setOpen(false)}
            >
              Annuler
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={save}
              disabled={addMutation.isPending}
            >
              Enregistrer la visite
            </button>
          </div>
        </div>
      )}
    </ViewSection>
  );
}

function TemplateRow({
  item,
  appId,
  canGenerate,
  onDone,
}: {
  item: ApplicableTemplate;
  appId: string;
  canGenerate: boolean;
  onDone: () => void;
}) {
  const tpl = item.template;
  const [openForm, setOpenForm] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const generate = useMutation({
    mutationFn: async () => {
      const res = await api.post(
        "/generated-contracts/generate/",
        {
          application: appId,
          template: tpl.id,
          extra_values: values,
        },
        { validateStatus: (s) => s === 200 || s === 201 || s === 202 },
      );
      return { status: res.status, data: res.data as Record<string, unknown> };
    },
    onSuccess: async (payload) => {
      setError(null);
      setOpenForm(false);
      onDone();
      const taskId =
        typeof payload.data?.task_id === "string"
          ? payload.data.task_id
          : null;
      if (
        (payload.status === 202 || payload.data?.status === "queued") &&
        taskId
      ) {
        try {
          const { pollAsyncTask } = await import("@/utils/pollAsyncTask");
          await pollAsyncTask(taskId, { onTick: onDone, maxAttempts: 30 });
          onDone();
        } catch (e) {
          setError(
            e instanceof Error
              ? e.message
              : "La génération du contrat a échoué.",
          );
        }
      }
    },
    onError: (e) =>
      setError(extractApiError(e, "La génération du contrat a échoué.")),
  });

  const hasExtra = (tpl.extra_fields?.length ?? 0) > 0;

  function trigger() {
    if (hasExtra && !openForm) {
      setOpenForm(true);
      return;
    }
    generate.mutate();
  }

  return (
    <div className="contract-template-row">
      <div className="contract-template-info">
        <span className="contract-template-icon">
          <FileText size={16} />
        </span>
        <div>
          <strong>{tpl.name}</strong>
          <div className="contract-template-badges">
            {tpl.category_display && (
              <span className="chip chip-muted">{tpl.category_display}</span>
            )}
            {tpl.is_required && (
              <span className="chip chip-warn">Obligatoire</span>
            )}
            {item.generated && (
              <span className="chip chip-ok">Généré</span>
            )}
          </div>
        </div>
      </div>
      {canGenerate && (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={trigger}
          disabled={generate.isPending}
        >
          <FileSignature size={14} />
          {item.generated ? "Régénérer" : "Générer"}
        </button>
      )}
      {openForm && (
        <div className="contract-extra-form">
          {tpl.extra_fields.map((f) => (
            <label key={f.key} className="field">
              <span>{f.label || f.key}</span>
              <input
                type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.key]: e.target.value }))
                }
              />
            </label>
          ))}
          <div className="page-actions">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setOpenForm(false)}
            >
              Annuler
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
            >
              Générer le contrat
            </button>
          </div>
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
    </div>
  );
}

function GeneratedContractRow({
  contract,
  canManage,
  onDone,
}: {
  contract: GeneratedContract;
  canManage: boolean;
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const uploadSigned = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("signed_file", file);
      return (
        await api.post(
          `/generated-contracts/${contract.id}/upload_signed/`,
          fd,
          { headers: { "Content-Type": "multipart/form-data" } },
        )
      ).data;
    },
    onSuccess: () => {
      setError(null);
      onDone();
    },
    onError: (e) =>
      setError(extractApiError(e, "L'import du contrat signé a échoué.")),
  });

  return (
    <div className="generated-contract-row">
      <div className="contract-template-info">
        <span className="contract-template-icon">
          <FileSignature size={16} />
        </span>
        <div>
          <strong>{contract.template_name}</strong>
          <div className="contract-template-badges">
            <Badge value={contract.status} label={contract.status_display} />
            {contract.created_by_name && (
              <span className="muted small">par {contract.created_by_name}</span>
            )}
            <span className="muted small">{formatDate(contract.created_at)}</span>
          </div>
        </div>
      </div>
      <div className="row-actions">
        {contract.file && (
          <a
            className="btn btn-ghost btn-sm"
            href={contract.file}
            target="_blank"
            rel="noreferrer"
          >
            <Download size={14} />
            Télécharger
          </a>
        )}
        {contract.signed_file && (
          <a
            className="btn btn-ghost btn-sm"
            href={contract.signed_file}
            target="_blank"
            rel="noreferrer"
          >
            <FileText size={14} />
            Version signée
          </a>
        )}
        {canManage && (
          <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>
            <Upload size={14} />
            {contract.signed_file ? "Remplacer signé" : "Importer signé"}
            <input
              type="file"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadSigned.mutate(file);
              }}
            />
          </label>
        )}
      </div>
      {error && <div className="form-error">{error}</div>}
    </div>
  );
}

function ContractsSection({
  appId,
  canGenerate,
}: {
  appId: string;
  canGenerate: boolean;
}) {
  const qc = useQueryClient();

  const { data: applicable } = useQuery({
    queryKey: ["contract-templates-applicable", appId],
    queryFn: async () =>
      (
        await api.get<ApplicableTemplate[]>("/contract-templates/applicable/", {
          params: { application: appId },
        })
      ).data,
    enabled: !!appId,
  });

  const { data: generated } = useQuery({
    queryKey: ["generated-contracts", appId],
    queryFn: async () =>
      (
        await api.get<Paginated<GeneratedContract>>("/generated-contracts/", {
          params: { application: appId },
        })
      ).data,
    enabled: !!appId,
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["contract-templates-applicable", appId] });
    qc.invalidateQueries({ queryKey: ["generated-contracts", appId] });
    qc.invalidateQueries({ queryKey: ["credit-application", appId] });
  }

  const templates = applicable ?? [];
  const contracts = (generated?.results ?? []).filter(
    (c) => c.status !== "CANCELLED",
  );

  return (
    <ViewSection
      id="sec-contracts"
      icon={FileSignature}
      title="Contrats"
      description="Génération des contrats à signer avant mise en place."
    >
      <SubSection icon={FileText} title="Modèles disponibles">
        {templates.length === 0 ? (
          <p className="muted small">
            Aucun modèle de contrat applicable. Configurez les modèles de la
            filiale dans « Administration → Contrats ».
          </p>
        ) : (
          <div className="contract-template-list">
            {templates.map((t) => (
              <TemplateRow
                key={t.template.id}
                item={t}
                appId={appId}
                canGenerate={canGenerate}
                onDone={refresh}
              />
            ))}
          </div>
        )}
      </SubSection>

      <SubSection icon={FileSignature} title="Contrats générés">
        {contracts.length === 0 ? (
          <p className="muted small">Aucun contrat généré pour l'instant.</p>
        ) : (
          <div className="contract-template-list">
            {contracts.map((c) => (
              <GeneratedContractRow
                key={c.id}
                contract={c}
                canManage={canGenerate}
                onDone={refresh}
              />
            ))}
          </div>
        )}
      </SubSection>
    </ViewSection>
  );
}

export function CreditApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [showSchedule, setShowSchedule] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cbsSituationOpen, setCbsSituationOpen] = useState(false);
  const [cbsSituation, setCbsSituation] = useState<CbsCreditSituation | null>(
    null,
  );
  const [cbsSituationError, setCbsSituationError] = useState<string | null>(
    null,
  );

  const { data: app, isLoading, isError, refetch } = useQuery({
    queryKey: ["credit-application", id],
    queryFn: async () =>
      (await api.get<CreditApplication>(`/credit-applications/${id}/`)).data,
    enabled: !!id,
  });

  const { data: readiness } = useQuery({
    queryKey: ["credit-readiness", id],
    queryFn: async () =>
      (
        await api.get<CreditReadiness>(
          `/credit-applications/${id}/readiness/`,
        )
      ).data,
    enabled: !!id,
  });

  const { data: setupGate } = useQuery({
    queryKey: ["setup-review", id],
    queryFn: async () => (await api.get<CreditSetupState>(`/credit-applications/${id}/setup-review/`)).data,
    enabled: !!id && !!app && ["APPROVED", "CONTRACT_GENERATED", "DISBURSEMENT_PENDING"].includes(app.status),
  });

  const { data: guarantees } = useQuery({
    queryKey: ["guarantees", id],
    queryFn: async () =>
      (
        await api.get<Paginated<Guarantee>>("/guarantees/", {
          params: { application: id },
        })
      ).data,
    enabled: !!id,
  });

  const { data: engagements } = useQuery({
    queryKey: ["surety-engagements", id],
    queryFn: async () =>
      (
        await api.get<Paginated<SuretyEngagement>>("/surety-engagements/", {
          params: { application: id },
        })
      ).data,
    enabled: !!id,
  });

  const canViewDations = hasPerm(user, "guarantees.view_dationrequest");
  const canViewFormalizations = hasPerm(
    user,
    "guarantees.view_guaranteeformalizationrequest",
  );
  const canViewReleases = hasPerm(
    user,
    "guarantees.view_guaranteereleaserequest",
  );

  const { data: dations } = useQuery({
    queryKey: ["dation-requests", id],
    queryFn: async () =>
      (
        await api.get<Paginated<DationRequest>>("/dation-requests/", {
          params: { application: id },
        })
      ).data,
    enabled: !!id && canViewDations,
  });

  const { data: formalizations } = useQuery({
    queryKey: ["guarantee-formalizations", id],
    queryFn: async () =>
      (
        await api.get<Paginated<GuaranteeFormalizationRequest>>(
          "/guarantee-formalizations/",
          { params: { application: id } },
        )
      ).data,
    enabled: !!id && canViewFormalizations,
  });

  const { data: releases } = useQuery({
    queryKey: ["guarantee-releases", id],
    queryFn: async () =>
      (
        await api.get<Paginated<GuaranteeReleaseRequest>>(
          "/guarantee-releases/",
          { params: { application: id } },
        )
      ).data,
    enabled: !!id && canViewReleases,
  });

  const { data: client, isError: clientError, refetch: refetchClient } = useQuery({
    queryKey: ["client", app?.client],
    queryFn: async () =>
      (await api.get<Client>(`/clients/${app!.client}/`)).data,
    enabled: !!app?.client,
  });

  const { data: loan } = useQuery({
    queryKey: ["loan", app?.loan_id],
    queryFn: async () =>
      (await api.get<LoanDetail>(`/loans/${app!.loan_id}/`)).data,
    enabled: !!app?.loan_id,
  });

  const { data: financials, isLoading: financialLoading, isError: financialError, refetch: refetchFinancials } = useQuery({
    queryKey: ["financial-analysis", id],
    queryFn: async () =>
      (
        await api.get<Paginated<FinancialAnalysis>>("/financial-analyses/", {
          params: { application: id },
        })
      ).data,
    enabled: !!id,
  });

  const { data: instances, isLoading: workflowLoading, isError: workflowError, refetch: refetchWorkflow } = useQuery({
    queryKey: ["workflow-instances", id],
    queryFn: async () =>
      {
        const results: WorkflowInstance[] = [];
        let page = 1;
        while (true) {
          const { data } = await api.get<Paginated<WorkflowInstance>>("/workflow-instances/", { params: { object_id: id, page, page_size: 100 } });
          results.push(...data.results);
          if (!data.next) return { results };
          page++;
        }
      },
    enabled: !!id && hasPerm(user, "workflow.view_workflowinstance"),
  });

  const { data: myTasks } = useQuery({
    queryKey: ["my-pending-tasks"],
    queryFn: async () =>
      (await api.get<Paginated<ApprovalTask>>("/approval-tasks/my_pending/"))
        .data,
  });

  const { data: conditions } = useQuery({
    queryKey: ["approval-conditions", id],
    queryFn: async () =>
      (
        await api.get<Paginated<ApprovalCondition>>("/approval-conditions/", {
          params: { application: id },
        })
      ).data,
    enabled: !!id,
  });

  const { data: timeline } = useQuery({
    queryKey: ["credit-timeline", id],
    queryFn: async () =>
      (
        await api.get<{ results: TimelineEvent[] }>(
          `/credit-applications/${id}/timeline/`,
        )
      ).data,
    enabled: !!id,
  });

  const submitMutation = useMutation({
    mutationFn: async () =>
      (await api.post(`/credit-applications/${id}/submit/`)).data,
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["credit-application", id] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      qc.invalidateQueries({ queryKey: ["credit-timeline", id] });
      qc.invalidateQueries({ queryKey: ["credit-readiness", id] });
    },
    onError: (e) =>
      setActionError(
        extractApiError(
          e,
          "La soumission a échoué. Vérifiez qu'un circuit d'approbation actif " +
            "couvre ce dossier, puis réessayez.",
        ),
      ),
  });

  const cancelDossierMutation = useMutation({
    mutationFn: async () =>
      (await api.post(`/credit-applications/${id}/cancel/`)).data,
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["credit-application", id] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      qc.invalidateQueries({ queryKey: ["credit-timeline", id] });
    },
    onError: (e) =>
      setActionError(
        extractApiError(e, "L'annulation formelle du dossier a échoué."),
      ),
  });

  const disburseMutation = useMutation({
    mutationFn: async () =>
      (await api.post(`/credit-applications/${id}/disburse/`)).data,
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["credit-application", id] });
    },
    onError: (e) =>
      setActionError(extractApiError(e, "La mise en place a échoué.")),
  });

  const requestDisburseMutation = useMutation({
    mutationFn: async () =>
      (await api.post(`/credit-applications/${id}/request-disburse/`)).data,
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["credit-application", id] });
    },
    onError: (e) =>
      setActionError(
        extractApiError(e, "La demande de mise en place a échoué."),
      ),
  });

  const cancelDisburseRequestMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/credit-applications/${id}/cancel-disburse-request/`)
      ).data,
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["credit-application", id] });
    },
    onError: (e) =>
      setActionError(
        extractApiError(e, "L'annulation de la demande a échoué."),
      ),
  });

  const cancelMutation = useMutation({
    mutationFn: async () =>
      (await api.post(`/credit-applications/${id}/cancel_submission/`)).data,
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["credit-application", id] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      qc.invalidateQueries({ queryKey: ["credit-timeline", id] });
    },
    onError: (e) =>
      setActionError(
        extractApiError(e, "L'annulation de la soumission a échoué."),
      ),
  });

  const cbsSituationMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<CbsCreditSituation>(
          `/credit-applications/${id}/cbs-situation/`,
        )
      ).data,
    onSuccess: (data) => {
      setCbsSituation(data);
      setCbsSituationError(null);
      setActionError(null);
    },
    onError: (e) => {
      setCbsSituationError(friendlyCbsSituationError(e));
    },
  });

  function openCbsSituationModal() {
    setCbsSituationOpen(true);
    setCbsSituationError(null);
    cbsSituationMutation.mutate();
  }

  function closeCbsSituationModal() {
    setCbsSituationOpen(false);
    setCbsSituationError(null);
  }

  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/credit-applications/${id}/`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credit-applications"] });
      navigate("/dossiers");
    },
    onError: (e) =>
      setActionError(extractApiError(e, "La suppression a échoué.")),
  });

  const [activeSection, setActiveSection] = useScrollSpy(
    [app?.id, app?.status],
    "sec-terms",
  );

  // Les principales informations de décision sont ouvertes à l'arrivée.
  const [openSections, setOpenSections] = useState<Set<string>>(
    () => new Set(["sec-client-profile", "sec-terms", "sec-financial", "sec-patrimoine"]),
  );

  useEffect(() => {
    const hasDecisionTask = !!myTasks?.results.some(
      (t) => t.application?.id === id,
    );
    if (!hasDecisionTask) return;
    setOpenSections((prev) => {
      if (prev.has("sec-decision")) return prev;
      return new Set(prev).add("sec-decision");
    });
  }, [myTasks, id]);

  if (isLoading) return <Spinner />;
  if (isError || !app) {
    return (
      <ErrorState
        message="Impossible de charger le dossier de crédit."
        onRetry={() => refetch()}
      />
    );
  }

  // Un dossier peut avoir plusieurs instances (cycles renvoyés/annulés puis
  // re-soumis) : on privilégie le cycle actif, sinon le plus récent.
  const appInstances = (instances?.results ?? []).filter(
    (i) => i.object_id === app.id,
  );
  const instance =
    appInstances.find((i) =>
      ["IN_PROGRESS", "AWAITING_CONDITIONS"].includes(i.status),
    ) ??
    [...appInstances].sort((a, b) =>
      (b.created_at ?? "").localeCompare(a.created_at ?? ""),
    )[0];
  const myTask =
    myTasks?.results.find((t) => t.application?.id === app.id) ?? null;
  const analyses = financials?.results ?? [];

  const uid = user?.id;
  const isSuper = !!user?.is_superuser;
  const canChangeCredit = hasPerm(user, "credits.change_creditapplication");
  const canDeleteCredit = hasPerm(user, "credits.delete_creditapplication");
  const canAddAnalysis = hasPerm(user, "credits.add_financialanalysis");
  const canAddVisit = hasPerm(user, "credits.add_fieldvisit");
  const canAddContract = hasPerm(user, "contracts.add_generatedcontract");
  const canAddGuarantee = hasPerm(user, "guarantees.add_guarantee");
  const canViewGuarantees = hasAnyPerm(user, PERM_GUARANTEES);
  const canAddSurety = hasPerm(user, "sureties.add_suretyengagement");
  const canViewSureties = hasAnyPerm(user, PERM_SURETIES);
  const canManageSuretyEng = hasPerm(user, "sureties.change_suretyengagement");
  const canViewCollections = hasPerm(user, "collections.view_collectioncase");
  const canProposeRestructure = hasPerm(user, "collections.add_loanrestructure");
  const canDecideRestructure = hasPerm(
    user,
    "collections.change_loanrestructure",
  );
  const showRestructure = Boolean(
    loan &&
      (canProposeRestructure ||
        canDecideRestructure ||
        (loan.restructures?.length ?? 0) > 0),
  );
  const showAfterSales =
    (dations?.results.length ?? 0) > 0 ||
    (formalizations?.results.length ?? 0) > 0 ||
    (releases?.results.length ?? 0) > 0;
  const isOwner =
    !!uid && (app.created_by === uid || app.submitted_by === uid);
  // Soumission et suppression : réservées au créateur du dossier (ou super-admin),
  // en cohérence avec le contrôle backend.
  const isCreator = isSuper || (!!uid && app.created_by === uid);
  // L'annulation de soumission reste réservée au soumetteur (ou super-admin,
  // en cohérence avec le contrôle backend).
  const isSubmitter =
    isSuper ||
    (!!uid &&
      (app.submitted_by === uid ||
        (!app.submitted_by && app.created_by === uid)));

  // Une étape a déjà statué (approbation, renvoi ou rejet) sur le dossier.
  const aStepActed = !!instance?.tasks?.some((t) =>
    ["APPROVED", "RETURNED", "REJECTED"].includes(t.status),
  );

  const editableStatus = ["DRAFT", "RETURNED"].includes(app.status);
  const canSubmit = editableStatus && isCreator && canChangeCredit;
  // Édition des champs du dossier : créateur seul (Analyste/Comité = analyses).
  const canEdit = editableStatus && canChangeCredit && isCreator;
  // L'annulation n'est possible que tant qu'aucune étape n'a agi (sauf super-admin).
  const canCancel =
    app.status === "IN_APPROVAL" &&
    isSubmitter &&
    canChangeCredit &&
    (isSuper || !aStepActed);
  const collateralStatuses = [
    "DRAFT",
    "RETURNED",
    "APPROVED",
    "CONTRACT_GENERATED",
    "DISBURSEMENT_PENDING",
    ...(readiness?.policy.allow_collateral_during_approval
      ? (["IN_APPROVAL", "SUBMITTED"] as const)
      : []),
  ];
  const canAttachCollateral = collateralStatuses.includes(app.status);
  const canCancelDossier =
    !!readiness?.policy.enable_cancel_status &&
    isCreator &&
    canChangeCredit &&
    !["DISBURSED", "CLOSED", "CANCELLED"].includes(app.status);
  const readyForDisburse = ["APPROVED", "CONTRACT_GENERATED"].includes(
    app.status,
  );
  const canDisburse =
    setupGate?.can_transmit === true &&
    (readyForDisburse || app.status === "DISBURSEMENT_PENDING") &&
    (!(readiness?.policy.require_setup_request || readiness?.policy.require_setup_four_eyes) || app.status === "DISBURSEMENT_PENDING") &&
    (!readiness?.policy.require_setup_four_eyes || (!!app.disbursement_requested_by && app.disbursement_requested_by !== user?.id)) &&
    hasPerm(user, "credits.disburse_creditapplication");
  const canRequestDisburse =
    readyForDisburse &&
    setupGate?.authorization_valid === true &&
    hasPerm(user, "credits.initiate_disburse_creditapplication");
  const canCancelDisburseRequest =
    app.status === "DISBURSEMENT_PENDING" &&
    (hasPerm(user, "credits.initiate_disburse_creditapplication") ||
      hasPerm(user, "credits.disburse_creditapplication"));
  // Contractualisation : visible dès l'approbation ; génération réservée à
  // l'initiateur (ou un profil privilégié) tant que le dossier n'est pas mis en place.
  const showContracts = [
    "APPROVED",
    "CONTRACT_GENERATED",
    "DISBURSEMENT_PENDING",
    "DISBURSED",
    "CLOSED",
  ].includes(app.status);
  const canGenerateContracts =
    (isOwner || isSuper) &&
    canAddContract &&
    ["APPROVED", "CONTRACT_GENERATED", "DISBURSEMENT_PENDING"].includes(
      app.status,
    );
  // Suppression réservée au créateur et uniquement sur un brouillon non soumis.
  const canDelete = isCreator && canDeleteCredit && app.status === "DRAFT";
  // Contribution : initiateur ou tâche PENDING, + droit d'ajout analyse/visite.
  const openForContribution = [
    "DRAFT",
    "SUBMITTED",
    "IN_APPROVAL",
    "RETURNED",
  ].includes(app.status);
  const canContributeWindow =
    isSuper || ((isOwner && openForContribution) || !!myTask);
  // Après mise en place : plus d'ajout d'analyse financière (lecture seule).
  const analysisLocked = [
    "DISBURSED",
    "CLOSED",
    "CANCELLED",
    "REJECTED",
  ].includes(app.status);
  const canContributeAnalysis =
    canContributeWindow && canAddAnalysis && !analysisLocked;
  const canContributeVisit =
    canAddVisit && (canContributeWindow || isControlePermanent(user));
  const cur = app.currency;

  const activeGuarantees = (guarantees?.results ?? []).filter(
    (g) => g.status === "ACTIVE",
  );
  const excludedGuaranteeCount = (guarantees?.results ?? []).filter((g) =>
    ["REALIZED", "RELEASED", "TRANSFERRED"].includes(g.status),
  ).length;
  const guaranteeTotal = activeGuarantees.reduce(
    (s, g) => s + Number(g.current_value || 0),
    0,
  );
  const coverageBase = Number(
    ([
      "APPROVED",
      "CONTRACT_GENERATED",
      "DISBURSEMENT_PENDING",
      "DISBURSED",
      "CLOSED",
    ].includes(app.status) &&
      app.amount_approved) ||
      app.amount_proposed ||
      app.amount_requested ||
      0,
  );
  const coveragePct =
    coverageBase > 0 ? (guaranteeTotal / coverageBase) * 100 : null;

  const schedule = computeSchedulePreview(app);

  const showActivity = !!(
    app.activity_start_date ||
    app.exact_address ||
    app.clientele ||
    app.tax_regime ||
    app.avg_client_payment_days != null ||
    app.avg_supplier_payment_days != null ||
    app.catchment_area ||
    (app.stock_photos && app.stock_photos.length > 0)
  );
  const showApplicant = !!(
    app.employer_name ||
    app.contract_type ||
    app.dependents_count != null ||
    app.salary_domiciliation
  );
  const showBanking = !!(
    app.client_account_number ||
    app.relationship_start_date ||
    Number(app.avg_monthly_credit_movements) > 0
  );
  const showInsurance = !!(
    app.has_credit_insurance ||
    app.insurance_company ||
    Number(app.insurance_premium) > 0
  );
  const showSpecial = !!(app.special_conditions || app.suspensive_conditions);
  const showCompliance = !!(
    app.beneficial_owner ||
    app.is_pep ||
    app.funds_origin
  );
  const hasChecklist = !!(
    app.document_checklist && app.document_checklist.length > 0
  );
  const hasConditions = (conditions?.results.length ?? 0) > 0;

  const navSections = [
    { id: "sec-decision", icon: Gavel, label: "Décision à rendre", show: !!myTask, group: "Priorité" },
    { id: "sec-conditions", icon: ClipboardCheck, label: "Réserves", show: hasConditions, group: "Priorité" },
    {
      id: "sec-readiness",
      icon: ClipboardCheck,
      label: "Ready à soumettre",
      show: Boolean(
        canSubmit && readiness?.show_checklist && editableStatus,
      ),
      group: "Priorité",
    },
    { id: "sec-client-profile", icon: UserRound, label: "Profil & conformité client", show: true, group: "Profil" },
    { id: "sec-terms", icon: Banknote, label: "Conditions du crédit", show: true, group: "Instruction" },
    { id: "sec-financial", icon: LineChart, label: "Analyse financière", show: true, group: "Instruction" },
    { id: "sec-exposure", icon: Wallet, label: "Engagements & relations", show: hasPerm(user, "credits.view_creditexposureobservation"), group: "Instruction" },
    { id: "sec-patrimoine", icon: Landmark, label: "Garanties & cautions", show: true, group: "Instruction" },
    {
      id: "sec-aftersales",
      icon: Scale,
      label: "Après-vente",
      show: showAfterSales,
      group: "Suivi",
    },
    {
      id: "sec-restructure",
      icon: RefreshCw,
      label: "Restructuration",
      show: showRestructure,
      group: "Suivi",
    },
    { id: "sec-activity", icon: Store, label: "Activité & commerce", show: showActivity, group: "Profil" },
    { id: "sec-applicant", icon: Briefcase, label: "Demandeur & emploi", show: showApplicant, group: "Profil" },
    { id: "sec-banking", icon: History, label: "Relation bancaire", show: showBanking, group: "Profil" },
    { id: "sec-insurance", icon: ShieldCheck, label: "Assurance", show: showInsurance, group: "Profil" },
    { id: "sec-special", icon: NotebookPen, label: "Conditions particulières", show: showSpecial, group: "Profil" },
    { id: "sec-compliance", icon: ShieldCheck, label: "Conformité (LBC-FT)", show: showCompliance, group: "Profil" },
    { id: "sec-schedule", icon: CalendarClock, label: "Échéancier", show: !!schedule, group: "Suivi" },
    { id: "sec-visits", icon: MapPin, label: "Visites terrain", show: true, group: "Suivi" },
    { id: "sec-checklist", icon: ClipboardList, label: "Pièces du dossier", show: hasChecklist, group: "Pièces" },
    { id: "sec-documents", icon: Paperclip, label: "Documents", show: true, group: "Pièces" },
    { id: "sec-contracts", icon: FileSignature, label: "Contrats", show: showContracts, group: "Pièces" },
    { id: "sec-workflow", icon: GitBranch, label: "Circuit d'approbation", show: true, group: "Circuit" },
    { id: "sec-timeline", icon: History, label: "Historique & audit", show: true, group: "Circuit" },
  ].filter((s) => s.show);

  const collapseCtx = {
    isOpen: (sid: string) => openSections.has(sid),
    toggle: (sid: string) =>
      setOpenSections((prev) => {
        const next = new Set(prev);
        if (next.has(sid)) next.delete(sid);
        else next.add(sid);
        return next;
      }),
  };
  const openAllSections = () =>
    setOpenSections(new Set(navSections.map((s) => s.id)));
  const closeAllSections = () => setOpenSections(new Set());
  const allOpen = navSections.every((s) => openSections.has(s.id));

  function goToSection(sid: string) {
    setActiveSection(sid);
    setOpenSections((prev) => new Set(prev).add(sid));
    // Laisse le contenu se déplier avant de défiler vers l'en-tête.
    setTimeout(() => scrollToSection(sid), 60);
  }

  function cancelSubmission() {
    if (
      window.confirm(
        "Annuler la soumission ? Le dossier repassera en brouillon et le circuit d'approbation en cours sera annulé.",
      )
    ) {
      cancelMutation.mutate();
    }
  }

  function deleteApplication() {
    if (
      window.confirm(
        "Supprimer définitivement ce dossier ? Cette action est irréversible.",
      )
    ) {
      deleteMutation.mutate();
    }
  }

  return (
    <div className="page-shell dossier-page detail-banner-page">
      <div className="credit-hero">
        <div className="credit-hero-main">
          <div className="credit-hero-top">
            <div className="credit-hero-info">
              <span className="credit-hero-icon">
                <FileText size={26} />
              </span>
              <div className="credit-hero-text">
                <h2 className="credit-hero-name">
                  <PermLink
                    user={user}
                    anyOf={PERM_CLIENTS}
                    className="link-inline"
                    to={`/clients/${app.client}`}
                  >
                    {app.client_display}
                  </PermLink>
                </h2>
                <p className="credit-hero-ref">
                  Dossier <code>{app.reference || app.id.slice(0, 8)}</code>
                  {app.product_label && (
                    <span className="muted"> · {app.product_label}</span>
                  )}
                </p>
                <div className="credit-hero-meta">
                  <Badge value={app.status} label={app.status_display} />
                  {app.agency_display && (
                    <span className="muted">{app.agency_display}</span>
                  )}
                </div>
              </div>
            </div>

            <div className="credit-hero-actions">
              <Link className="btn btn-banner" to="/dossiers">
                <ArrowLeft size={15} />
                Retour
              </Link>
              {(app.cbs_demande_ref ||
                app.cbs_contract_number ||
                app.status === "DISBURSED" ||
                app.status === "CLOSED") && (
                <button
                  type="button"
                  className="btn btn-banner"
                  onClick={openCbsSituationModal}
                  title="Consulter la situation crédit via Perfect crd/situation"
                >
                  <Landmark size={15} />
                  Situation crédit CBS
                </button>
              )}
              {canViewCollections && app.collection_case_id && (
                <Link
                  className="btn btn-banner"
                  to={`/recouvrement/${app.collection_case_id}`}
                >
                  <CircleDollarSign size={15} />
                  Recouvrement
                  {app.collection_stage_display
                    ? ` · ${app.collection_stage_display}`
                    : ""}
                </Link>
              )}
              {canEdit && (
                <Link
                  className="btn btn-banner"
                  to={`/dossiers/${id}/modifier`}
                >
                  <FilePenLine size={15} />
                  Modifier
                </Link>
              )}
              {canContributeAnalysis && (
                <Link
                  className="btn btn-banner"
                  to={`/dossiers/${id}/analyse-financiere`}
                >
                  <LineChart size={15} />
                  Ajouter une analyse
                </Link>
              )}
              {canCancel && (
                <button
                  type="button"
                  className="btn btn-banner btn-banner-danger"
                  onClick={cancelSubmission}
                  disabled={cancelMutation.isPending}
                >
                  <Ban size={15} />
                  Annuler la soumission
                </button>
              )}
              {canSubmit && (
                <button
                  type="button"
                  className="btn btn-banner btn-banner-primary"
                  onClick={() => submitMutation.mutate()}
                  disabled={
                    submitMutation.isPending ||
                    (readiness?.show_checklist === true &&
                      readiness.ready === false)
                  }
                  title={
                    readiness?.show_checklist && !readiness.ready
                      ? "Complétez la checklist de readiness avant de soumettre"
                      : undefined
                  }
                >
                  <Send size={15} />
                  Soumettre à validation
                </button>
              )}
              {canCancelDossier && (
                <button
                  type="button"
                  className="btn btn-banner btn-banner-danger"
                  onClick={() => {
                    if (
                      window.confirm(
                        "Annuler définitivement ce dossier (statut Annulé) ?",
                      )
                    ) {
                      cancelDossierMutation.mutate();
                    }
                  }}
                  disabled={cancelDossierMutation.isPending}
                >
                  <Ban size={15} />
                  Annuler le dossier
                </button>
              )}
              {canRequestDisburse && (
                <button
                  type="button"
                  className="btn btn-banner btn-banner-primary"
                  onClick={() => requestDisburseMutation.mutate()}
                  disabled={requestDisburseMutation.isPending}
                >
                  <Wallet size={15} />
                  Demander la mise en place
                </button>
              )}
              {canDisburse && (
                <button
                  type="button"
                  className="btn btn-banner btn-banner-primary"
                  onClick={() => disburseMutation.mutate()}
                  disabled={disburseMutation.isPending}
                >
                  <Wallet size={15} />
                  Transmettre au CBS
                </button>
              )}
              {canCancelDisburseRequest && (
                <button
                  type="button"
                  className="btn btn-banner"
                  onClick={() => cancelDisburseRequestMutation.mutate()}
                  disabled={cancelDisburseRequestMutation.isPending}
                >
                  Annuler la demande
                </button>
              )}
              {canDelete && (
                <button
                  type="button"
                  className="btn btn-banner btn-banner-danger"
                  onClick={deleteApplication}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 size={15} />
                  Supprimer
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {actionError && (
        <div className="form-error" style={{ marginBottom: 0 }}>
          {actionError}
        </div>
      )}

      {cbsSituationOpen && (
        <div
          className="modal-backdrop modal-backdrop--top"
          role="presentation"
          onClick={closeCbsSituationModal}
        >
          <div
            className="modal-card modal-card--xl cbs-situation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cbs-situation-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="cbs-situation-modal__header">
              <div>
                <h3 id="cbs-situation-title">
                  <Landmark size={18} />
                  Situation du crédit
                </h3>
                <p className="muted small" style={{ margin: "4px 0 0" }}>
                  Dossier <code>{app.reference}</code>
                  {app.client_display ? ` · ${app.client_display}` : ""}
                </p>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={closeCbsSituationModal}
                aria-label="Fermer"
              >
                Fermer
              </button>
            </header>

            <div className="cbs-situation-modal__body">
              {cbsSituationMutation.isPending && !cbsSituation && (
                <div className="cbs-situation-modal__loading">
                  <Spinner />
                  <p className="muted">Chargement de la situation du crédit…</p>
                </div>
              )}

              {cbsSituationError && (
                <div className="form-error" style={{ marginBottom: 12 }}>
                  {cbsSituationError}
                </div>
              )}

              {cbsSituation && (
                <>
                  <dl className="def-list two">
                    <Row
                      term="N° demande (numDemande)"
                      value={cbsSituation.num_demande || "—"}
                    />
                    <Row
                      term="Réf. demande (refDemande)"
                      value={cbsSituation.ref_demande || "—"}
                    />
                    <Row
                      term="N° contrat (numContrat)"
                      value={cbsSituation.num_contrat || "—"}
                    />
                    <Row
                      term="Soldé"
                      value={
                        cbsSituation.settled === true
                          ? "Oui"
                          : cbsSituation.settled === false
                            ? "Non"
                            : "—"
                      }
                    />
                    <Row
                      term="Encours"
                      value={formatMoney(
                        cbsSituation.outstanding ?? null,
                        cbsSituation.currency || app.currency || "XOF",
                      )}
                    />
                    <Row
                      term="Retard (jours)"
                      value={
                        cbsSituation.days_overdue != null
                          ? String(cbsSituation.days_overdue)
                          : "—"
                      }
                    />
                    <Row
                      term="Montant en retard"
                      value={formatMoney(
                        cbsSituation.overdue_amount ?? null,
                        cbsSituation.currency || app.currency || "XOF",
                      )}
                    />
                    <Row
                      term="Devise CBS"
                      value={cbsSituation.currency || "—"}
                    />
                  </dl>

                  <h4 className="section-subtitle" style={{ marginTop: 16 }}>
                    Échéancier CBS
                  </h4>
                  {(cbsSituation.schedule?.length ?? 0) === 0 ? (
                    <p className="muted small">
                      Aucune échéance renvoyée par le CBS.
                    </p>
                  ) : (
                    <div className="table-scroll table-scroll--rows-20">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Date</th>
                            <th className="num">Capital</th>
                            <th className="num">Intérêt</th>
                            <th className="num">Total</th>
                            <th>Statut</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(cbsSituation.schedule ?? []).map((row, idx) => {
                            const cur =
                              cbsSituation.currency || app.currency || "XOF";
                            return (
                              <tr key={idx}>
                                <td>{String(row.echeance ?? idx + 1)}</td>
                                <td>{String(row.date ?? "—")}</td>
                                <td className="num">
                                  {formatMoney(
                                    row.montantCapital != null
                                      ? String(row.montantCapital)
                                      : null,
                                    cur,
                                  )}
                                </td>
                                <td className="num">
                                  {formatMoney(
                                    row.montantInteret != null
                                      ? String(row.montantInteret)
                                      : null,
                                    cur,
                                  )}
                                </td>
                                <td className="num">
                                  {formatMoney(
                                    row.montantTotal != null
                                      ? String(row.montantTotal)
                                      : null,
                                    cur,
                                  )}
                                </td>
                                <td>{String(row.statut ?? "—")}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>

            <footer className="cbs-situation-modal__footer">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={closeCbsSituationModal}
              >
                Fermer
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={cbsSituationMutation.isPending}
                onClick={() => cbsSituationMutation.mutate()}
              >
                <RefreshCw size={14} />
                {cbsSituationMutation.isPending
                  ? "Actualisation…"
                  : "Actualiser"}
              </button>
            </footer>
          </div>
        </div>
      )}

      <div className="credit-form">
        <aside className="credit-form-nav">
          <div className="credit-form-nav-inner">
            <p className="credit-form-nav-title">Navigation</p>
            {navSections.map((s, idx) => {
              const prevGroup = idx > 0 ? navSections[idx - 1].group : null;
              const showGroup = s.group && s.group !== prevGroup;
              return (
                <div key={s.id}>
                  {showGroup && (
                    <p className="credit-nav-group">{s.group}</p>
                  )}
                  <button
                    type="button"
                    className={`credit-nav-item${activeSection === s.id ? " active" : ""}${
                      openSections.has(s.id) ? " open" : ""
                    }`}
                    onClick={() => goToSection(s.id)}
                  >
                    <s.icon size={16} />
                    <span>{s.label}</span>
                  </button>
                </div>
              );
            })}
            <button
              type="button"
              className="btn btn-ghost btn-sm credit-nav-toggle-all"
              onClick={allOpen ? closeAllSections : openAllSections}
            >
              {allOpen ? "Tout replier" : "Tout déplier"}
            </button>
          </div>
        </aside>

        <SectionCollapseContext.Provider value={collapseCtx}>
        <div className="credit-form-main stack">
          <CreditGovernancePanel applicationId={app.id} status={app.status} />
          <ViewSection
            id="sec-client-profile"
            icon={UserRound}
            title="Profil & conformité client"
            description="Identité, coordonnées et état KYC tels qu’enregistrés dans la fiche client."
            action={
              <PermLink
                user={user}
                anyOf={PERM_CLIENTS}
                fallback={null}
                className="btn btn-ghost btn-sm"
                to={`/clients/${app.client}`}
              >
                Ouvrir la fiche client
              </PermLink>
            }
          >
            {clientError ? (
              <div role="alert">
                <p className="form-error">Impossible de charger le profil client. Les informations de conformité sont indisponibles.</p>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => void refetchClient()}>Réessayer</button>
              </div>
            ) : !client ? (
              <p className="muted small">Chargement du profil client…</p>
            ) : (
              <>
                <div className="checklist-badges">
                  <Badge
                    value={client.kyc_status}
                    label={
                      ({
                        PENDING: "KYC en attente",
                        VALIDATED: "KYC validé",
                        REJECTED: "KYC rejeté",
                        EXPIRED: "KYC expiré",
                      } as Record<string, string>)[client.kyc_status] || client.kyc_status
                    }
                  />
                  <Badge
                    value={client.is_active ? "ACTIVE" : "INACTIVE"}
                    label={client.is_active ? "Client actif" : "Client inactif"}
                  />
                </div>
                <dl className="def-list two">
                  <Row term="Référence client" value={client.reference} />
                  <Row term="Nom du client" value={client.display_name} />
                  <Row term="Type de client" value={CLIENT_LABELS.client_type[client.client_type]} />
                  <Row term="Téléphone" value={client.phone} />
                  <Row term="E-mail" value={client.email} />
                  <Row term="Adresse" value={[client.address, client.city].filter(Boolean).join(", ")} />
                  {client.client_type === "INDIVIDUAL" ? (
                    <>
                      <Row term="Nationalité" value={client.nationality} />
                      <Row term="Date de naissance" value={client.birth_date ? formatDate(client.birth_date) : undefined} />
                      <Row term="Profession" value={client.profession} />
                      <Row term="Situation matrimoniale" value={CLIENT_LABELS.marital_status[client.marital_status]} />
                      <Row term="Pièce d’identité" value={[CLIENT_LABELS.id_document_type[client.id_document_type] || client.id_document_type, client.national_id].filter(Boolean).join(" · ")} />
                      <Row term="Validité de la pièce" value={client.id_document_expiry_date ? formatDate(client.id_document_expiry_date) : undefined} />
                    </>
                  ) : (
                    <>
                      <Row term="Raison sociale" value={client.company_name || client.display_name} />
                      <Row term="Forme juridique" value={CLIENT_LABELS.legal_form[client.legal_form] || client.legal_form} />
                      <Row term="IFU" value={client.ifu} />
                      <Row term="RCCM" value={client.rccm} />
                      <Row term="Dirigeant" value={[client.manager_first_name, client.manager_last_name].filter(Boolean).join(" ")} />
                      <Row term="Fonction du dirigeant" value={client.manager_position} />
                      <Row term="Téléphone du dirigeant" value={client.manager_phone} />
                      <Row term="Validité de la pièce du dirigeant" value={client.manager_id_document_expiry_date ? formatDate(client.manager_id_document_expiry_date) : undefined} />
                    </>
                  )}
                  <Row term="KYC validé le" value={client.kyc_validated_at ? formatDate(client.kyc_validated_at) : undefined} />
                  {client.agency === app.agency && <Row term="Agence de rattachement" value={app.agency_display || undefined} />}
                </dl>
                {client.kyc_status !== "VALIDATED" && (
                  <p className="form-error" role="status">
                    Le statut KYC du client est « {({ PENDING: "en attente", REJECTED: "rejeté", EXPIRED: "expiré" } as Record<string, string>)[client.kyc_status] || client.kyc_status} ». Vérifiez la conformité avant décision.
                  </p>
                )}
              </>
            )}
          </ViewSection>
          {myTask && (
            <ViewSection
              id="sec-decision"
              icon={Gavel}
              title={`Décision — ${myTask.step_name}`}
              description="Vous êtes habilité à statuer sur cette étape."
            >
              <p className="muted small" style={{ marginTop: 0 }}>
                Consultez ci-dessous l'ensemble du dossier, des garanties, des
                cautions et des documents, puis validez, retournez ou rejetez le
                dossier.
              </p>
              <DecisionPanel task={myTask} />
            </ViewSection>
          )}

          {hasConditions && (
            <ViewSection
              id="sec-conditions"
              icon={ClipboardCheck}
              title="Réserves d'approbation"
            >
              <ApprovalConditionsCard
                conditions={conditions!.results}
                appId={app.id}
              />
            </ViewSection>
          )}

          {canSubmit && readiness?.show_checklist && (
            <ViewSection
              id="sec-readiness"
              icon={ClipboardCheck}
              title="Préparation à la soumission"
              description="Contrôles selon la politique d'instruction de la filiale."
            >
              <ul className="readiness-list">
                {readiness.checks.map((c) => (
                  <li
                    key={c.key}
                    className={`readiness-item${c.ok ? " ok" : c.blocking ? " blocking" : " warn"}`}
                  >
                    <span className="readiness-mark">
                      {c.ok ? <Check size={14} /> : <X size={14} />}
                    </span>
                    <div>
                      <strong>{c.label}</strong>
                      {!c.ok && c.message && (
                        <p className="muted small">{c.message}</p>
                      )}
                      {!c.blocking && !c.ok && (
                        <span className="muted small">{c.key === "cbs_mapping" ? "Bloquant avant autorisation de mise en place" : "Alerte (non bloquant)"}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              <p className={`muted small${readiness.ready ? "" : " readiness-block-hint"}`}>
                {readiness.ready
                  ? "Le dossier peut être soumis au circuit."
                  : "Corrigez les points bloquants avant de soumettre."}
              </p>
            </ViewSection>
          )}

          <ViewSection
            id="sec-terms"
            icon={Banknote}
            title="Conditions du crédit"
          >
            <dl className="def-list two">
            <Row term="Montant demandé" value={formatMoney(app.amount_requested, cur)} />
            <Row term="Montant proposé" value={app.amount_proposed && formatMoney(app.amount_proposed, cur)} />
            <Row term="Montant accordé" value={app.amount_approved && formatMoney(app.amount_approved, cur)} />
            <Row term="Devise" value={app.currency_label || app.currency} />
            <Row term="Taux d'intérêt" value={app.interest_rate && `${app.interest_rate} %`} />
            <Row
              term="Épargne obligatoire"
              value={
                app.mandatory_savings_rate
                  ? `${app.mandatory_savings_rate} % (hors ratios institution)`
                  : undefined
              }
            />
            <Row
              term="Périodicité"
              value={
                app.periodicity_label ||
                lbl(CREDIT_LABELS.periodicity, app.periodicity)
              }
            />
            <Row term="Durée" value={`${app.duration_months} mois`} />
            <Row term="Première échéance" value={app.first_due_date && formatDate(app.first_due_date)} />
            <Row term="Dernière échéance" value={app.last_due_date && formatDate(app.last_due_date)} />
            <Row
              term="Mécanisme"
              value={
                app.repayment_mechanism_label ||
                (app.repayment_mechanism &&
                  lbl(
                    CREDIT_LABELS.repayment_mechanism,
                    app.repayment_mechanism,
                  ))
              }
            />
            <Row term="Objet du financement" value={app.purpose_type && lbl(CREDIT_LABELS.purpose_type, app.purpose_type)} />
            <Row term="Objet de financement CBS exact" value={app.cbs_refs?.financing_object?.label ? `${app.cbs_refs.financing_object.label} (${app.cbs_refs.financing_object.cbs_code})` : "À sélectionner"} />
            <Row term="Niveau de risque (circuit)" value={app.risk_level ?? undefined} />
          </dl>
          {app.cbs_refs && (
            <details className="subsection"><summary className="subsection-title">Informations de transmission au CBS</summary>
              <dl className="def-list two">
                <Row
                  term="Périodicité"
                  value={
                    app.cbs_refs.periodicity?.label ||
                    app.periodicity_label ||
                    "—"
                  }
                />
                <Row
                  term="Type de crédit"
                  value={app.product_label || "—"}
                />
                <Row term="Produit de crédit CBS" value={app.cbs_refs.product_cbs_code || "Produit crédit à configurer"} />
                <Row term="Référence de remboursement CBS" value={app.cbs_refs.product_repayment_cbs_code || "Référence CBS à renseigner"} />
                <Row
                  term="Mécanisme de remboursement"
                  value={
                    app.cbs_refs.repayment_method?.label ||
                    app.repayment_mechanism_label ||
                    "—"
                  }
                />
                <Row
                  term="Devise transmise"
                  value={
                    app.cbs_refs.currency?.cbs_code || app.currency || "—"
                  }
                />
                <Row
                  term="Gestionnaire"
                  value={
                    app.submitted_by_display ||
                    app.created_by_display ||
                    "—"
                  }
                />
                <Row
                  term="Adhérent CBS"
                  value={app.cbs_refs.client_adherent_id || "—"}
                />
                <Row
                  term="Agence"
                  value={app.agency_display || "—"}
                />
              </dl>
              {!!app.cbs_refs.warnings?.length && <div className="form-error"><strong>Correspondances à compléter avant mise en place</strong><ul>{app.cbs_refs.warnings.map((message) => <li key={message}>{message}</li>)}</ul></div>}
            </details>
          )}
          {(app.cbs_demande_number ||
            app.cbs_demande_ref ||
            app.cbs_contract_number ||
            app.cbs_operation_date) && (
            <SubSection icon={Cable} title="Références CBS (mise en place)">
              <dl className="def-list two">
                <Row
                  term="N° demande (numDemande)"
                  value={app.cbs_demande_number || "—"}
                />
                <Row
                  term="Réf. demande (refDemande)"
                  value={app.cbs_demande_ref || "—"}
                />
                <Row
                  term="N° contrat (numContrat)"
                  value={app.cbs_contract_number || "—"}
                />
                <Row
                  term="Date opération"
                  value={
                    app.cbs_operation_date
                      ? formatDate(app.cbs_operation_date)
                      : "—"
                  }
                />
              </dl>
            </SubSection>
          )}
          {app.fees_breakdown && app.fees_breakdown.lines.length > 0 && (
            <SubSection icon={Wallet} title="Frais">
              <p className="muted small" style={{ marginTop: 0 }}>
                Les % s’appliquent sur le montant de référence
                {app.fees_breakdown.base_amount
                  ? ` (${formatMoney(app.fees_breakdown.base_amount, cur)})`
                  : ""}
                . À la mise en place, Fin Flow envoie le{" "}
                <strong>montant accordé</strong> ; les prélèvements relèvent du CBS. Vérifier la concordance des frais avec ses conditions avant mise en place.
              </p>
              <div className="fees-breakdown">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Intitulé</th>
                      <th>Base</th>
                      <th className="num">Montant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {app.fees_breakdown.lines.map((line, idx) => (
                      <tr key={line.id || `fee-${idx}`}>
                        <td>{line.label}{line.tax_amount != null && Number(line.tax_amount) > 0 && <span className="muted small"> · dont taxe {formatMoney(line.tax_amount, cur)}</span>}</td>
                        <td>
                          {line.mode === "PERCENT"
                            ? `${line.value} %`
                            : formatMoney(line.value, cur)}
                        </td>
                        <td className="num">
                          {line.amount != null
                            ? formatMoney(line.amount, cur)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  {(app.fees_breakdown.total != null ||
                    app.fees_breakdown.net_after_fees != null) && (
                    <tfoot>
                      {app.fees_breakdown.total != null && (
                        <tr>
                          <td colSpan={2}>
                            <strong>Total des frais{app.pricing_quote?.engine === "CONFIGURED" ? ", taxes sur frais comprises" : ""}</strong>
                          </td>
                          <td className="num">
                            <strong>
                              {formatMoney(app.fees_breakdown.total, cur)}
                            </strong>
                          </td>
                        </tr>
                      )}
                      {app.fees_breakdown.net_after_fees != null && (
                        <tr>
                          <td colSpan={2}>
                            Net indicatif après frais (CBS)
                          </td>
                          <td className="num">
                            {formatMoney(app.fees_breakdown.net_after_fees, cur)}
                          </td>
                        </tr>
                      )}
                    </tfoot>
                  )}
                </table>
              </div>
            </SubSection>
          )}
          {(Number(app.project_total_cost) > 0 ||
            Number(app.personal_contribution) > 0 ||
            app.financed_quota) && (
            <SubSection icon={Wallet} title="Plan de financement">
              <dl className="def-list two">
                <Row
                  term="Coût total du projet"
                  value={Number(app.project_total_cost) > 0 ? formatMoney(app.project_total_cost!, cur) : undefined}
                />
                <Row
                  term="Apport personnel"
                  value={Number(app.personal_contribution) > 0 ? formatMoney(app.personal_contribution!, cur) : undefined}
                />
                <Row term="Quotité financée" value={app.financed_quota ? `${Number(app.financed_quota).toFixed(1)} %` : undefined} />
              </dl>
            </SubSection>
          )}
          {app.purpose && (
            <SubSection icon={FileText} title="Détails de la demande">
              <p className="prose">{app.purpose}</p>
            </SubSection>
          )}
          {app.request_letter_scan && (
            <div className="doc-row">
              <a className="doc-chip" href={app.request_letter_scan} target="_blank" rel="noreferrer">
                <FileText size={15} />
                Lettre de demande
              </a>
            </div>
          )}
          </ViewSection>

          <FinancialAnalysesSection
            analyses={analyses}
            currency={cur}
            appId={app.id}
            canContribute={canContributeAnalysis}
            loading={financialLoading}
            error={financialError}
            onRetry={() => void refetchFinancials()}
          />

          {hasPerm(user, "credits.view_creditexposureobservation") && <ViewSection
            id="sec-exposure"
            icon={Wallet}
            title="Engagements et relations économiques"
            description="Endettement global du client et relations économiques déclarées."
          >
            <CreditExposurePanel key={app.id} applicationId={app.id} clientId={app.client} currency={app.currency} />
          </ViewSection>}

          {showActivity && (
          <ViewSection
            id="sec-activity"
            icon={Store}
            title="Activité et environnement commercial"
          >
          <dl className="def-list two">
            <Row term="Date de création" value={app.activity_start_date && formatDate(app.activity_start_date)} />
            <Row term="Adresse exacte" value={app.exact_address} />
            <Row term="Clientèle" value={app.clientele} />
            <Row term="Régime fiscal" value={app.tax_regime && lbl(CREDIT_LABELS.tax_regime, app.tax_regime)} />
            <Row term="Délai paiement clients" value={app.avg_client_payment_days != null ? `${app.avg_client_payment_days} j` : undefined} />
            <Row term="Délai paiement fournisseurs" value={app.avg_supplier_payment_days != null ? `${app.avg_supplier_payment_days} j` : undefined} />
            <Row term="Zone de chalandise" value={app.catchment_area && lbl(CREDIT_LABELS.catchment_area, app.catchment_area)} />
          </dl>
          {app.stock_photos && app.stock_photos.length > 0 && (
            <SubSection icon={Store} title="Photos du stock">
              <div className="photo-gallery">
                {app.stock_photos.map((p) => (
                  <a key={p.id} href={p.image} target="_blank" rel="noreferrer">
                    <img src={p.image} alt={p.caption || "Photo du stock"} />
                  </a>
                ))}
              </div>
            </SubSection>
          )}
          </ViewSection>
          )}

          <ViewSection
            id="sec-patrimoine"
            icon={Landmark}
            title="Patrimoine, garanties et cautions"
            description="Piliers collatéral d'instruction : garanties réelles et cautions."
          >
          <CollateralSummaryCard
            applicationId={app.id}
            currency={cur}
            embedded
          />
          <dl className="def-list two">
            <Row term="Occupation des locaux" value={app.premises_status && lbl(CREDIT_LABELS.premises_status, app.premises_status)} />
          </dl>

          <SubSection icon={ShieldCheck} title="Garanties">
            {canAttachCollateral && canAddGuarantee && (
              <RenewGuaranteesPanel
                applicationId={id!}
                currency={cur}
                enabled={!!id && canAttachCollateral && canAddGuarantee}
              />
            )}
            {guarantees && guarantees.results.length > 0 ? (
              <ul className="link-list">
                {guarantees.results.map((g) => (
                  <li
                    key={g.id}
                    className={canViewGuarantees ? "row-clickable" : undefined}
                    onClick={
                      canViewGuarantees
                        ? () => navigate(`/dossiers/${id}/garanties/${g.id}`)
                        : undefined
                    }
                  >
                    <span>
                      <ShieldCheck size={14} /> {g.type_display}
                      {g.guarantee_type === "PLEDGE" && g.pledge_category && (
                        <em className="muted small">
                          {" "}
                          — {GUARANTEE_LABELS.pledge_category[g.pledge_category]}
                        </em>
                      )}
                      {describeGuarantee(g) && (
                        <em className="muted small"> · {describeGuarantee(g)}</em>
                      )}
                      {g.renewed_from_reference && (
                        <em className="muted small">
                          {" "}
                          · reconduite depuis {g.renewed_from_reference}
                        </em>
                      )}
                      {g.belongs_to_applicant === false && (
                        <em className="muted small">
                          {" "}
                          · bien hors client
                          {g.surety_display ? ` (${g.surety_display})` : ""}
                        </em>
                      )}
                    </span>
                    <span className="muted">
                      {formatMoney(g.current_value, cur)}
                      {g.guarantee_type === "MORTGAGE" && g.ltv_ratio && (
                        <> · Couverture {(Number(g.ltv_ratio) * 100).toFixed(0)} %</>
                      )}
                    </span>
                    <Badge value={g.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">Aucune garantie rattachée.</p>
            )}
            {(guaranteeTotal > 0 || excludedGuaranteeCount > 0) && (
              <div className="finance-recap" style={{ marginTop: 10 }}>
                <div className="recap-item">
                  <span className="recap-label">Valeur des garanties actives</span>
                  <span className="recap-value">{formatMoney(guaranteeTotal, cur)}</span>
                </div>
                {coveragePct !== null && (
                  <div className={`recap-item${coveragePct >= 100 ? " strong" : ""}`}>
                    <span className="recap-label">Taux de couverture</span>
                    <span className="recap-value">{coveragePct.toFixed(0)} %</span>
                  </div>
                )}
                {excludedGuaranteeCount > 0 && (
                  <p className="muted small" style={{ marginTop: 6 }}>
                    {excludedGuaranteeCount} garantie
                    {excludedGuaranteeCount > 1 ? "s" : ""} réalisée
                    {excludedGuaranteeCount > 1 ? "s" : ""}, levée
                    {excludedGuaranteeCount > 1 ? "s" : ""} ou transférée
                    {excludedGuaranteeCount > 1 ? "s" : ""} exclue
                    {excludedGuaranteeCount > 1 ? "s" : ""} du taux.
                  </p>
                )}
              </div>
            )}
            {canAttachCollateral && canAddGuarantee && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/dossiers/${id}/garanties/nouvelle`}
              >
                <Plus size={15} />
                Ajouter une garantie
              </Link>
            )}
          </SubSection>

          <SubSection icon={HandCoins} title="Cautions">
            {engagements && engagements.results.length > 0 ? (
              <ul className="link-list stacked">
                {engagements.results.map((e) => (
                  <li
                    key={e.id}
                    style={{ flexDirection: "column", alignItems: "stretch" }}
                  >
                    <div
                      className={canViewSureties ? "row-clickable" : undefined}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 12,
                        cursor: canViewSureties ? "pointer" : "default",
                      }}
                      onClick={
                        canViewSureties
                          ? () =>
                              navigate(`/dossiers/${id}/cautions/${e.surety}`)
                          : undefined
                      }
                    >
                      <span>
                        <HandCoins size={14} /> {e.surety_display}
                        {e.engagement_type_display ? (
                          <em className="muted small">
                            {" "}
                            · {e.engagement_type_display}
                          </em>
                        ) : null}
                      </span>
                      <Badge
                        value={e.status}
                        label={e.status_display || e.status}
                      />
                    </div>
                    <SuretyEngagementActions
                      engagement={e}
                      canManage={canManageSuretyEng}
                      canContracts={canAddContract}
                      currency={cur}
                      invalidateKeys={[
                        ["surety-engagements", id],
                        ["credit-application", id],
                        ["credit-readiness", id],
                        ["generated-contracts", id],
                      ]}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">Aucune caution rattachée.</p>
            )}
            {canAttachCollateral && canAddSurety && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/dossiers/${id}/cautions/nouvelle`}
              >
                <Plus size={15} />
                Ajouter une caution
              </Link>
            )}
          </SubSection>
          </ViewSection>

          {showAfterSales && (
          <ViewSection
            id="sec-aftersales"
            icon={Scale}
            title="Après-vente"
            description="Dations, formalisations et mains levées rattachées à ce dossier."
          >
            {canViewDations && dations && dations.results.length > 0 && (
              <SubSection icon={CircleDollarSign} title="Dations">
                <ul className="link-list">
                  {dations.results.map((d) => (
                    <li
                      key={d.id}
                      className="row-clickable"
                      onClick={() => navigate(`/dations/${d.id}`)}
                    >
                      <span>
                        <CircleDollarSign size={14} />{" "}
                        {d.reference || "Dation"}
                      </span>
                      <span className="muted small">
                        {formatDate(d.created_at)}
                      </span>
                      <Badge
                        value={d.status}
                        label={d.status_display || d.status}
                      />
                    </li>
                  ))}
                </ul>
              </SubSection>
            )}

            {canViewFormalizations &&
              formalizations &&
              formalizations.results.length > 0 && (
              <SubSection icon={FileSignature} title="Formalisations">
                <ul className="link-list">
                  {formalizations.results.map((f) => (
                    <li
                      key={f.id}
                      className="row-clickable"
                      onClick={() => navigate(`/formalisations/${f.id}`)}
                    >
                      <span>
                        <FileSignature size={14} />{" "}
                        {f.reference || "Formalisation"}
                        {f.guarantee_reference ? (
                          <em className="muted small">
                            {" "}
                            · {f.guarantee_reference}
                          </em>
                        ) : null}
                      </span>
                      <span className="muted small">
                        {f.legal_stage_display || f.legal_stage}
                      </span>
                      <Badge
                        value={f.status}
                        label={f.status_display || f.status}
                      />
                    </li>
                  ))}
                </ul>
              </SubSection>
            )}

            {canViewReleases && releases && releases.results.length > 0 && (
              <SubSection icon={Unlock} title="Mains levées">
                <ul className="link-list">
                  {releases.results.map((r) => (
                    <li
                      key={r.id}
                      className="row-clickable"
                      onClick={() => navigate(`/mains-levees/${r.id}`)}
                    >
                      <span>
                        <Unlock size={14} /> {r.reference || "Main levée"}
                        {r.guarantee_reference ? (
                          <em className="muted small">
                            {" "}
                            · {r.guarantee_reference}
                          </em>
                        ) : null}
                      </span>
                      <span className="muted small">
                        {formatDate(r.created_at)}
                      </span>
                      <Badge
                        value={r.status}
                        label={r.status_display || r.status}
                      />
                    </li>
                  ))}
                </ul>
              </SubSection>
            )}
          </ViewSection>
          )}

          {showRestructure && loan && (
          <ViewSection
            id="sec-restructure"
            icon={RefreshCw}
            title="Restructuration"
            description="Analyse d'une demande client ou interne. Perfect n'a pas d'API : l'échéancier CBS n'est pas modifié."
          >
            <RestructureRequestPanel
              origin="LOAN"
              loanId={loan.id}
              caseId={loan.collection_case_id}
              currency={loan.currency || cur}
              outstanding={loan.outstanding_principal}
              currentDuration={loan.duration_months}
              currentRate={loan.interest_rate}
              restructures={loan.restructures || []}
              canPropose={canProposeRestructure && loan.status === "ACTIVE"}
              canDecide={canDecideRestructure}
              frozen={loan.financial_ops_frozen}
              frozenReason={loan.financial_ops_frozen_reason}
              loanActive={loan.status === "ACTIVE"}
              currentUserId={uid}
              onChanged={() => {
                qc.invalidateQueries({ queryKey: ["loan", app.loan_id] });
                qc.invalidateQueries({ queryKey: ["credit-application", id] });
              }}
              onError={(msg) => setActionError(msg || null)}
              onSuccess={() => setActionError(null)}
            />
          </ViewSection>
          )}

          {showApplicant && (
          <ViewSection
            id="sec-applicant"
            icon={Briefcase}
            title="Demandeur & emploi"
          >
            <dl className="def-list two">
              <Row term="Employeur" value={app.employer_name} />
              <Row term="Type de contrat" value={app.contract_type && lbl(CREDIT_LABELS.contract_type, app.contract_type)} />
              <Row term="Personnes à charge" value={app.dependents_count ?? undefined} />
              <Row term="Domiciliation du salaire" value={app.salary_domiciliation ? "Oui" : undefined} />
            </dl>
          </ViewSection>
          )}

          {showBanking && (
          <ViewSection
            id="sec-banking"
            icon={History}
            title="Relation bancaire"
          >
            <dl className="def-list two">
              <Row term="Numéro de compte" value={app.client_account_number} />
              <Row term="Début de la relation" value={app.relationship_start_date && formatDate(app.relationship_start_date)} />
              <Row
                term="Mouvements créditeurs moyens"
                value={Number(app.avg_monthly_credit_movements) > 0 ? formatMoney(app.avg_monthly_credit_movements!, cur) : undefined}
              />
            </dl>
          </ViewSection>
          )}

          {showInsurance && (
          <ViewSection id="sec-insurance" icon={ShieldCheck} title="Assurance">
            <dl className="def-list two">
              <Row term="Assurance décès-invalidité (ADI)" value={app.has_credit_insurance ? "Oui" : "Non"} />
              <Row term="Compagnie d'assurance" value={app.insurance_company} />
              <Row term="Numéro de police" value={app.insurance_policy_number} />
              <Row term="Fin de couverture" value={app.insurance_expiry_date ? formatDate(app.insurance_expiry_date) : undefined} />
              <Row
                term="Prime d'assurance"
                value={Number(app.insurance_premium) > 0 ? formatMoney(app.insurance_premium!, cur) : undefined}
              />
            </dl>
          </ViewSection>
          )}

          {showSpecial && (
          <ViewSection
            id="sec-special"
            icon={NotebookPen}
            title="Conditions particulières"
          >
            {app.special_conditions && (
              <SubSection icon={NotebookPen} title="Conditions particulières">
                <p className="prose">{app.special_conditions}</p>
              </SubSection>
            )}
            {app.suspensive_conditions && (
              <SubSection icon={NotebookPen} title="Conditions suspensives">
                <p className="prose">{app.suspensive_conditions}</p>
              </SubSection>
            )}
          </ViewSection>
          )}

          {showCompliance && (
          <ViewSection
            id="sec-compliance"
            icon={ShieldCheck}
            title="Conformité (LBC-FT)"
          >
            <dl className="def-list two">
              <Row term="Bénéficiaire effectif" value={app.beneficial_owner} />
              <Row term="Origine des fonds / apport" value={app.funds_origin} />
              <Row term="Personne politiquement exposée (PPE)" value={app.is_pep ? "Oui" : undefined} />
            </dl>
          </ViewSection>
          )}

          {schedule && (
          <ViewSection
            id="sec-schedule"
            icon={CalendarClock}
            title="Échéancier prévisionnel"
          >
            <div className="metric-grid">
              <Metric
                label={`Échéance institution (${schedule.periodLabel})`}
                value={formatMoney(schedule.installment, cur)}
              />
              <Metric label="Nombre d'échéances" value={schedule.count} />
              <Metric label="Intérêts totaux" value={formatMoney(schedule.totalInterest, cur)} />
              {schedule.hasSavings && (
                <Metric label="Épargne totale" value={formatMoney(schedule.totalSavings, cur)} />
              )}
              <Metric label="Total à rembourser" value={formatMoney(schedule.totalRepayment, cur)} />
            </div>
            <p className="muted small">
              Simulation à échéances constantes (taux annuel réparti selon la
              périodicité) sur la base du montant{" "}
              {app.amount_proposed ? "proposé" : "demandé"}. Les échéances tombant
              un week-end sont reportées au lundi. L'échéancier définitif est
              généré à la mise en place.
            </p>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setShowSchedule((v) => !v)}
            >
              <CalendarClock size={15} />
              {showSchedule
                ? "Masquer le tableau d'amortissement"
                : "Voir le tableau d'amortissement"}
            </button>
            {showSchedule && (
              <div className="table-scroll" style={{ marginTop: 12 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>N°</th>
                      <th>Date</th>
                      <th className="num">Capital</th>
                      <th className="num">Intérêt</th>
                      {schedule.hasSavings && <th className="num">Épargne</th>}
                      <th className="num">Montant échéance</th>
                      <th className="num">Capital restant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedule.rows.map((row) => (
                      <tr key={row.number}>
                        <td>{row.number}</td>
                        <td>{formatDate(row.dueDate)}</td>
                        <td className="num">{formatMoney(row.principal, cur)}</td>
                        <td className="num">{formatMoney(row.interest, cur)}</td>
                        {schedule.hasSavings && (
                          <td className="num">{formatMoney(row.savings, cur)}</td>
                        )}
                        <td className="num">{formatMoney(row.total, cur)}</td>
                        <td className="num">{formatMoney(row.balance, cur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </ViewSection>
          )}

          <FieldVisitsCard appId={app.id} canAdd={canContributeVisit} />

          {hasChecklist && (
          <ViewSection
            id="sec-checklist"
            icon={ClipboardList}
            title="Pièces du dossier"
          >
            <div className="checklist-badges">
              {app.document_checklist.map((item, idx) => {
                const scan = app.documents?.find(
                  (d) => d.label === item.label,
                );
                return scan ? (
                  <a
                    key={`${item.label}-${idx}`}
                    className="doc-badge ok as-link"
                    href={scan.file}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Check size={13} />
                    {item.label}
                    <Paperclip size={12} />
                  </a>
                ) : (
                  <span
                    key={`${item.label}-${idx}`}
                    className={`doc-badge ${item.provided ? "ok" : "missing"}`}
                  >
                    {item.provided ? <Check size={13} /> : <X size={13} />}
                    {item.label}
                  </span>
                );
              })}
            </div>
          </ViewSection>
          )}

          <ViewSection
            id="sec-documents"
            icon={Paperclip}
            title="Documents du dossier"
          >
          <SubSection icon={FileText} title="Dossier de prêt">
            {app.request_letter_scan || (app.stock_photos?.length ?? 0) > 0 ? (
              <>
                <div className="doc-row">
                  {app.request_letter_scan && (
                    <DocLink
                      label="Lettre de demande"
                      url={app.request_letter_scan}
                    />
                  )}
                </div>
                {app.stock_photos && app.stock_photos.length > 0 && (
                  <div className="photo-gallery" style={{ marginTop: 10 }}>
                    {app.stock_photos.map((p) => (
                      <a key={p.id} href={p.image} target="_blank" rel="noreferrer">
                        <img src={p.image} alt={p.caption || "Photo du stock"} />
                      </a>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="muted small">Aucun document.</p>
            )}
          </SubSection>

          {client && clientDocs(client).length > 0 && (
            <SubSection icon={UserRound} title={`Client — ${client.display_name}`}>
              <div className="doc-row">
                {clientDocs(client).map((d) => (
                  <DocLink key={d.label} label={d.label} url={d.url} />
                ))}
              </div>
            </SubSection>
          )}

          {guarantees?.results.map((g) => {
            const docs = guaranteeDocs(g);
            const photos = g.photos ?? [];
            if (docs.length === 0 && photos.length === 0) return null;
            return (
              <SubSection
                key={g.id}
                icon={ShieldCheck}
                title={`Garantie — ${g.type_display}`}
              >
                <div className="doc-row">
                  {docs.map((d) => (
                    <DocLink key={d.label} label={d.label} url={d.url} />
                  ))}
                  {canViewGuarantees && (
                    <Link
                      className="doc-chip ghost"
                      to={`/dossiers/${id}/garanties/${g.id}`}
                    >
                      <ShieldCheck size={15} />
                      Voir la garantie
                    </Link>
                  )}
                </div>
                {photos.length > 0 && (
                  <div className="photo-gallery" style={{ marginTop: 10 }}>
                    {photos.map((p) => (
                      <a key={p.id} href={p.image} target="_blank" rel="noreferrer">
                        <img src={p.image} alt={p.caption || "Photo"} />
                      </a>
                    ))}
                  </div>
                )}
              </SubSection>
            );
          })}

          {engagements?.results.map((e) => {
            const docs: DocItem[] = [];
            if (e.surety_id_document_scan)
              docs.push({
                label: "Pièce d'identité",
                url: e.surety_id_document_scan,
              });
            if (e.surety_photo)
              docs.push({ label: "Photo", url: e.surety_photo });
            if (docs.length === 0) return null;
            return (
              <SubSection
                key={e.id}
                icon={HandCoins}
                title={`Caution — ${e.surety_display}`}
              >
                <div className="doc-row">
                  {docs.map((d) => (
                    <DocLink key={d.label} label={d.label} url={d.url} />
                  ))}
                </div>
              </SubSection>
            );
          })}
          </ViewSection>

          {showContracts && (
            <ContractsSection
              appId={app.id}
              canGenerate={canGenerateContracts}
            />
          )}

          <ViewSection
            id="sec-workflow"
            icon={GitBranch}
            title="Circuit d'approbation"
          >
          {!hasPerm(user, "workflow.view_workflowinstance") ? (
            <p className="muted small">Vous n'êtes pas habilité à consulter le détail du circuit.</p>
          ) : workflowLoading ? (
            <p className="muted small">Chargement du circuit…</p>
          ) : workflowError ? (
            <div role="alert"><p className="form-error">Impossible de charger le circuit d'approbation.</p><button type="button" className="btn btn-ghost btn-sm" onClick={() => void refetchWorkflow()}>Réessayer</button></div>
          ) : !instance ? (
            app.status === "DRAFT" ? <p className="muted small">Dossier non encore soumis.</p>
              : <p className="form-error" role="alert">Aucun historique de circuit disponible pour ce dossier au statut « {app.status_display || app.status} ». La traçabilité du circuit est à vérifier ; aucune étape de validation ne peut être déduite de ce seul statut.</p>
          ) : (
            <>
              <p className="muted small" style={{ marginTop: 0 }}>
                État :{" "}
                <Badge
                  value={instance.status}
                  label={
                    WORKFLOW_LABELS.instance_status[instance.status] ||
                    instance.status
                  }
                />
              </p>
              <ol className="workflow-steps">
                {instance.tasks.map((t) => (
                  <li key={t.id}>
                    <div className="workflow-step-line">
                      <span>{t.step_name}</span>
                      <Badge value={t.status} />
                      {t.opinion && (
                        <span className="muted small">
                          {" "}
                          · {t.opinion_display || WORKFLOW_LABELS.opinion[t.opinion]}
                        </span>
                      )}
                      {t.acted_by_display && (
                        <span className="muted small">
                          {" "}
                          par {t.acted_by_display}
                        </span>
                      )}
                      {t.proposed_amount && (
                        <span className="muted small">
                          {" "}
                          · montant proposé {formatMoney(t.proposed_amount, cur)}
                        </span>
                      )}
                    </div>
                    {t.decision_comment && (
                      <p className="workflow-step-comment">
                        « {t.decision_comment} »
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}
          </ViewSection>

          <ViewSection
            id="sec-timeline"
            icon={History}
            title="Historique & piste d'audit"
            description="Chronologie des évènements clés du dossier."
          >
            {!timeline || timeline.results.length === 0 ? (
              <p className="muted small">Aucun évènement enregistré.</p>
            ) : (
              <ul className="audit-timeline">
                {timeline.results.map((ev, i) => {
                  const tone = TIMELINE_TONE[ev.event] ?? "muted";
                  const label = TIMELINE_LABELS[ev.event] ?? ev.event;
                  return (
                    <li key={`${ev.timestamp}-${i}`} className="audit-item">
                      <span className={`audit-dot dot-${tone}`} />
                      <div className="audit-body">
                        <div className="audit-head">
                          <span className="audit-label">
                            {label}
                            {ev.step && (
                              <span className="muted"> · {ev.step}</span>
                            )}
                          </span>
                          <span className="audit-time">
                            {formatDate(ev.timestamp)}
                          </span>
                        </div>
                        <div className="audit-meta">
                          {ev.actor && <span>par {ev.actor}</span>}
                          {ev.opinion && (
                            <span>
                              {" "}
                              ·{" "}
                              {WORKFLOW_LABELS.opinion[ev.opinion] ?? ev.opinion}
                            </span>
                          )}
                        </div>
                        {ev.comment && (
                          <p className="audit-comment">« {ev.comment} »</p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </ViewSection>
        </div>
        </SectionCollapseContext.Provider>
      </div>
    </div>
  );
}
