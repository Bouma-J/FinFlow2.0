import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDollarSign, Download } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type {
  AgentCollectionDashboard,
  CollectionCase,
  CollectionTranche,
  HearingAgendaItem,
  Paginated,
  ParClass,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import { isFinflowAdmin, PERM_LITIGATION } from "@/auth/routePerms";
import {
  AgencyFilter,
  ClientFilterBanner,
  FilterField,
  FilterSelect,
  FilterToggle,
  ListFilters,
  OfficerFilter,
  ProductFilter,
  SearchInput,
  countActive,
  useClientSearchParam,
} from "@/components/ListFilters";
import {
  Badge,
  DEFAULT_PAGE_SIZE,
  PageHeader,
  PaginationBar,
  QueryStatus,
  TenantScopeNotice,
  formatMoney,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

const PAR_OPTIONS: { value: "" | ParClass; label: string }[] = [
  { value: "", label: "Toutes classes PAR" },
  { value: "PAR0", label: "Sain" },
  { value: "PAR1_30", label: "PAR 1-30" },
  { value: "PAR31_90", label: "PAR 31-90" },
  { value: "PAR91_180", label: "PAR 91-180" },
  { value: "PAR180_PLUS", label: "PAR > 180" },
];

const STAGE_OPTIONS = [
  { value: "", label: "Tous les stades" },
  { value: "AMICABLE", label: "Amiable" },
  { value: "PRECONTENTIOUS", label: "Précontentieux" },
  { value: "LITIGATION", label: "Contentieux" },
  { value: "CLOSED", label: "Clôturé" },
] as const;

const OWNER_OPTIONS = [
  { value: "", label: "Tous les responsables" },
  { value: "GESTIONNAIRE", label: "Gestionnaire" },
  { value: "COLLECTION", label: "Service recouvrement" },
  { value: "LEGAL", label: "Juridique" },
] as const;

export function CollectionsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { clientFilter, clearClientFilter } = useClientSearchParam();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const qc = useQueryClient();
  const canManageCase = hasPerm(user, "collections.change_collectioncase");
  const canViewLitigation = hasAnyPerm(user, PERM_LITIGATION);
  const canSeeTeamDash =
    hasPerm(user, "collections.view_collectioncase") &&
    (isFinflowAdmin(user) ||
      canManageCase ||
      Boolean(
        user?.capabilities?.includes("collection_broad_view"),
      ));
  const canRefreshCbs =
    isFinflowAdmin(user) ||
    Boolean(
      user?.capabilities?.includes("collection_officer"),
    );
  const [page, setPage] = useState(1);
  const [parClass, setParClass] = useState("");
  const [trancheId, setTrancheId] = useState("");
  const [stage, setStage] = useState("");
  const [agency, setAgency] = useState("");
  const [product, setProduct] = useState("");
  const [gestionnaire, setGestionnaire] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [ownerKind, setOwnerKind] = useState("");
  const [cbsError, setCbsError] = useState(false);
  const [openOnly, setOpenOnly] = useState(true);
  const [mine, setMine] = useState(false);
  const [unassigned, setUnassigned] = useState(false);
  const [followupDue, setFollowupDue] = useState(() =>
    Boolean(
      (location.state as { followupDue?: boolean } | null)?.followupDue,
    ),
  );
  const [brokenPromises, setBrokenPromises] = useState(() =>
    Boolean(
      (location.state as { brokenPromises?: boolean } | null)?.brokenPromises,
    ),
  );
  const [search, setSearch] = useState("");
  const [dashScope, setDashScope] = useState<"mine" | "team">(
    canSeeTeamDash ? "team" : "mine",
  );
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  useEffect(() => {
    const st = location.state as {
      followupDue?: boolean;
      brokenPromises?: boolean;
    } | null;
    if (st?.followupDue) {
      setFollowupDue(true);
      setBrokenPromises(false);
      setPage(1);
    }
    if (st?.brokenPromises) {
      setBrokenPromises(true);
      setFollowupDue(false);
      setPage(1);
    }
  }, [location.state]);

  const tranches = useQuery({
    queryKey: ["collection-tranches", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CollectionTranche>>("/collection-tranches/", {
          params: { page_size: 50, ordering: "position" },
        })
      ).data,
    enabled: !needsTenant,
  });

  const dashboard = useQuery({
    queryKey: ["collection-agent-dashboard", activeTenant, dashScope],
    queryFn: async () =>
      (
        await api.get<AgentCollectionDashboard>(
          "/collection-cases/agent-dashboard/",
          { params: { scope: dashScope } },
        )
      ).data,
    enabled: !needsTenant,
  });

  const hearings = useQuery({
    queryKey: ["hearings-agenda", activeTenant],
    queryFn: async () =>
      (
        await api.get<HearingAgendaItem[]>(
          "/collection-cases/hearings-agenda/",
          { params: { within_days: 30 } },
        )
      ).data,
    enabled: canViewLitigation && !needsTenant,
  });

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      "collection-cases",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      parClass,
      trancheId,
      stage,
      agency,
      product,
      gestionnaire,
      assignedTo,
      ownerKind,
      cbsError,
      openOnly,
      mine,
      unassigned,
      followupDue,
      brokenPromises,
      search,
      clientFilter,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<CollectionCase>>("/collection-cases/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(parClass ? { par_class: parClass } : {}),
            ...(trancheId ? { tranche: trancheId } : {}),
            ...(stage ? { stage } : {}),
            ...(agency ? { agency } : {}),
            ...(product ? { product } : {}),
            ...(gestionnaire ? { gestionnaire } : {}),
            ...(assignedTo ? { assigned_to: assignedTo } : {}),
            ...(ownerKind ? { owner_kind: ownerKind } : {}),
            ...(cbsError ? { cbs_error: 1 } : {}),
            ...(openOnly ? { open: 1 } : {}),
            ...(mine ? { mine: 1 } : {}),
            ...(unassigned ? { unassigned: 1 } : {}),
            ...(followupDue ? { followup_due: 1 } : {}),
            ...(brokenPromises ? { broken_promises: 1 } : {}),
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(clientFilter ? { client: clientFilter } : {}),
            ordering: followupDue ? "next_action_date" : "-days_overdue",
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  const refreshOverdue = useMutation({
    mutationFn: async () => {
      const res = await api.post(
        "/collection-cases/refresh-overdue/",
        {},
        { validateStatus: (s) => s === 200 || s === 202 },
      );
      return { httpStatus: res.status, data: res.data as Record<string, unknown> };
    },
    onSuccess: async (payload) => {
      const invalidate = () => {
        qc.invalidateQueries({ queryKey: ["collection-cases"] });
        qc.invalidateQueries({ queryKey: ["collection-agent-dashboard"] });
      };
      invalidate();
      setRefreshNotice(null);
      const taskId =
        typeof payload.data?.task_id === "string"
          ? payload.data.task_id
          : null;
      if (payload.httpStatus === 202 && taskId) {
        setRefreshNotice("Recalcul en cours…");
        try {
          const { pollAsyncTask } = await import("@/utils/pollAsyncTask");
          await pollAsyncTask(taskId, {
            intervalMs: 3000,
            maxAttempts: 40,
            onTick: invalidate,
          });
          invalidate();
          setRefreshNotice("Retards recalculés.");
        } catch (e) {
          setRefreshNotice(
            e instanceof Error
              ? e.message
              : "Échec du recalcul des retards.",
          );
        }
      } else if (payload.httpStatus === 200) {
        setRefreshNotice("Retards recalculés.");
      }
    },
    onError: (err: unknown) => {
      setRefreshNotice(
        apiErrorMessage(err, "Impossible de lancer le recalcul des retards."),
      );
    },
  });

  function applyKpiFilter(
    kind: "mine" | "followups" | "broken" | "unassigned",
  ) {
    setPage(1);
    setFollowupDue(kind === "followups");
    setBrokenPromises(kind === "broken");
    setUnassigned(kind === "unassigned");
    if (kind === "mine") {
      setMine(true);
      setUnassigned(false);
    } else if (kind === "unassigned") {
      setMine(false);
    } else if (dashScope === "team") {
      setMine(false);
    }
  }

  async function exportCsv() {
    const res = await api.get("/collection-cases/export/", {
      params: {
        ...(parClass ? { par_class: parClass } : {}),
        ...(trancheId ? { tranche: trancheId } : {}),
        ...(stage ? { stage } : {}),
        ...(agency ? { agency } : {}),
        ...(product ? { product } : {}),
        ...(gestionnaire ? { gestionnaire } : {}),
        ...(assignedTo ? { assigned_to: assignedTo } : {}),
        ...(ownerKind ? { owner_kind: ownerKind } : {}),
        ...(cbsError ? { cbs_error: 1 } : {}),
        ...(openOnly ? { open: 1 } : {}),
        ...(mine ? { mine: 1 } : {}),
        ...(unassigned ? { unassigned: 1 } : {}),
        ...(followupDue ? { followup_due: 1 } : {}),
        ...(brokenPromises ? { broken_promises: 1 } : {}),
        ...(search.trim() ? { search: search.trim() } : {}),
        ...(clientFilter ? { client: clientFilter } : {}),
        ordering: followupDue ? "next_action_date" : "-days_overdue",
      },
      responseType: "blob",
    });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "recouvrement.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const dash = dashboard.data;
  const showHearingsPanel = canViewLitigation;
  const showFollowupsPanel = Boolean(dash) && !clientFilter;
  const showCollectionsAside = showHearingsPanel || showFollowupsPanel;

  return (
    <div className="page-shell page-shell--list collections-page">
      <div className="list-page-chrome">
        <PageHeader
          icon={CircleDollarSign}
          title="Recouvrement"
          subtitle="Impayés lus depuis le CBS — suivi terrain, pas de saisie d'encaissement"
          actions={
            <div className="row-actions" style={{ gap: 8 }}>
              {canRefreshCbs && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={refreshOverdue.isPending}
                  onClick={() => refreshOverdue.mutate()}
                >
                  {refreshOverdue.isPending
                    ? "Lancement…"
                    : "Recalculer depuis le CBS"}
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={exportCsv}
              >
                <Download size={14} /> Export CSV
              </button>
            </div>
          }
        />
        {needsTenant && <TenantScopeNotice />}

        {refreshNotice && (
          <p
            className={
              refreshNotice.includes("Échec") ||
              refreshNotice.includes("Impossible") ||
              refreshNotice.includes("Délai")
                ? "form-error"
                : "muted"
            }
            style={{ marginBottom: 10 }}
          >
            {refreshNotice}
          </p>
        )}

        {canSeeTeamDash && (
          <div className="row-actions" style={{ marginBottom: 10, gap: 8 }}>
            <button
              type="button"
              className={`btn btn-sm ${dashScope === "mine" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setDashScope("mine")}
            >
              Mes indicateurs
            </button>
            <button
              type="button"
              className={`btn btn-sm ${dashScope === "team" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setDashScope("team")}
            >
              Équipe / filiale
            </button>
          </div>
        )}

        {dash && (
          <div className="mini-kpis" style={{ marginBottom: 16 }}>
            <button
              type="button"
              className="mini-kpi"
              onClick={() => {
                setPage(1);
                setFollowupDue(false);
                setBrokenPromises(false);
                setUnassigned(false);
                setMine(dashScope === "mine");
              }}
              title="Filtrer le portefeuille"
            >
              <span className="mk-value">{dash.assigned_open}</span>
              <span className="mk-label">
                {dashScope === "team" ? "Dossiers ouverts" : "Mon portefeuille"}
              </span>
            </button>
            {dashScope === "team" && (
              <button
                type="button"
                className="mini-kpi"
                onClick={() => applyKpiFilter("unassigned")}
              >
                <span className="mk-value">{dash.unassigned_open ?? 0}</span>
                <span className="mk-label">Non affectés</span>
              </button>
            )}
            <button
              type="button"
              className="mini-kpi"
              onClick={() => applyKpiFilter("followups")}
            >
              <span className="mk-value">{dash.followups_due}</span>
              <span className="mk-label">Actions dues</span>
            </button>
            <div className="mini-kpi">
              <span className="mk-value">{dash.pending_promises}</span>
              <span className="mk-label">Promesses en cours</span>
            </div>
            <button
              type="button"
              className="mini-kpi"
              onClick={() => applyKpiFilter("broken")}
            >
              <span className="mk-value">{dash.broken_promises_30d}</span>
              <span className="mk-label">Promesses rompues (30 j)</span>
            </button>
            <div className="mini-kpi">
              <span className="mk-value">{dash.settled_this_month ?? 0}</span>
              <span className="mk-label">Soldés CBS ce mois</span>
            </div>
          </div>
        )}

        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={(value) => {
                setPage(1);
                setSearch(value);
              }}
              placeholder="Référence, client, CBS…"
            />
          }
          activeCount={
            countActive(
              search,
              parClass,
              trancheId,
              stage,
              agency,
              product,
              gestionnaire,
              assignedTo,
              ownerKind,
              cbsError,
              unassigned,
              followupDue,
              brokenPromises,
              clientFilter,
            ) +
            (openOnly ? 0 : 1) +
            (mine ? 1 : 0)
          }
          onReset={() => {
            setSearch("");
            setParClass("");
            setTrancheId("");
            setStage("");
            setAgency("");
            setProduct("");
            setGestionnaire("");
            setAssignedTo("");
            setOwnerKind("");
            setCbsError(false);
            setOpenOnly(true);
            setMine(false);
            setUnassigned(false);
            setFollowupDue(false);
            setBrokenPromises(false);
            setPage(1);
            if (clientFilter) clearClientFilter();
          }}
          extra={
            <>
              <FilterToggle
                label="Ouverts seulement"
                checked={openOnly}
                onChange={setFilter(setOpenOnly)}
              />
              <FilterToggle
                label="Mon portefeuille"
                checked={mine}
                onChange={(checked) => {
                  setPage(1);
                  setMine(checked);
                  if (checked) {
                    setUnassigned(false);
                    setAssignedTo("");
                  }
                }}
              />
              <FilterToggle
                label="Non affectés"
                checked={unassigned}
                onChange={(checked) => {
                  setPage(1);
                  setUnassigned(checked);
                  if (checked) {
                    setMine(false);
                    setAssignedTo("");
                  }
                }}
              />
              <FilterToggle
                label="Actions dues"
                checked={followupDue}
                onChange={setFilter(setFollowupDue)}
              />
              <FilterToggle
                label="Promesses rompues"
                checked={brokenPromises}
                onChange={setFilter(setBrokenPromises)}
              />
              <FilterToggle
                label="Erreur synchro CBS"
                checked={cbsError}
                onChange={setFilter(setCbsError)}
              />
            </>
          }
        >
          <FilterField label="Classe PAR" active={!!parClass}>
            <FilterSelect value={parClass} onChange={setFilter(setParClass)}>
              {PAR_OPTIONS.map((o) => (
                <option key={o.value || "all"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Tranche" active={!!trancheId}>
            <FilterSelect value={trancheId} onChange={setFilter(setTrancheId)}>
              <option value="">Toutes les tranches</option>
              {(tranches.data?.results ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.days_label})
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Stade" active={!!stage}>
            <FilterSelect value={stage} onChange={setFilter(setStage)}>
              {STAGE_OPTIONS.map((o) => (
                <option key={o.value || "all"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Responsable" active={!!ownerKind}>
            <FilterSelect value={ownerKind} onChange={setFilter(setOwnerKind)}>
              {OWNER_OPTIONS.map((o) => (
                <option key={o.value || "all"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <AgencyFilter value={agency} onChange={setFilter(setAgency)} />
          <ProductFilter value={product} onChange={setFilter(setProduct)} />
          <OfficerFilter
            value={gestionnaire}
            onChange={setFilter(setGestionnaire)}
          />
          <OfficerFilter
            value={assignedTo}
            onChange={(value) => {
              setPage(1);
              setAssignedTo(value);
              if (value) {
                setMine(false);
                setUnassigned(false);
              }
            }}
            label="Agent"
            emptyLabel="Tous les agents"
          />
        </ListFilters>
        <ClientFilterBanner
          clientId={clientFilter}
          onClear={() => {
            clearClientFilter();
            setPage(1);
          }}
        />
      </div>

      <div
        className={`collections-workspace${showCollectionsAside ? " has-aside" : ""}`}
      >
        <div className="list-table-region">
          <QueryStatus
            isLoading={isLoading}
            isError={isError}
            isEmpty={!data?.results.length}
            emptyMessage="Aucun crédit en impayé."
            onRetry={() => refetch()}
          >
            <>
              <div className="table-scroll table-scroll--fill">
                <table className="table card">
                  <thead>
                    <tr>
                      <th>Dossier</th>
                      <th>Client</th>
                      <th>Produit</th>
                      <th>PAR</th>
                      <th>Tranche</th>
                      <th className="num">Jours</th>
                      <th className="num">Impayé</th>
                      <th>Prochaine action</th>
                      <th>Agent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.results ?? []).map((c) => (
                      <tr
                        key={c.id}
                        className="row-clickable"
                        onClick={() => navigate(`/recouvrement/${c.id}`)}
                      >
                        <td>
                          {c.application_reference || c.loan.slice(0, 8)}
                        </td>
                        <td>{c.client_name}</td>
                        <td className="small">{c.product_name || "—"}</td>
                        <td>
                          <Badge value={c.par_class_display} />
                        </td>
                        <td>
                          <Badge value={c.tranche_name || c.stage_display} />
                        </td>
                        <td className="num">{c.days_overdue}</td>
                        <td className="num">
                          {formatMoney(c.overdue_amount)}
                        </td>
                        <td className="small">
                          {c.next_action_date
                            ? `${c.next_action_date}${
                                c.next_action_type_display
                                  ? ` · ${c.next_action_type_display}`
                                  : ""
                              }`
                            : "—"}
                        </td>
                        <td className="small">
                          {c.assigned_to_name || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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

        {showCollectionsAside && (
          <aside className="collections-aside" aria-label="Suivi terrain">
            {showHearingsPanel && (
              <div className="collections-aside-card">
                <div className="collections-aside-head">
                  <strong>Agenda audiences</strong>
                  <span className="muted small">30 j</span>
                </div>
                {hearings.data && hearings.data.length > 0 ? (
                  <div className="collections-aside-scroll">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Client</th>
                          <th>Juridiction</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hearings.data.map((h) => (
                          <tr
                            key={h.id}
                            className="row-clickable"
                            onClick={() =>
                              navigate(
                                `/recouvrement/${h.case_id}/contentieux/${h.id}`,
                              )
                            }
                          >
                            <td className="small">
                              {h.hearing_date}
                              {h.hearing_time
                                ? ` ${String(h.hearing_time).slice(0, 5)}`
                                : ""}
                            </td>
                            <td className="small">{h.client_name}</td>
                            <td className="small muted">
                              {h.court_name || h.law_firm_name || "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted small collections-aside-empty">
                    Aucune audience planifiée.
                  </p>
                )}
              </div>
            )}

            {showFollowupsPanel && (
              <div className="collections-aside-card">
                <div className="collections-aside-head">
                  <strong>Prochaines actions</strong>
                </div>
                {dash && dash.due_followups.length > 0 ? (
                  <div className="collections-aside-scroll">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Client</th>
                          <th className="num">Impayé</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dash.due_followups.map((f) => (
                          <tr
                            key={f.id}
                            className="row-clickable"
                            onClick={() => navigate(`/recouvrement/${f.id}`)}
                          >
                            <td className="small">
                              {f.next_action_date || "—"}
                              {f.next_action_type
                                ? ` · ${f.next_action_type}`
                                : ""}
                            </td>
                            <td className="small">
                              <div>{f.client_name}</div>
                              <div className="muted">
                                {f.application_reference || f.id.slice(0, 8)}
                              </div>
                            </td>
                            <td className="num small">
                              {formatMoney(f.overdue_amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted small collections-aside-empty">
                    Aucune action planifiée.
                  </p>
                )}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
