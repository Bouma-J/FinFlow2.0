import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Building2,
  CalendarClock,
  ClipboardCheck,
  FileText,
  Layers,
  User,
  UserCircle,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { MyDossierRow, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm } from "@/auth/permissions";
import {
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_FORMALIZATIONS,
  PERM_RELEASES,
} from "@/auth/routePerms";
import {
  FilterField,
  FilterSelect,
  ListFilters,
  OfficerFilter,
  SearchInput,
  countActive,
} from "@/components/ListFilters";
import {
  Badge,
  DEFAULT_PAGE_SIZE,
  EmptyState,
  PageHeader,
  PaginationBar,
  QueryStatus,
  TenantScopeNotice,
  formatDate,
  formatMoney,
} from "@/components/ui";

const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

const MY_TASK_LABELS: Record<string, string> = {
  PENDING: "À traiter",
  APPROVED: "Traité (approuvé)",
  RETURNED: "Traité (retourné)",
  REJECTED: "Traité (rejeté)",
  SKIPPED: "Ignoré",
};

type StepOption = {
  value: string;
  label: string;
  step_name?: string;
  step_role?: string;
  order?: number | null;
};

type DossiersPage = Paginated<MyDossierRow> & {
  actionable_count?: number;
  treated_count?: number;
  visible_count?: number;
  step_options?: StepOption[];
  queue?: string;
};

type QueueFilter = "actionable" | "all" | "treated";

const TASK_STATUS_OPTIONS = [
  ["", "Tous (hors brouillon)"],
  ["IN_APPROVAL", "En cours d'approbation"],
  ["APPROVED", "Approuvé"],
  ["REJECTED", "Rejeté"],
  ["RETURNED", "Retourné"],
  ["COMPLETED", "Clôturé"],
  ["DISBURSED", "Mis en place"],
  ["CANCELLED", "Annulé"],
  ["BLOCKED", "Bloqué"],
] as const;

function taskHref(row: MyDossierRow): string {
  return row.detail_path || `/dossiers/${row.id}`;
}

function canOpenTask(user: ReturnType<typeof useAuth>["user"], href: string) {
  if (href.startsWith("/formalisations"))
    return hasAnyPerm(user, PERM_FORMALIZATIONS);
  if (href.startsWith("/dations")) return hasAnyPerm(user, PERM_DATIONS);
  if (href.startsWith("/mains-levees")) return hasAnyPerm(user, PERM_RELEASES);
  if (href.startsWith("/dossiers")) return hasAnyPerm(user, PERM_CREDITS);
  return true;
}

export function TasksPage() {
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [clientTypeFilter, setClientTypeFilter] = useState("");
  const [initiatorFilter, setInitiatorFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("actionable");
  const [stepFilter, setStepFilter] = useState("");

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      "my-dossiers",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      query,
      statusFilter,
      kindFilter,
      clientTypeFilter,
      initiatorFilter,
      dateFrom,
      dateTo,
      queueFilter,
      stepFilter,
    ],
    queryFn: async () =>
      (
        await api.get<DossiersPage>("/approval-tasks/my_dossiers/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            queue: queueFilter,
            ...(query.trim() ? { search: query.trim() } : {}),
            ...(statusFilter ? { status: statusFilter } : {}),
            ...(kindFilter ? { target_kind: kindFilter } : {}),
            ...(clientTypeFilter ? { client_type: clientTypeFilter } : {}),
            ...(initiatorFilter ? { gestionnaire: initiatorFilter } : {}),
            ...(dateFrom ? { created_after: dateFrom } : {}),
            ...(dateTo ? { created_before: dateTo } : {}),
            ...(stepFilter ? { step_role: stepFilter } : {}),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  const rows = data?.results ?? [];
  const actionableCount = data?.actionable_count ?? 0;
  const treatedCount = data?.treated_count ?? 0;
  const visibleCount = data?.visible_count ?? 0;
  const stepOptions = data?.step_options ?? [];

  const hasFilters =
    !!query ||
    !!statusFilter ||
    !!kindFilter ||
    !!clientTypeFilter ||
    !!initiatorFilter ||
    !!dateFrom ||
    !!dateTo ||
    !!stepFilter ||
    queueFilter !== "actionable";

  function resetFilters() {
    setQuery("");
    setStatusFilter("");
    setKindFilter("");
    setClientTypeFilter("");
    setInitiatorFilter("");
    setDateFrom("");
    setDateTo("");
    setStepFilter("");
    setQueueFilter("actionable");
    setPage(1);
  }

  return (
    <div className="page-shell page-shell--list">
      <div className="list-page-chrome">
        <PageHeader
          icon={ClipboardCheck}
          title="Mes validations"
          subtitle="Dossiers en circuit selon votre périmètre (file, agence ou dossiers soumis)"
        />
        {needsTenant && <TenantScopeNotice />}
        <ListFilters
          search={
            <SearchInput
              value={query}
              onChange={setFilter(setQuery)}
              placeholder="Référence, client, produit, initiateur, étape…"
            />
          }
          activeCount={countActive(
            query,
            statusFilter,
            kindFilter,
            clientTypeFilter,
            initiatorFilter,
            dateFrom,
            dateTo,
            stepFilter,
            queueFilter !== "actionable" ? queueFilter : "",
          )}
          onReset={resetFilters}
          extra={
            <span className="toolbar-count">
              {data?.count ?? rows.length} affiché(s) · {actionableCount} à
              traiter · {visibleCount} visible(s)
            </span>
          }
        >
          <FilterField label="File" active={queueFilter !== "actionable"}>
            <FilterSelect
              value={queueFilter}
              onChange={(v) => setFilter(setQueueFilter)(v as QueueFilter)}
            >
              <option value="actionable">
                À traiter ({actionableCount})
              </option>
              <option value="all">Tous les dossiers ({visibleCount})</option>
              <option value="treated">Déjà traités ({treatedCount})</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Étape du circuit" active={!!stepFilter}>
            <FilterSelect
              value={stepFilter}
              onChange={setFilter(setStepFilter)}
            >
              <option value="">Toutes les étapes</option>
              {stepOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Type de dossier" active={!!kindFilter}>
            <FilterSelect
              value={kindFilter}
              onChange={setFilter(setKindFilter)}
            >
              <option value="">Tous</option>
              <option value="CREDIT">Crédit</option>
              <option value="MAIN_LEVEE">Main levée</option>
              <option value="DATION">Dation</option>
              <option value="FORMALISATION">Formalisation</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Statut" active={!!statusFilter}>
            <FilterSelect
              value={statusFilter}
              onChange={setFilter(setStatusFilter)}
            >
              {TASK_STATUS_OPTIONS.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Type de client" active={!!clientTypeFilter}>
            <FilterSelect
              value={clientTypeFilter}
              onChange={setFilter(setClientTypeFilter)}
            >
              <option value="">Tous</option>
              <option value="particulier">Particulier</option>
              <option value="groupement">Groupement</option>
              <option value="entreprise">Entreprise</option>
            </FilterSelect>
          </FilterField>
          <OfficerFilter
            value={initiatorFilter}
            onChange={setFilter(setInitiatorFilter)}
          />
          <FilterField label="Créé du" active={!!dateFrom}>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setFilter(setDateFrom)(e.target.value)}
            />
          </FilterField>
          <FilterField label="au" active={!!dateTo}>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setFilter(setDateTo)(e.target.value)}
            />
          </FilterField>
        </ListFilters>
      </div>

      <div className="list-table-region">
        <QueryStatus
          isLoading={isLoading}
          isError={isError}
          isEmpty={!hasFilters && rows.length === 0}
          emptyMessage="Aucun dossier en circuit pour votre périmètre."
          onRetry={() => refetch()}
        >
          <>
            <div className="table-scroll table-scroll--fill list-scroll--cards">
              {rows.length === 0 ? (
                <EmptyState message="Aucun dossier ne correspond à vos critères." />
              ) : (
                <div className="valid-grid">
                  {rows.map((r) => {
                    const overdue =
                      r.is_actionable &&
                      !!r.my_task_due_at &&
                      new Date(r.my_task_due_at) < new Date();
                    const href = taskHref(r);
                    const openable = canOpenTask(user, href);
                    const cardClass = `valid-card${r.is_actionable ? " is-actionable" : ""}${
                      overdue ? " is-overdue" : ""
                    }`;
                    const stepLabel =
                      r.current_step_label ||
                      r.current_step_role ||
                      r.current_step_name ||
                      r.definition_name;
                    const body = (
                      <>
                        <div className="valid-card-top">
                          <span className="valid-ref">
                            <FileText size={15} />
                            {r.reference || "—"}
                          </span>
                          <Badge value={r.status} label={r.status_display} />
                        </div>

                        <div className="valid-client">
                          {r.client_type === "INDIVIDUAL" ? (
                            <User size={14} />
                          ) : (
                            <Building2 size={14} />
                          )}
                          {r.client_display}
                        </div>

                        <div className="valid-amount">
                          {formatMoney(
                            r.amount_proposed || r.amount_requested,
                            r.currency || "XOF",
                          )}
                          <small>
                            {r.amount_proposed
                              ? r.product_label || "Montant proposé"
                              : r.product_label || "Montant demandé"}
                          </small>
                        </div>

                        <div className="valid-meta">
                          <span className="valid-chip valid-chip-step">
                            <Layers />
                            Étape : {stepLabel || "—"}
                          </span>
                          {r.created_by_display && (
                            <span className="valid-chip">
                              <UserCircle />
                              {r.created_by_display}
                            </span>
                          )}
                          {r.created_at && (
                            <span className="valid-chip">
                              <CalendarClock />
                              {formatDate(r.created_at)}
                            </span>
                          )}
                        </div>

                        <div className="valid-card-foot">
                          {r.my_task_status ? (
                            <Badge
                              value={r.is_actionable ? "PENDING" : "APPROVED"}
                              label={
                                MY_TASK_LABELS[r.my_task_status] ??
                                r.my_task_status
                              }
                            />
                          ) : (
                            <Badge value="SUBMITTED" label="En circuit" />
                          )}
                          {openable && (
                            <span className="valid-open">
                              Ouvrir le dossier
                              <ArrowRight size={16} />
                            </span>
                          )}
                        </div>
                      </>
                    );
                    return openable ? (
                      <Link
                        key={`${r.target_kind || "CREDIT"}-${r.id}`}
                        to={href}
                        className={cardClass}
                      >
                        {body}
                      </Link>
                    ) : (
                      <div
                        key={`${r.target_kind || "CREDIT"}-${r.id}`}
                        className={cardClass}
                      >
                        {body}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <PaginationBar
              page={page}
              count={data?.count ?? 0}
              pageSize={LIST_PAGE_SIZE}
              onPageChange={setPage}
            />
          </>
        </QueryStatus>
      </div>
    </div>
  );
}
