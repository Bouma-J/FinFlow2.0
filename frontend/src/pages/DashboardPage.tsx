import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  Banknote,
  Building2,
  ClipboardCheck,
  Clock,
  FilePlus2,
  FileSignature,
  FileText,
  Filter,
  Handshake,
  LayoutDashboard,
  Percent,
  RotateCcw,
  Scale,
  ServerCrash,
  Shield,
  ShieldAlert,
  UserRound,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { DashboardData } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import {
  PERM_AFTER_SALES,
  PERM_CLIENTS,
  PERM_COLLECTIONS,
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_FORMALIZATIONS,
  PERM_GUARANTEES,
  PERM_RELEASES,
  PERM_TASKS,
} from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import {
  AgencyFilter,
  CREDIT_STATUS_OPTIONS,
  FilterField,
  FilterSelect,
  ListFilters,
  OfficerFilter,
  ProductFilter,
  countActive,
} from "@/components/ListFilters";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatCard,
  formatMoney,
} from "@/components/ui";
import { useTenantBranding } from "@/hooks/useTenantBranding";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Brouillon",
  SUBMITTED: "Soumis",
  IN_APPROVAL: "En approbation",
  APPROVED: "Approuvé",
  REJECTED: "Rejeté",
  RETURNED: "Retourné",
  CONTRACT_GENERATED: "Contrat généré",
  DISBURSEMENT_PENDING: "Transmission au CBS en attente",
  DISBURSED: "Mis en place",
  CLOSED: "Clôturé",
  CANCELLED: "Annulé",
};

const STATUS_TONE: Record<string, string> = {
  APPROVED: "success",
  DISBURSED: "success",
  CONTRACT_GENERATED: "success",
  DISBURSEMENT_PENDING: "warning",
  REJECTED: "danger",
  RETURNED: "warning",
  IN_APPROVAL: "info",
  SUBMITTED: "info",
  DRAFT: "muted",
  CANCELLED: "muted",
  CLOSED: "muted",
};

const CLIENT_TYPE_LABELS: Record<string, string> = {
  INDIVIDUAL: "Particuliers",
  PROFESSIONAL: "Groupements",
  CORPORATE: "Entreprises",
};

const PAR_LABELS: Record<string, string> = {
  PAR0: "Sain (PAR 0)",
  PAR1_30: "PAR 1-30 j",
  PAR31_90: "PAR 31-90 j",
  PAR91_180: "PAR 91-180 j",
  PAR180_PLUS: "PAR > 180 j",
};

const STAGE_LABELS: Record<string, string> = {
  AMICABLE: "Amiable",
  PRECONTENTIOUS: "Précontentieux",
  LITIGATION: "Contentieux",
  CLOSED: "Clôturé",
};

const STAGE_TONE: Record<string, string> = {
  AMICABLE: "info",
  PRECONTENTIOUS: "warning",
  LITIGATION: "danger",
  CLOSED: "muted",
};

type DashFilters = {
  date_from: string;
  date_to: string;
  agency: string;
  gestionnaire: string;
  status: string;
  product: string;
  client_type: string;
};

const EMPTY_FILTERS: DashFilters = {
  date_from: "",
  date_to: "",
  agency: "",
  gestionnaire: "",
  status: "",
  product: "",
  client_type: "",
};

function num(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  return typeof value === "string" ? Number(value) || 0 : value;
}

function compactMoney(value: string | number | null | undefined): string {
  const n = num(value);
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} Md`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} k`;
  return n.toLocaleString("fr-FR");
}

function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1)
    .toLocaleDateString("fr-FR", { month: "short" })
    .replace(".", "");
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function presetRange(key: string): Pick<DashFilters, "date_from" | "date_to"> {
  const today = new Date();
  const to = isoDate(today);
  if (key === "7d") {
    const from = new Date(today);
    from.setDate(from.getDate() - 6);
    return { date_from: isoDate(from), date_to: to };
  }
  if (key === "30d") {
    const from = new Date(today);
    from.setDate(from.getDate() - 29);
    return { date_from: isoDate(from), date_to: to };
  }
  if (key === "month") {
    return {
      date_from: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
      date_to: to,
    };
  }
  if (key === "year") {
    return {
      date_from: isoDate(new Date(today.getFullYear(), 0, 1)),
      date_to: to,
    };
  }
  return { date_from: "", date_to: "" };
}

function isPresetActive(filters: DashFilters, key: string): boolean {
  const range = presetRange(key);
  return (
    filters.date_from === range.date_from && filters.date_to === range.date_to
  );
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Bonjour";
  if (h < 18) return "Bon après-midi";
  return "Bonsoir";
}

function TrendChart({ data }: { data: DashboardData["credits"]["monthly"] }) {
  const max = Math.max(1, ...data.map((d) => num(d.amount)));
  const totalCount = data.reduce((s, d) => s + d.count, 0);
  if (totalCount === 0)
    return <EmptyState message="Aucune activité sur la période." />;

  return (
    <div className="trend-chart">
      {data.map((d) => {
        const h = Math.round((num(d.amount) / max) * 100);
        return (
          <div className="trend-col" key={d.month}>
            <span className="trend-count">{d.count}</span>
            <div className="trend-bar-track">
              <div
                className="trend-bar"
                style={{ height: `${Math.max(h, 3)}%` }}
                title={`${monthLabel(d.month)} · ${d.count} dossier(s) · ${formatMoney(
                  d.amount,
                )}`}
              />
            </div>
            <span className="trend-label">{monthLabel(d.month)}</span>
          </div>
        );
      })}
    </div>
  );
}

function DistBars({
  rows,
  emptyMessage,
}: {
  rows: {
    label: string;
    count: number;
    amount?: string | number | null;
    tone?: string;
  }[];
  emptyMessage: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (rows.length === 0) return <EmptyState message={emptyMessage} />;
  return (
    <ul className="dist-bars">
      {rows.map((r) => (
        <li key={r.label}>
          <div className="dist-row">
            <span className="dist-label">{r.label}</span>
            <span className="dist-meta">
              {r.count}
              {r.amount != null ? ` · ${compactMoney(r.amount)}` : ""}
            </span>
          </div>
          <div className="dist-track">
            <div
              className={`dist-fill tone-${r.tone ?? "info"}`}
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function QuickAction({
  to,
  icon: Icon,
  label,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
}) {
  return (
    <Link to={to} className="quick-action">
      <span className="qa-icon">
        <Icon size={18} />
      </span>
      <span className="qa-label">{label}</span>
      <ArrowUpRight size={15} className="qa-arrow" />
    </Link>
  );
}

function KpiSection({
  title,
  children,
  link,
}: {
  title: string;
  children: ReactNode;
  link?: ReactNode;
}) {
  return (
    <section className="kpi-section">
      <h3 className="kpi-section-title">
        {title}
        {link}
      </h3>
      <div className="stat-grid dash-kpi-grid">{children}</div>
    </section>
  );
}

function kpiConsult({
  user,
  anyOf,
  to,
  state,
  label = "Consulter",
}: {
  user: ReturnType<typeof useAuth>["user"];
  anyOf: readonly string[];
  to: string;
  state?: unknown;
  label?: string;
}): ReactNode | undefined {
  if (!hasAnyPerm(user, anyOf)) return undefined;
  return (
    <PermLink
      user={user}
      anyOf={anyOf}
      to={to}
      state={state}
      className="stat-link"
      fallback={null}
    >
      {label} <ArrowUpRight size={12} />
    </PermLink>
  );
}

function FunnelStrip({
  funnel,
}: {
  funnel: NonNullable<DashboardData["credits"]["funnel"]>;
}) {
  const steps = [
    { label: "Soumis", value: funnel.submitted },
    { label: "En circuit", value: funnel.in_approval },
    { label: "Approuvés", value: funnel.approved },
    { label: "Mis en place", value: funnel.disbursed },
  ];
  const max = Math.max(1, ...steps.map((s) => s.value));
  return (
    <div className="dash-funnel">
      <div className="dash-funnel-steps">
        {steps.map((s) => (
          <div className="dash-funnel-step" key={s.label}>
            <span className="dash-funnel-value">{s.value}</span>
            <div className="dash-funnel-track">
              <div
                className="dash-funnel-fill"
                style={{ width: `${(s.value / max) * 100}%` }}
              />
            </div>
            <span className="dash-funnel-label">{s.label}</span>
          </div>
        ))}
      </div>
      <div className="dash-funnel-rates">
        <span>
          Taux d&apos;approbation{" "}
          <strong>
            {funnel.approval_rate_pct != null
              ? `${funnel.approval_rate_pct} %`
              : "—"}
          </strong>
          <span className="muted">
            {" "}
            · {funnel.rejected} rejetés · {funnel.returned} retournés
          </span>
        </span>
        <span>
          Taux de mise en place{" "}
          <strong>
            {funnel.disbursement_rate_pct != null
              ? `${funnel.disbursement_rate_pct} %`
              : "—"}
          </strong>
        </span>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { activeTenant, user } = useAuth();
  const { tenantName, tenantCode } = useTenantBranding();
  const [filters, setFilters] = useState<DashFilters>(EMPTY_FILTERS);

  const scope = user?.data_scope ?? "AGENCY";
  const isGroup = !!user?.is_group_level;
  const showOrgFilters = scope !== "OWN" || isGroup || !!user?.is_superuser;

  const queryParams = useMemo(() => {
    const p: Record<string, string> = { live: "1" };
    if (activeTenant) p.tenant = activeTenant;
    (Object.keys(filters) as (keyof DashFilters)[]).forEach((k) => {
      if (filters[k]) p[k] = filters[k];
    });
    return p;
  }, [activeTenant, filters]);

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ["dashboard", queryParams],
    queryFn: async () =>
      (
        await api.get<DashboardData>("/reporting/dashboard/", {
          params: queryParams,
        })
      ).data,
  });

  const setFilter = <K extends keyof DashFilters>(key: K, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const resetFilters = () => setFilters(EMPTY_FILTERS);
  const activeFilterCount = countActive(
    filters.date_from,
    filters.date_to,
    filters.agency,
    filters.gestionnaire,
    filters.status,
    filters.product,
    filters.client_type,
  );

  const outstanding = num(data?.portfolio.outstanding);
  const overdue = num(data?.risk.total_overdue);
  const parRatio =
    outstanding + overdue > 0
      ? (overdue / (outstanding + overdue)) * 100
      : null;
  const s = data?.credits.summary;
  const scopeLabel = isGroup && !activeTenant
    ? "Vue consolidée Groupe"
    : tenantCode
      ? `${tenantCode} · ${tenantName}`
      : tenantName || "Fin Flow";

  return (
    <div className="page-shell dashboard-page">
      <PageHeader
        icon={LayoutDashboard}
        title={`${greeting()}, ${user?.first_name || user?.username || ""}`.trim()}
        subtitle={
          isGroup && !activeTenant
            ? `${scopeLabel} — synthèse multi-filiales`
            : `${scopeLabel} — pipeline, mises en place et risque de votre périmètre`
        }
        actions={
          <div className="dash-header-actions">
            {hasPerm(user, "credits.add_creditapplication") && (
              <QuickAction
                to="/dossiers/nouveau"
                icon={FilePlus2}
                label="Nouveau dossier"
              />
            )}
            {hasAnyPerm(user, PERM_TASKS) && (
              <QuickAction
                to="/taches"
                icon={ClipboardCheck}
                label="Mes validations"
              />
            )}
            {hasAnyPerm(user, PERM_AFTER_SALES) && (
              <QuickAction
                to="/apres-vente"
                icon={Handshake}
                label="Après-vente"
              />
            )}
          </div>
        }
      />

      <div className="dash-presets" aria-label="Périodes">
        {(
          [
            ["7d", "7 jours"],
            ["30d", "30 jours"],
            ["month", "Mois en cours"],
            ["year", "Année"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`dash-chip${isPresetActive(filters, key) ? " is-active" : ""}`}
            onClick={() =>
              setFilters((prev) => ({ ...prev, ...presetRange(key) }))
            }
          >
            {label}
          </button>
        ))}
        {isFetching && <span className="dash-live">Mise à jour…</span>}
      </div>

      <ListFilters
        extra={
          scope === "OWN" && !isGroup ? (
            <p className="dash-scope-note">
              Périmètre « mes dossiers » : les indicateurs portent sur les
              dossiers que vous avez créés. L’agence d’un dossier est celle du
              gestionnaire au moment de la création.
            </p>
          ) : undefined
        }
        activeCount={activeFilterCount}
        onReset={resetFilters}
      >
        <FilterField label="Du" active={!!filters.date_from}>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => setFilter("date_from", e.target.value)}
          />
        </FilterField>
        <FilterField label="Au" active={!!filters.date_to}>
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => setFilter("date_to", e.target.value)}
          />
        </FilterField>
        {showOrgFilters && (
          <AgencyFilter
            value={filters.agency}
            onChange={(v) => setFilter("agency", v)}
          />
        )}
        {showOrgFilters && (
          <OfficerFilter
            value={filters.gestionnaire}
            onChange={(v) => setFilter("gestionnaire", v)}
          />
        )}
        <FilterField label="Statut" active={!!filters.status}>
          <FilterSelect
            value={filters.status}
            onChange={(v) => setFilter("status", v)}
          >
            {CREDIT_STATUS_OPTIONS.map(([value, label]) => (
              <option key={value || "all"} value={value}>
                {label}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
        <ProductFilter
          value={filters.product}
          onChange={(v) => setFilter("product", v)}
        />
        <FilterField label="Type de client" active={!!filters.client_type}>
          <FilterSelect
            value={filters.client_type}
            onChange={(v) => setFilter("client_type", v)}
          >
            <option value="">Tous les types</option>
            {Object.entries(CLIENT_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
      </ListFilters>

      {showOrgFilters && (
        <p className="dash-scope-note dash-agency-hint">
          L’agence d’un dossier est celle du gestionnaire qui le crée — pas une
          agence choisie à la main.
        </p>
      )}

      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <ErrorState
          message="Impossible de charger le tableau de bord."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {data.cbs && data.cbs.failed > 0 && (
            <div className="dash-cbs-banner" role="status">
              <ServerCrash size={16} />
              {data.cbs.failed} échec{data.cbs.failed > 1 ? "s" : ""} CBS
              <span className="muted">
                {data.cbs.pending} en attente · {data.cbs.retry} à rejouer
              </span>
            </div>
          )}

          {(hasAnyPerm(user, PERM_TASKS) ||
            (data.workflow?.conditions_pending ?? 0) > 0) && (
            <KpiSection
              title="File d'attente"
              link={
                hasAnyPerm(user, PERM_TASKS) ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_TASKS}
                    to="/taches"
                    className="kpi-section-link"
                    fallback={null}
                  >
                    Ouvrir <ArrowUpRight size={14} />
                  </PermLink>
                ) : undefined
              }
            >
              <StatCard
                icon={ClipboardCheck}
                label="Mes tâches"
                value={data.workflow?.my_pending_tasks ?? 0}
                tone={
                  (data.workflow?.my_pending_tasks ?? 0) > 0
                    ? "warning"
                    : "default"
                }
                hint={
                  (data.workflow?.my_overdue_tasks ?? 0) > 0
                    ? `${data.workflow?.my_overdue_tasks} en retard SLA`
                    : "À valider"
                }
                action={kpiConsult({ user, anyOf: PERM_TASKS, to: "/taches" })}
              />
              <StatCard
                icon={AlertTriangle}
                label="Mes retards SLA"
                value={data.workflow?.my_overdue_tasks ?? 0}
                tone={
                  (data.workflow?.my_overdue_tasks ?? 0) > 0
                    ? "danger"
                    : "default"
                }
                action={kpiConsult({ user, anyOf: PERM_TASKS, to: "/taches" })}
              />
              <StatCard
                icon={Filter}
                label="Réserves"
                value={data.workflow?.conditions_pending ?? 0}
                tone={
                  (data.workflow?.conditions_pending ?? 0) > 0
                    ? "warning"
                    : "default"
                }
                hint="Conditions d'approbation"
                action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=IN_APPROVAL" })}
              />
              <StatCard
                icon={Clock}
                label="Tâches périmètre"
                value={data.workflow?.pending_tasks ?? 0}
                hint={
                  (data.workflow?.overdue_tasks ?? 0) > 0
                    ? `${data.workflow?.overdue_tasks} en retard`
                    : "En attente"
                }
                tone={
                  (data.workflow?.overdue_tasks ?? 0) > 0 ? "danger" : "default"
                }
                action={kpiConsult({ user, anyOf: PERM_TASKS, to: "/taches" })}
              />
            </KpiSection>
          )}

          <KpiSection title="Pipeline crédit">
            <StatCard
              icon={FileText}
              label="Dossiers"
              value={s?.total ?? 0}
              hint={`${s?.pending_count ?? 0} en instruction`}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers" })}
            />
            <StatCard
              icon={Clock}
              label="En approbation"
              value={s?.in_approval_count ?? 0}
              tone="warning"
              hint={`${formatMoney(s?.amount_requested ?? null)} demandés`}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=IN_APPROVAL" })}
            />
            <StatCard
              icon={RotateCcw}
              label="Retournés"
              value={s?.returned_count ?? 0}
              tone={(s?.returned_count ?? 0) > 0 ? "warning" : "default"}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=RETURNED" })}
            />
            <StatCard
              icon={Banknote}
              label="À mettre en place"
              value={s?.disbursement_pending_count ?? 0}
              tone={
                (s?.disbursement_pending_count ?? 0) > 0 ? "warning" : "default"
              }
              hint={formatMoney(s?.disbursement_pending_amount ?? null)}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=DISBURSEMENT_PENDING" })}
            />
          </KpiSection>

          <KpiSection title="Portefeuille">
            <StatCard
              icon={Wallet}
              label="Mis en place"
              value={s?.disbursed_count ?? 0}
              hint={formatMoney(s?.disbursed_amount ?? null)}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=DISBURSED" })}
            />
            <StatCard
              icon={Banknote}
              label="Encours"
              value={compactMoney(data.portfolio.outstanding)}
              hint={`${data.portfolio.active_loans} prêt(s) actif(s)`}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/prets" })}
            />
            <StatCard
              icon={AlertTriangle}
              label="Échéances en retard"
              value={data.portfolio.overdue_installments}
              tone={
                data.portfolio.overdue_installments > 0 ? "danger" : "default"
              }
              hint={
                parRatio !== null
                  ? `PAR ${parRatio.toFixed(1)} % · ${formatMoney(overdue)}`
                  : undefined
              }
              action={kpiConsult({ user, anyOf: PERM_COLLECTIONS, to: "/recouvrement" })}
            />
            <StatCard
              icon={Scale}
              label="Recouvrement"
              value={data.risk.open_cases ?? 0}
              tone={
                (data.risk.followups_due ?? 0) > 0 ? "warning" : "default"
              }
              hint={
                (data.risk.followups_due ?? 0) > 0
                  ? `${data.risk.followups_due} action(s) due(s)`
                  : "Dossiers ouverts"
              }
              action={kpiConsult({ user, anyOf: PERM_COLLECTIONS, to: "/recouvrement" })}
            />
          </KpiSection>

          {hasAnyPerm(user, PERM_COLLECTIONS) && (
            <KpiSection
              title="Recouvrement opérationnel"
              link={
                <PermLink
                  user={user}
                  anyOf={PERM_COLLECTIONS}
                  to="/recouvrement"
                  className="kpi-section-link"
                  fallback={null}
                >
                  Ouvrir <ArrowUpRight size={14} />
                </PermLink>
              }
            >
              <StatCard
                icon={Clock}
                label="Actions dues"
                value={data.risk.followups_due ?? 0}
                tone={
                  (data.risk.followups_due ?? 0) > 0 ? "warning" : "default"
                }
                hint="Prochaine action ≤ aujourd'hui"
                action={kpiConsult({ user, anyOf: PERM_COLLECTIONS, to: "/recouvrement", state: { followupDue: true } })}
              />
              <StatCard
                icon={Handshake}
                label="Promesses en cours"
                value={data.risk.pending_promises ?? 0}
                action={kpiConsult({ user, anyOf: PERM_COLLECTIONS, to: "/recouvrement" })}
              />
              <StatCard
                icon={ShieldAlert}
                label="Promesses rompues"
                value={data.risk.broken_promises_30d ?? 0}
                tone={
                  (data.risk.broken_promises_30d ?? 0) > 0
                    ? "danger"
                    : "default"
                }
                hint="30 derniers jours"
                action={kpiConsult({ user, anyOf: PERM_COLLECTIONS, to: "/recouvrement", state: { brokenPromises: true } })}
              />
              <StatCard
                icon={AlertTriangle}
                label="Encours à risque"
                value={compactMoney(data.risk.total_overdue)}
                tone={num(data.risk.total_overdue) > 0 ? "danger" : "default"}
                action={kpiConsult({ user, anyOf: PERM_COLLECTIONS, to: "/recouvrement" })}
              />
            </KpiSection>
          )}

          {(() => {
            const as = data.after_sales;
            if (!as) return null;
            const cards: ReactNode[] = [];
            if (as.access.main_levee && as.main_levee && hasAnyPerm(user, PERM_RELEASES)) {
              cards.push(
                <StatCard
                  key="ml"
                  icon={Shield}
                  label="Mains levées"
                  value={as.main_levee.open}
                  hint={`${as.main_levee.in_approval} en circuit`}
                  tone={as.main_levee.in_approval > 0 ? "warning" : "default"}
                  action={kpiConsult({ user, anyOf: PERM_RELEASES, to: "/mains-levees" })}
                />,
              );
            }
            if (as.access.dation && as.dation && hasAnyPerm(user, PERM_DATIONS)) {
              cards.push(
                <StatCard
                  key="dt"
                  icon={FileSignature}
                  label="Dations"
                  value={as.dation.open}
                  hint={`${as.dation.in_approval} en circuit`}
                  tone={as.dation.in_approval > 0 ? "warning" : "default"}
                  action={kpiConsult({ user, anyOf: PERM_DATIONS, to: "/dations" })}
                />,
              );
            }
            if (
              as.access.formalisation &&
              as.formalisation &&
              hasAnyPerm(user, PERM_FORMALIZATIONS)
            ) {
              cards.push(
                <StatCard
                  key="fm"
                  icon={FileText}
                  label="Formalisations"
                  value={as.formalisation.open}
                  hint={`${as.formalisation.in_approval} en circuit`}
                  tone={
                    as.formalisation.in_approval > 0 ? "warning" : "default"
                  }
                  action={kpiConsult({ user, anyOf: PERM_FORMALIZATIONS, to: "/formalisations" })}
                />,
              );
            }
            if (cards.length === 0) return null;
            return (
              <KpiSection
                title="Après-vente"
                link={
                  <PermLink
                    user={user}
                    anyOf={PERM_AFTER_SALES}
                    to="/apres-vente"
                    className="kpi-section-link"
                    fallback={null}
                  >
                    Hub <ArrowUpRight size={14} />
                  </PermLink>
                }
              >
                {cards}
              </KpiSection>
            );
          })()}

          {(data.quality || data.credits.funnel) && (
            <KpiSection title="Conversion & qualité">
              {data.credits.funnel && (
                <StatCard
                  icon={Percent}
                  label="Taux d'approbation"
                  value={
                    data.credits.funnel.approval_rate_pct != null
                      ? `${data.credits.funnel.approval_rate_pct} %`
                      : "—"
                  }
                  hint={`${data.credits.funnel.approved} approuvés · ${data.credits.funnel.rejected} rejetés`}
                  action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers" })}
                />
              )}
              {data.credits.funnel && (
                <StatCard
                  icon={Wallet}
                  label="Taux de mise en place"
                  value={
                    data.credits.funnel.disbursement_rate_pct != null
                      ? `${data.credits.funnel.disbursement_rate_pct} %`
                      : "—"
                  }
                  hint={`${data.credits.funnel.disbursed} / ${data.credits.funnel.approved} approuvés`}
                  action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=DISBURSED" })}
                />
              )}
              {data.quality && hasAnyPerm(user, PERM_CLIENTS) && (
                <StatCard
                  icon={UserRound}
                  label="KYC en attente"
                  value={data.quality.kyc_pending}
                  tone={
                    data.quality.kyc_pending > 0 || data.quality.kyc_rejected > 0
                      ? "warning"
                      : "default"
                  }
                  hint={
                    data.quality.kyc_rejected > 0
                      ? `${data.quality.kyc_rejected} rejeté(s)`
                      : "Clients à valider"
                  }
                  action={kpiConsult({ user, anyOf: PERM_CLIENTS, to: "/clients?kyc_status=PENDING" })}
                />
              )}
              {data.quality && hasAnyPerm(user, PERM_GUARANTEES) && (
                <StatCard
                  icon={ShieldAlert}
                  label="Sans garantie active"
                  value={data.quality.pipeline_without_active_guarantee}
                  tone={
                    data.quality.pipeline_without_active_guarantee > 0
                      ? "warning"
                      : "default"
                  }
                  hint="Dossiers pipeline"
                  action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers" })}
                />
              )}
            </KpiSection>
          )}

          <KpiSection title="Volumes">
            {hasAnyPerm(user, PERM_CLIENTS) && (
              <StatCard
                icon={Users}
                label="Clients"
                value={data.clients.total}
                hint={
                  data.clients.new_period_label === "period"
                    ? `+${data.clients.new_this_month} sur la période`
                    : `+${data.clients.new_this_month} ce mois`
                }
                action={kpiConsult({ user, anyOf: PERM_CLIENTS, to: "/clients" })}
              />
            )}
            {hasAnyPerm(user, PERM_GUARANTEES) && (
              <StatCard
                icon={Shield}
                label="Garanties actives"
                value={data.guarantees.active_count ?? data.guarantees.count}
                hint={compactMoney(
                  data.guarantees.active_value ??
                    data.guarantees.total_current_value,
                )}
                action={kpiConsult({ user, anyOf: PERM_GUARANTEES, to: "/garanties" })}
              />
            )}
            {data.contracts && (
              <StatCard
                icon={FileSignature}
                label="Contrats"
                value={data.contracts.total}
                hint={`${data.contracts.signed} signés · ${data.contracts.generated} générés`}
                action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=CONTRACT_GENERATED" })}
              />
            )}
            <StatCard
              icon={ClipboardCheck}
              label="Approuvés"
              value={s?.approved_count ?? 0}
              tone="success"
              hint={formatMoney(s?.amount_approved ?? null)}
              action={kpiConsult({ user, anyOf: PERM_CREDITS, to: "/dossiers?status=APPROVED" })}
            />
          </KpiSection>

          <div className="dash-grid">
            <div className="dash-main">
              {data.credits.funnel && (
                <section className="card">
                  <div className="card-title">
                    <Percent size={18} />
                    Tunnel commercial
                  </div>
                  <div className="card-body">
                    <FunnelStrip funnel={data.credits.funnel} />
                  </div>
                </section>
              )}

              <section className="card">
                <div className="card-title">
                  <Clock size={18} />
                  Activité récente
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    to="/dossiers"
                    className="card-title-link"
                    fallback={null}
                  >
                    Voir tout <ArrowUpRight size={14} />
                  </PermLink>
                </div>
                <div className="card-body no-pad">
                  {data.credits.recent.length === 0 ? (
                    <div className="pad">
                      <EmptyState message="Aucun dossier récent." />
                    </div>
                  ) : (
                    <ul className="activity-list">
                      {data.credits.recent.map((r) => (
                        <li key={r.id}>
                          <PermLink
                            user={user}
                            anyOf={PERM_CREDITS}
                            to={`/dossiers/${r.id}`}
                            className="activity-row"
                          >
                            <span className="activity-avatar">
                              {(r.client || "?").slice(0, 1).toUpperCase()}
                            </span>
                            <span className="activity-info">
                              <span className="activity-client">{r.client}</span>
                              <span className="activity-meta">
                                {r.reference || "—"} · {r.product}
                                {r.agency && r.agency !== "—"
                                  ? ` · ${r.agency}`
                                  : ""}
                                {r.owner && r.owner !== "—"
                                  ? ` · ${r.owner}`
                                  : ""}
                              </span>
                            </span>
                            <span className="activity-amount">
                              {formatMoney(r.amount)}
                            </span>
                            <span
                              className={`badge badge-${
                                STATUS_TONE[r.status] ?? "muted"
                              }`}
                            >
                              {STATUS_LABELS[r.status] ?? r.status}
                            </span>
                          </PermLink>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>

              <section className="card">
                <div className="card-title">
                  <FileText size={18} />
                  Évolution des dossiers
                </div>
                <div className="card-body">
                  <TrendChart data={data.credits.monthly} />
                </div>
              </section>
            </div>

            <aside className="dash-side">
              <section className="card">
                <div className="card-title">
                  <Building2 size={18} />
                  Par agence
                </div>
                <div className="card-body">
                  <DistBars
                    emptyMessage="Aucun dossier rattaché à une agence."
                    rows={(data.credits.by_agency ?? []).map((a) => ({
                      label: a.agency,
                      count: a.count,
                      amount: a.amount,
                    }))}
                  />
                </div>
              </section>

              <section className="card">
                <div className="card-title">
                  <FileText size={18} />
                  Par statut
                </div>
                <div className="card-body">
                  <DistBars
                    emptyMessage="Aucun dossier."
                    rows={data.credits.by_status.map((row) => ({
                      label: STATUS_LABELS[row.status] ?? row.status,
                      count: row.count,
                      amount: row.amount,
                      tone: STATUS_TONE[row.status],
                    }))}
                  />
                </div>
              </section>

              <section className="card">
                <div className="card-title">
                  <Wallet size={18} />
                  Par produit
                </div>
                <div className="card-body">
                  <DistBars
                    emptyMessage="Aucun dossier par produit."
                    rows={data.credits.by_product.map((row) => ({
                      label: row.product || "—",
                      count: row.count,
                      amount: row.amount,
                    }))}
                  />
                </div>
              </section>

              {hasAnyPerm(user, PERM_CLIENTS) && (
                <section className="card">
                  <div className="card-title">
                    <Users size={18} />
                    Clientèle
                  </div>
                  <div className="card-body">
                    <DistBars
                      emptyMessage="Aucun client."
                      rows={data.clients.by_type.map((row) => ({
                        label:
                          CLIENT_TYPE_LABELS[row.client_type] ?? row.client_type,
                        count: row.count,
                      }))}
                    />
                  </div>
                </section>
              )}

              <section className="card">
                <div className="card-title">
                  <AlertTriangle size={18} />
                  Portefeuille à risque
                </div>
                <div className="card-body">
                  <DistBars
                    emptyMessage="Aucun encours à risque."
                    rows={data.risk.by_par_class.map((r) => ({
                      label: PAR_LABELS[r.par_class] ?? r.par_class,
                      count: r.count,
                      amount: r.amount,
                      tone: r.par_class === "PAR0" ? "success" : "danger",
                    }))}
                  />
                </div>
              </section>

              {hasAnyPerm(user, PERM_COLLECTIONS) &&
                (data.risk.by_stage?.length ?? 0) > 0 && (
                  <section className="card">
                    <div className="card-title">
                      <Scale size={18} />
                      Recouvrement par stade
                    </div>
                    <div className="card-body">
                      <DistBars
                        emptyMessage="Aucun dossier de recouvrement."
                        rows={(data.risk.by_stage ?? []).map((r) => ({
                          label: STAGE_LABELS[r.stage] ?? r.stage,
                          count: r.count,
                          amount: r.amount,
                          tone: STAGE_TONE[r.stage],
                        }))}
                      />
                    </div>
                  </section>
                )}
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
