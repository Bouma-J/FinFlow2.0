import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Banknote,
  FileUp,
  Gavel,
  Plus,
  Receipt,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Trash2,
  Unlock,
  UserRound,
} from "lucide-react";
import { useMemo, useState, type FormEvent, useEffect } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type {
  ApprovalTask,
  Client,
  GedDocument,
  GuaranteeReleaseRequest,
  Paginated,
  ReleaseClientContext,
  ReleaseClientCredit,
  ReleaseFee,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { PERM_CREDITS, PERM_GUARANTEES } from "@/auth/routePerms";
import { ClientAutocomplete } from "@/components/ClientAutocomplete";
import { PermLink } from "@/components/PermLink";
import { DecisionPanel } from "@/components/DecisionPanel";
import {
  AgencyFilter,
  ClientFilterBanner,
  FilterField,
  FilterSelect,
  ListFilters,
  PROCESS_STATUS_OPTIONS,
  SearchInput,
  countActive,
  useClientSearchParam,
} from "@/components/ListFilters";
import {
  Badge,
  Card,
  DEFAULT_PAGE_SIZE,
  EmptyState,
  ErrorState,
  PageHeader,
  PaginationBar,
  QueryStatus,
  Spinner,
  formatDate,
  formatMoney,
} from "@/components/ui";

const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

const RELEASE_FEE_TYPES = [
  { value: "NOTARY", label: "Notaire / acte" },
  { value: "REGISTRATION", label: "Radiation / publicité" },
  { value: "BAILIFF", label: "Huissier" },
  { value: "ADMIN", label: "Frais administratifs" },
  { value: "OTHER", label: "Divers" },
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export function GuaranteeReleasesPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { clientFilter, clearClientFilter } = useClientSearchParam();
  const canInitiate = hasPerm(
    user,
    "guarantees.initiate_guaranteereleaserequest",
  );
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [agency, setAgency] = useState("");

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  const list = useQuery({
    queryKey: [
      "guarantee-releases",
      page,
      LIST_PAGE_SIZE,
      search,
      status,
      agency,
      clientFilter,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<GuaranteeReleaseRequest>>(
          "/guarantee-releases/",
          {
            params: {
              page,
              page_size: LIST_PAGE_SIZE,
              ...(search.trim() ? { search: search.trim() } : {}),
              ...(status ? { status } : {}),
              ...(agency ? { agency } : {}),
              ...(clientFilter ? { client: clientFilter } : {}),
            },
          },
        )
      ).data,
  });

  return (
    <div className="page-shell page-shell--list">
      <div className="list-page-chrome">
        <PageHeader
          icon={ShieldOff}
          title="Mains levées"
          subtitle="Brouillon → demande client → acte généré/signé → circuit CBS"
          actions={
            canInitiate ? (
              <Link className="btn btn-primary" to="/mains-levees/nouvelle">
                <Plus />
                Nouvelle main levée
              </Link>
            ) : undefined
          }
        />

        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={setFilter(setSearch)}
              placeholder="Réf. ML, prêt CBS, client…"
            />
          }
          activeCount={countActive(search, status, agency, clientFilter)}
          onReset={() => {
            setSearch("");
            setStatus("");
            setAgency("");
            setPage(1);
            if (clientFilter) clearClientFilter();
          }}
        >
          <FilterField label="Statut" active={!!status}>
            <FilterSelect value={status} onChange={setFilter(setStatus)}>
              {PROCESS_STATUS_OPTIONS.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <AgencyFilter value={agency} onChange={setFilter(setAgency)} />
        </ListFilters>
        <ClientFilterBanner
          clientId={clientFilter}
          onClear={() => {
            clearClientFilter();
            setPage(1);
          }}
        />
      </div>

      <div className="list-table-region">
        <QueryStatus
          isLoading={list.isLoading}
          isError={list.isError}
          isEmpty={!list.data?.results.length}
          emptyMessage="Aucune demande de main levée ne correspond à ces critères."
          onRetry={() => list.refetch()}
        >
          <>
            <div className="table-scroll table-scroll--fill">
              <table className="table card">
                <thead>
                  <tr>
                    <th>Référence</th>
                    <th>Garantie</th>
                    <th>Client</th>
                    <th>Date demande</th>
                    <th>Réf. prêt CBS</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {(list.data?.results ?? []).map((r) => (
                    <tr
                      key={r.id}
                      className="row-clickable"
                      onClick={() => navigate(`/mains-levees/${r.id}`)}
                    >
                      <td>
                        <code>{r.reference || "—"}</code>
                      </td>
                      <td>
                        <PermLink
                          user={user}
                          anyOf={PERM_GUARANTEES}
                          to={`/garanties/${r.guarantee}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {r.guarantee_reference || r.guarantee.slice(0, 8)}
                        </PermLink>
                      </td>
                      <td>{r.client_display}</td>
                      <td>
                        {r.request_date ? formatDate(r.request_date) : "—"}
                      </td>
                      <td className="muted small">
                        {r.cbs_loan_reference || "—"}
                      </td>
                      <td>
                        <Badge value={r.status} label={r.status_display} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationBar
              page={page}
              count={list.data?.count ?? 0}
              pageSize={LIST_PAGE_SIZE}
              onPageChange={setPage}
            />
          </>
        </QueryStatus>
      </div>
    </div>
  );
}

export function GuaranteeReleaseNewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [clientId, setClientId] = useState(searchParams.get("client") || "");
  const applicationFromQuery = searchParams.get("application") || "";
  const [cbsClientId, setCbsClientId] = useState("");
  const [guaranteeId, setGuaranteeId] = useState(
    searchParams.get("guarantee") || "",
  );
  const [selectedCreditKey, setSelectedCreditKey] = useState("");
  const [requestDate, setRequestDate] = useState(todayISO());
  const [releaseFees, setReleaseFees] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const context = useQuery({
    queryKey: ["release-client-context", clientId],
    queryFn: async () =>
      (
        await api.get<ReleaseClientContext>(
          "/guarantee-releases/client-context/",
          { params: { client: clientId } },
        )
      ).data,
    enabled: !!clientId,
    retry: false,
  });

  useEffect(() => {
    if (!context.data) return;
    if (context.data.cbs_client_id && !cbsClientId) {
      setCbsClientId(context.data.cbs_client_id);
    }
    const gParam = searchParams.get("guarantee");
    if (
      gParam &&
      !guaranteeId &&
      context.data.guarantees.some((g) => g.id === gParam)
    ) {
      setGuaranteeId(gParam);
    }
    if (!selectedCreditKey && applicationFromQuery) {
      const match = context.data.credits.find(
        (c) => c.application_id === applicationFromQuery,
      );
      if (match) setSelectedCreditKey(creditKey(match));
    }
  }, [
    context.data,
    cbsClientId,
    guaranteeId,
    searchParams,
    selectedCreditKey,
    applicationFromQuery,
  ]);

  const selectedCredit: ReleaseClientCredit | null = useMemo(() => {
    const credits = context.data?.credits ?? [];
    return credits.find((c) => creditKey(c) === selectedCreditKey) ?? null;
  }, [context.data, selectedCreditKey]);

  const settledCredits = (context.data?.credits ?? []).filter(
    (c) => c.cbs_settled === true,
  );

  const canSubmit =
    !!clientId &&
    !!cbsClientId.trim() &&
    !!guaranteeId &&
    !!selectedCredit?.cbs_loan_reference &&
    selectedCredit.cbs_settled === true &&
    !!requestDate;

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<GuaranteeReleaseRequest>("/guarantee-releases/", {
          guarantee: guaranteeId,
          loan: selectedCredit?.loan_id || null,
          cbs_loan_reference: selectedCredit?.cbs_loan_reference || "",
          cbs_client_id: cbsClientId,
          request_date: requestDate,
          release_fees: releaseFees || null,
          as_draft: true,
          comment,
        })
      ).data,
    onSuccess: (data) => navigate(`/mains-levees/${data.id}`),
    onError: (err: unknown) => {
      const data = (err as { response?: { data?: unknown } })?.response?.data;
      const raw =
        data && typeof data === "object" && "errors" in data
          ? (data as { errors: unknown }).errors
          : data;
      setError(
        typeof raw === "string"
          ? raw
          : Array.isArray(raw)
            ? raw.map(String).join(" · ")
            : "Création impossible (prêt non soldé, CBS ou circuit manquant).",
      );
    },
  });

  function onClientPicked(id: string, _label: string, client?: Client | null) {
    setClientId(id);
    setCbsClientId((client?.cbs_client_id || "").trim());
    setGuaranteeId("");
    setSelectedCreditKey("");
    setError(null);
  }

  if (!hasPerm(user, "guarantees.initiate_guaranteereleaserequest")) {
    return (
      <div>
        <PageHeader icon={ShieldOff} title="Nouvelle main levée" />
        <EmptyState message="Vous n'avez pas le droit d'initier une main levée." />
      </div>
    );
  }

  const guarantees = context.data?.guarantees ?? [];
  const credits = context.data?.credits ?? [];
  const currency = selectedCredit?.cbs_currency || "XOF";

  return (
    <div className="page-shell release-compose">
      <PageHeader
        icon={ShieldOff}
        title="Nouvelle main levée"
        subtitle="Garanties Fin Flow + crédits CBS du client (libération si prêt soldé)"
        actions={
          <Link className="btn btn-ghost" to="/mains-levees">
            <ArrowLeft />
            Retour
          </Link>
        }
      />

      <form
        className="release-compose-form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setError(null);
          if (!clientId) {
            setError("Sélectionnez un client.");
            return;
          }
          if (!cbsClientId.trim()) {
            setError(
              "Matricule Core Banking manquant sur la fiche client.",
            );
            return;
          }
          if (!guaranteeId) {
            setError("Choisissez la garantie à libérer.");
            return;
          }
          if (!selectedCredit || selectedCredit.cbs_settled !== true) {
            setError(
              "Sélectionnez un crédit soldé dans le CBS pour autoriser la main levée.",
            );
            return;
          }
          create.mutate();
        }}
      >
        <div className="dation-compose-layout">
          <div className="dation-compose-main">
            <section className="card form-section">
              <div className="card-title form-section-head">
                <span className="form-section-icon">
                  <UserRound size={18} />
                </span>
                <div className="form-section-heading">
                  <span className="form-section-title">1. Client</span>
                  <span className="form-section-desc">
                    Recherchez le client. Le matricule CBS est repris de la
                    fiche ; les garanties et crédits sont chargés
                    automatiquement.
                  </span>
                </div>
              </div>
              <div className="form-grid">
                <label className="field" style={{ gridColumn: "1 / -1" }}>
                  <span>Client</span>
                  <ClientAutocomplete
                    value={clientId}
                    onChange={onClientPicked}
                    required
                  />
                </label>
                <div className="field">
                  <span>Matricule Core Banking (CBS)</span>
                  <div
                    className={`dation-cbs-matricule${cbsClientId ? "" : " missing"}`}
                  >
                    {clientId ? (
                      cbsClientId ? (
                        <code>{cbsClientId}</code>
                      ) : (
                        <span className="muted">
                          Non renseigné sur la fiche client
                        </span>
                      )
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </div>
                </div>
              </div>
            </section>

            {!clientId ? (
              <section className="card form-section dation-compose-empty">
                <ShieldOff size={28} />
                <p>
                  Recherchez un client pour afficher ses garanties Fin Flow et
                  ses crédits avec statut CBS.
                </p>
              </section>
            ) : context.isLoading ? (
              <Spinner />
            ) : context.isError ? (
              <div className="form-error">
                Impossible de charger le contexte client.
              </div>
            ) : (
              <>
                <section className="card form-section">
                  <div className="card-title form-section-head">
                    <span className="form-section-icon">
                      <ShieldCheck size={18} />
                    </span>
                    <div className="form-section-heading">
                      <span className="form-section-title">
                        2. Garantie à libérer
                      </span>
                      <span className="form-section-desc">
                        Garanties actives Fin Flow disponibles pour ce client.
                      </span>
                    </div>
                  </div>
                  {guarantees.length === 0 ? (
                    <EmptyState message="Aucune garantie active disponible." />
                  ) : (
                    <div className="dation-guarantee-list" role="list">
                      {guarantees.map((g) => {
                        const checked = guaranteeId === g.id;
                        const busy = Boolean(g.process_busy);
                        const val =
                          g.current_value ||
                          g.value_to_consider ||
                          g.expertise_value;
                        return (
                          <label
                            key={g.id}
                            role="listitem"
                            className={`dation-guarantee-row${checked ? " selected" : ""}${busy ? " muted" : ""}`}
                          >
                            <input
                              type="radio"
                              name="release-guarantee"
                              checked={checked}
                              disabled={busy}
                              onChange={() => setGuaranteeId(g.id)}
                            />
                            <span className="dation-guarantee-body">
                              <span className="dation-guarantee-title">
                                {g.type_display}
                                <code>
                                  {g.reference || g.id.slice(0, 8)}
                                </code>
                              </span>
                              {g.description && (
                                <span className="dation-guarantee-desc">
                                  {g.description.slice(0, 140)}
                                </span>
                              )}
                              {busy && (
                                <span className="muted small">
                                  {g.process_busy?.label}
                                </span>
                              )}
                            </span>
                            <span className="dation-guarantee-meta">
                              <strong>
                                {formatMoney(val, currency)}
                              </strong>
                              <Badge value={g.status} />
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </section>

                <section className="card form-section">
                  <div className="card-title form-section-head">
                    <span className="form-section-icon">
                      <Banknote size={18} />
                    </span>
                    <div className="form-section-heading">
                      <span className="form-section-title">
                        3. Crédits & statut CBS
                      </span>
                      <span className="form-section-desc">
                        Sélectionnez le crédit soldé dans le CBS justifiant la
                        main levée.
                      </span>
                    </div>
                    <div className="form-section-action">
                      <span className="muted small">
                        {settledCredits.length} soldé
                        {settledCredits.length > 1 ? "s" : ""}
                      </span>
                    </div>
                  </div>
                  {credits.length === 0 ? (
                    <EmptyState message="Aucun dossier / prêt pour ce client." />
                  ) : (
                    <div className="release-credit-list" role="list">
                      {credits.map((c) => {
                        const key = creditKey(c);
                        const checked = selectedCreditKey === key;
                        const settled = c.cbs_settled === true;
                        return (
                          <label
                            key={key}
                            role="listitem"
                            className={`release-credit-row${checked ? " selected" : ""}${settled ? " settled" : " active-loan"}`}
                          >
                            <input
                              type="radio"
                              name="release-credit"
                              checked={checked}
                              disabled={!settled || !c.cbs_loan_reference}
                              onChange={() => setSelectedCreditKey(key)}
                            />
                            <span className="release-credit-body">
                              <span className="dation-guarantee-title">
                                {c.application_reference}
                                {c.product_label && (
                                  <span className="muted small">
                                    {" "}
                                    — {c.product_label}
                                  </span>
                                )}
                              </span>
                              <span className="dation-guarantee-desc">
                                Dossier {c.application_status_display}
                                {c.loan_status_display
                                  ? ` · Prêt Fin Flow : ${c.loan_status_display}`
                                  : " · Pas de prêt local"}
                                {c.cbs_loan_reference
                                  ? ` · CBS ${c.cbs_loan_reference}`
                                  : " · Réf. CBS manquante"}
                              </span>
                              {c.cbs_error && (
                                <span className="form-error small">
                                  {c.cbs_error}
                                </span>
                              )}
                            </span>
                            <span className="dation-guarantee-meta">
                              <strong>
                                {formatMoney(c.amount, c.currency)}
                              </strong>
                              <Badge
                                value={
                                  c.cbs_settled === true
                                    ? "OK"
                                    : c.cbs_settled === false
                                      ? "WARN"
                                      : "DRAFT"
                                }
                                label={c.cbs_status_label}
                              />
                              {c.cbs_settled === false &&
                                c.cbs_outstanding != null && (
                                  <span className="muted small">
                                    Encours{" "}
                                    {formatMoney(
                                      c.cbs_outstanding,
                                      c.cbs_currency,
                                    )}
                                  </span>
                                )}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </section>

                <section className="card form-section">
                  <div className="card-title form-section-head">
                    <span className="form-section-icon">
                      <Unlock size={18} />
                    </span>
                    <div className="form-section-heading">
                      <span className="form-section-title">
                        4. Informations de la demande
                      </span>
                      <span className="form-section-desc">
                        Date, frais et commentaire pour le circuit.
                      </span>
                    </div>
                  </div>
                  <div className="form-grid">
                    <label className="field">
                      <span>Date de la demande</span>
                      <input
                        type="date"
                        value={requestDate}
                        onChange={(e) => setRequestDate(e.target.value)}
                        required
                      />
                    </label>
                    <label className="field">
                      <span>Frais de main levée</span>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={releaseFees}
                        onChange={(e) => setReleaseFees(e.target.value)}
                        placeholder="Optionnel"
                      />
                    </label>
                    <label
                      className="field"
                      style={{ gridColumn: "1 / -1" }}
                    >
                      <span>Commentaire / motif</span>
                      <textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        rows={3}
                        placeholder="Observations, pièces jointes à prévoir…"
                      />
                    </label>
                  </div>
                </section>
              </>
            )}
          </div>

          <aside className="dation-compose-aside">
            <div className="dation-coverage panel">
              <div className="dation-coverage-head">
                <Unlock size={18} />
                <strong>Récapitulatif</strong>
              </div>
              {!clientId ? (
                <p className="muted small">Sélectionnez un client.</p>
              ) : (
                <dl className="def-list">
                  <div>
                    <dt>Matricule CBS</dt>
                    <dd>
                      <code>{cbsClientId || "—"}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Garanties dispo.</dt>
                    <dd>{guarantees.length}</dd>
                  </div>
                  <div>
                    <dt>Crédits CBS</dt>
                    <dd>
                      {credits.length} dont {settledCredits.length} soldé
                      {settledCredits.length > 1 ? "s" : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Crédit retenu</dt>
                    <dd>
                      {selectedCredit
                        ? selectedCredit.application_reference
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Prêt CBS</dt>
                    <dd>
                      {selectedCredit?.cbs_settled === true
                        ? "Soldé — main levée possible"
                        : selectedCredit
                          ? "Non soldé / non sélectionnable"
                          : "—"}
                    </dd>
                  </div>
                </dl>
              )}
            </div>

            {error && <div className="form-error">{error}</div>}

            <div className="dation-compose-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={create.isPending || !canSubmit}
              >
                {create.isPending
                  ? "Vérification CBS…"
                  : "Créer le brouillon"}
              </button>
              <Link className="btn btn-ghost" to="/mains-levees">
                Annuler
              </Link>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
}

function creditKey(c: ReleaseClientCredit) {
  return `${c.application_id}:${c.loan_id || "none"}:${c.cbs_loan_reference || ""}`;
}

export function GuaranteeReleaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { user } = useAuth();
  const canInitiate = hasPerm(
    user,
    "guarantees.initiate_guaranteereleaserequest",
  );

  const [demandeFile, setDemandeFile] = useState<File | null>(null);
  const [signedFile, setSignedFile] = useState<File | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [feeType, setFeeType] = useState("NOTARY");
  const [feeAmount, setFeeAmount] = useState("");
  const [feePayer, setFeePayer] = useState("CLIENT");
  const [feeLabel, setFeeLabel] = useState("");
  const [draftComment, setDraftComment] = useState("");

  const detail = useQuery({
    queryKey: ["guarantee-release", id],
    queryFn: async () =>
      (await api.get<GuaranteeReleaseRequest>(`/guarantee-releases/${id}/`))
        .data,
    enabled: !!id,
  });

  const docs = useQuery({
    queryKey: ["guarantee-release-docs", id],
    queryFn: async () =>
      (await api.get<GedDocument[]>(`/guarantee-releases/${id}/documents/`))
        .data,
    enabled: !!id,
  });

  const workflow = useQuery({
    queryKey: ["guarantee-release-workflow", id],
    queryFn: async () =>
      (
        await api.get<{
          instance: { status: string; definition_code?: string } | null;
        }>(`/guarantee-releases/${id}/workflow/`)
      ).data,
    enabled: !!id,
  });

  const { data: myTasks } = useQuery({
    queryKey: ["my-pending-tasks"],
    queryFn: async () =>
      (await api.get<Paginated<ApprovalTask>>("/approval-tasks/my_pending/"))
        .data,
  });

  function invalidateAll() {
    qc.invalidateQueries({ queryKey: ["guarantee-release", id] });
    qc.invalidateQueries({ queryKey: ["guarantee-release-docs", id] });
    qc.invalidateQueries({ queryKey: ["guarantee-release-workflow", id] });
    qc.invalidateQueries({ queryKey: ["guarantee-releases"] });
    qc.invalidateQueries({ queryKey: ["guarantees"] });
  }

  function errMsg(err: unknown, fallback: string) {
    const data = (err as { response?: { data?: unknown } })?.response?.data;
    const raw =
      data && typeof data === "object" && "errors" in data
        ? (data as { errors: unknown }).errors
        : data;
    if (typeof raw === "string") return raw;
    if (Array.isArray(raw)) return raw.map(String).join(" · ");
    return fallback;
  }

  const retry = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-releases/${id}/retry_cbs/`)).data,
    onSuccess: () => invalidateAll(),
    onError: (e) => setActionError(errMsg(e, "Échec retry CBS.")),
  });

  const submit = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-releases/${id}/submit/`)).data,
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Soumission impossible.")),
  });

  const cancel = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/guarantee-releases/${id}/cancel/`, {
          comment: "Annulé",
        })
      ).data,
    onSuccess: () => invalidateAll(),
    onError: (e) => setActionError(errMsg(e, "Annulation impossible.")),
  });

  const refreshCbs = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-releases/${id}/refresh-cbs/`)).data,
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) =>
      setActionError(errMsg(e, "Rafraîchissement CBS impossible.")),
  });

  const addFee = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/guarantee-releases/${id}/add-fee/`, {
          fee_type: feeType,
          label: feeLabel,
          amount: feeAmount,
          payer: feePayer,
        })
      ).data,
    onSuccess: () => {
      setFeeAmount("");
      setFeeLabel("");
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Ajout de frais impossible.")),
  });

  const removeFee = useMutation({
    mutationFn: async (feeId: string) =>
      (await api.post(`/guarantee-releases/${id}/remove-fee/${feeId}/`)).data,
    onSuccess: () => invalidateAll(),
  });

  const updateDraft = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/guarantee-releases/${id}/update-draft/`, {
          comment: draftComment || detail.data?.comment || "",
        })
      ).data,
    onSuccess: () => invalidateAll(),
    onError: (e) => setActionError(errMsg(e, "Mise à jour impossible.")),
  });

  const generateActe = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-releases/${id}/generate-acte/`)).data,
    onSuccess: () => invalidateAll(),
    onError: (e) => setActionError(errMsg(e, "Génération impossible.")),
  });

  const uploadDemande = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (demandeFile) fd.append("file", demandeFile);
      fd.append("name", demandeFile?.name || "Demande client");
      fd.append("category", "ML_DEMANDE");
      return (
        await api.post(`/guarantee-releases/${id}/documents/`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      ).data;
    },
    onSuccess: () => {
      setDemandeFile(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Upload demande impossible.")),
  });

  const uploadSigned = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (signedFile) fd.append("file", signedFile);
      return (
        await api.post(`/guarantee-releases/${id}/upload-acte-signe/`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      ).data;
    },
    onSuccess: () => {
      setSignedFile(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Dépôt acte signé impossible.")),
  });

  if (detail.isLoading) return <Spinner />;
  if (detail.isError || !detail.data)
    return (
      <ErrorState
        message="Impossible de charger la main levée."
        onRetry={() => detail.refetch()}
      />
    );
  const r = detail.data;
  const cur = r.cbs_currency || "XOF";
  const editable = r.status === "DRAFT" || r.status === "RETURNED";
  const canCancel =
    canInitiate &&
    ["DRAFT", "RETURNED", "IN_APPROVAL", "BLOCKED"].includes(r.status);
  const canUploadDocs = !["COMPLETED", "CANCELLED", "REJECTED"].includes(
    r.status,
  );
  const myTask =
    myTasks?.results.find(
      (t) =>
        t.target_meta?.kind === "MAIN_LEVEE" && t.target_meta.id === r.id,
    ) ?? null;
  const canDepositSigned =
    Boolean(r.can_deposit_signed_acte) || canInitiate || Boolean(myTask);
  const fees: ReleaseFee[] = r.fees ?? [];
  const schedule = Array.isArray(r.cbs_raw?.datas)
    ? (r.cbs_raw.datas as Array<Record<string, unknown>>)
    : [];

  const stepDemandeDone = Boolean(r.has_client_demande);
  const stepActeDone = Boolean(r.has_signed_acte);
  const stepCircuitDone = ["APPROVED", "COMPLETED"].includes(r.status);
  const stepClosed = r.status === "COMPLETED";
  const stepCurrent = !stepDemandeDone
    ? 1
    : !stepActeDone && editable
      ? 2
      : !stepCircuitDone
        ? 3
        : stepClosed
          ? 4
          : 3;

  return (
    <div className="page-shell detail-banner-page release-detail-page">
      <div className="client-banner">
        <div className="client-banner-main">
          <div className="client-banner-info">
            <span className="client-banner-icon">
              <Unlock size={26} />
            </span>
            <div className="client-banner-identity">
              <h2 className="client-banner-name">
                {r.client_display || "Main levée"}
              </h2>
              <p className="client-banner-ref">
                Main levée <code>{r.reference || "—"}</code>
                {r.guarantee && (
                  <PermLink
                    user={user}
                    anyOf={PERM_GUARANTEES}
                    className="client-banner-inline-link"
                    to={`/garanties/${r.guarantee}`}
                    fallback={
                      r.guarantee_reference ? (
                        <span className="muted">
                          · {r.guarantee_reference}
                        </span>
                      ) : null
                    }
                  >
                    · Garantie{" "}
                    {r.guarantee_reference || r.guarantee.slice(0, 8)}
                  </PermLink>
                )}
                {r.application && (
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    className="client-banner-inline-link"
                    to={`/dossiers/${r.application}`}
                    fallback={null}
                  >
                    · Dossier crédit {r.application.slice(0, 8)}
                  </PermLink>
                )}
              </p>
              <div className="client-banner-meta">
                <Badge value={r.status} label={r.status_display} />
                <Badge
                  value={r.acte_status || "NONE"}
                  label={r.acte_status_display || "Acte non généré"}
                />
                {r.cbs_settled != null && (
                  <Badge
                    value={r.cbs_settled ? "ACTIVE" : "WARN"}
                    label={r.cbs_settled ? "Prêt soldé CBS" : "Prêt non soldé"}
                  />
                )}
                <span className="muted">
                  Encours : {formatMoney(r.cbs_outstanding, cur)}
                </span>
              </div>
            </div>
          </div>

          <div className="client-banner-actions">
            <Link className="btn btn-banner" to="/mains-levees">
              <ArrowLeft size={15} />
              Retour
            </Link>
            {canInitiate &&
              !["COMPLETED", "CANCELLED", "REJECTED"].includes(r.status) && (
                <button
                  type="button"
                  className="btn btn-banner"
                  onClick={() => refreshCbs.mutate()}
                  disabled={refreshCbs.isPending}
                >
                  <RefreshCw size={15} />
                  Rafraîchir CBS
                </button>
              )}
            {canCancel && (
              <button
                type="button"
                className="btn btn-banner btn-banner-danger"
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
              >
                Annuler
              </button>
            )}
            {r.status === "BLOCKED" && (
              <button
                type="button"
                className="btn btn-banner btn-banner-primary"
                onClick={() => retry.mutate()}
                disabled={retry.isPending}
              >
                <RefreshCw size={15} />
                Retenter CBS
              </button>
            )}
            {canInitiate && editable && (
              <button
                type="button"
                className="btn btn-banner btn-banner-primary"
                onClick={() => submit.mutate()}
                disabled={submit.isPending}
              >
                Soumettre au circuit
              </button>
            )}
          </div>
        </div>
      </div>

      {actionError && <div className="form-error">{actionError}</div>}

      {r.status === "APPROVED" && !r.has_signed_acte && (
        <div className="form-error">
          Dossier approuvé : déposez l&apos;acte signé pour clôturer la main
          levée.
        </div>
      )}

      <div className="process-steps" aria-label="Étapes du processus">
        {[
          {
            n: 1,
            label: "Demande client",
            hint: stepDemandeDone ? "Jointe" : "À joindre",
            done: stepDemandeDone,
          },
          {
            n: 2,
            label: "Acte",
            hint: stepActeDone
              ? "Signé"
              : r.has_generated_acte
                ? "À signer"
                : "À générer",
            done: stepActeDone,
          },
          {
            n: 3,
            label: "Circuit",
            hint: stepCircuitDone ? "Validé" : "Validation",
            done: stepCircuitDone,
          },
          {
            n: 4,
            label: "Clôture",
            hint: stepClosed ? "Terminée" : "En attente",
            done: stepClosed,
          },
        ].map((s) => (
          <div
            key={s.n}
            className={`process-step${s.done ? " done" : ""}${
              stepCurrent === s.n ? " current" : ""
            }`}
          >
            <span className="step-num">{s.n}</span>
            <span>
              <strong>{s.label}</strong>
              {s.hint}
            </span>
          </div>
        ))}
      </div>

      <div className="detail-sections">
        <div className="detail-sections-row">
          <Card
            title={
              <>
                <ShieldCheck size={17} /> Dossier
              </>
            }
          >
            <dl className="def-list two">
              <div>
                <dt>Statut</dt>
                <dd>
                  <Badge value={r.status} label={r.status_display} />
                </dd>
              </div>
              <div>
                <dt>Garantie</dt>
                <dd>
                  <PermLink
                    user={user}
                    anyOf={PERM_GUARANTEES}
                    to={`/garanties/${r.guarantee}`}
                  >
                    {r.guarantee_reference || r.guarantee.slice(0, 8)}
                  </PermLink>
                </dd>
              </div>
              <div>
                <dt>Client</dt>
                <dd>{r.client_display || "—"}</dd>
              </div>
              <div>
                <dt>Date de demande</dt>
                <dd>
                  {r.request_date ? formatDate(r.request_date) : "—"}
                </dd>
              </div>
              <div>
                <dt>Demande client</dt>
                <dd>{r.has_client_demande ? "Jointe" : "Manquante"}</dd>
              </div>
              <div>
                <dt>Acte signé</dt>
                <dd>{r.has_signed_acte ? "Déposé" : "Manquant"}</dd>
              </div>
              <div>
                <dt>Frais client</dt>
                <dd>
                  {formatMoney(r.fees_client_total ?? r.release_fees ?? null, cur)}
                </dd>
              </div>
              <div>
                <dt>Frais institution</dt>
                <dd>{formatMoney(r.fees_institution_total ?? null, cur)}</dd>
              </div>
            </dl>
            {editable && canInitiate && (
              <div className="form-grid" style={{ marginTop: 12 }}>
                <label className="field full-span">
                  <span>Commentaire</span>
                  <textarea
                    rows={2}
                    value={draftComment || r.comment || ""}
                    onChange={(e) => setDraftComment(e.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={updateDraft.isPending}
                  onClick={() => updateDraft.mutate()}
                >
                  Enregistrer le commentaire
                </button>
              </div>
            )}
            {!editable && r.comment && (
              <p className="muted small" style={{ marginTop: 12 }}>
                {r.comment}
              </p>
            )}
          </Card>

          <Card
            title={
              <>
                <Banknote size={17} /> Situation CBS
              </>
            }
          >
            <dl className="def-list two">
              <div>
                <dt>Réf. demande CBS</dt>
                <dd>
                  <code>{r.cbs_loan_reference || "—"}</code>
                </dd>
              </div>
              <div>
                <dt>Code adhérent</dt>
                <dd>
                  <code>{r.cbs_client_id || "—"}</code>
                </dd>
              </div>
              <div>
                <dt>Soldé CBS</dt>
                <dd>
                  {r.cbs_settled == null ? (
                    "—"
                  ) : r.cbs_settled ? (
                    <Badge value="ACTIVE" label="Oui" />
                  ) : (
                    <Badge value="WARN" label="Non" />
                  )}
                </dd>
              </div>
              <div>
                <dt>Encours CBS</dt>
                <dd>{formatMoney(r.cbs_outstanding, cur)}</dd>
              </div>
              <div>
                <dt>Devise</dt>
                <dd>{cur}</dd>
              </div>
              <div>
                <dt>Vérifié le</dt>
                <dd>
                  {r.cbs_checked_at ? formatDate(r.cbs_checked_at) : "—"}
                </dd>
              </div>
            </dl>
          </Card>
        </div>

        <div className="detail-sections-row">
          <Card
            title={
              <>
                <FileUp size={17} /> Demande client
              </>
            }
          >
            <p className="muted small">
              Joindre la demande de main levée transmise par le client
              (obligatoire avant soumission).
            </p>
            {(docs.data ?? []).length > 0 && (
              <ul className="link-list">
                {(docs.data ?? []).map((d) => (
                  <li
                    key={d.id}
                    className="row-clickable"
                    onClick={() =>
                      window.open(d.file, "_blank", "noopener,noreferrer")
                    }
                  >
                    <span>
                      <FileUp size={14} /> {d.name}
                      <em className="muted small"> · {d.category_label}</em>
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {canInitiate && canUploadDocs && (
              <div className="form-grid" style={{ marginTop: 12 }}>
                <label className="field">
                  <span>Fichier demande</span>
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={(e) =>
                      setDemandeFile(e.target.files?.[0] ?? null)
                    }
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!demandeFile || uploadDemande.isPending}
                  onClick={() => uploadDemande.mutate()}
                >
                  <FileUp size={14} />
                  Charger la demande
                </button>
              </div>
            )}
          </Card>

          <Card
            title={
              <>
                <ShieldOff size={17} /> Acte de main levée
              </>
            }
          >
            <p className="muted small">
              Générez l&apos;acte, faites-le signer, puis déposez le scan.
              L&apos;acte signé est obligatoire pour clôturer.
            </p>
            <dl className="def-list two">
              <div>
                <dt>Statut acte</dt>
                <dd>
                  <Badge
                    value={r.acte_status || "NONE"}
                    label={r.acte_status_display || "Non généré"}
                  />
                </dd>
              </div>
              <div>
                <dt>Acte généré</dt>
                <dd>
                  {r.acte_generated_url ? (
                    <a
                      href={r.acte_generated_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Télécharger
                    </a>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Généré le</dt>
                <dd>
                  {r.acte_generated_at
                    ? formatDate(r.acte_generated_at)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Acte signé</dt>
                <dd>
                  {r.acte_signed_url ? (
                    <a
                      href={r.acte_signed_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Voir le dépôt
                    </a>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Signé déposé le</dt>
                <dd>
                  {r.acte_signed_at ? formatDate(r.acte_signed_at) : "—"}
                </dd>
              </div>
            </dl>
            {canInitiate && canUploadDocs && (
              <div className="row-actions" style={{ marginTop: 12, gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={generateActe.isPending || r.has_signed_acte}
                  onClick={() => generateActe.mutate()}
                >
                  {r.has_generated_acte
                    ? "Régénérer l'acte"
                    : "Générer l'acte"}
                </button>
              </div>
            )}
            {canDepositSigned &&
              r.has_generated_acte &&
              !r.has_signed_acte &&
              canUploadDocs && (
                <div className="form-grid" style={{ marginTop: 12 }}>
                  <label className="field">
                    <span>Acte signé (PDF / scan)</span>
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png"
                      onChange={(e) =>
                        setSignedFile(e.target.files?.[0] ?? null)
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={!signedFile || uploadSigned.isPending}
                    onClick={() => uploadSigned.mutate()}
                  >
                    <FileUp size={14} />
                    Déposer l&apos;acte signé
                  </button>
                </div>
              )}
          </Card>
        </div>

        <div className="detail-sections-row">
          <Card
            title={
              <>
                <Receipt size={17} /> Frais
              </>
            }
          >
            {fees.length === 0 ? (
              <p className="muted small">Aucun frais enregistré.</p>
            ) : (
              <ul className="link-list">
                {fees.map((f) => (
                  <li key={f.id}>
                    <span>
                      <Receipt size={14} /> {f.fee_type_display}
                      {f.label ? ` — ${f.label}` : ""}
                      <em className="muted small"> · {f.payer_display}</em>
                    </span>
                    <span className="row-actions">
                      <span className="num">
                        {formatMoney(f.amount, cur)}
                      </span>
                      {editable && canInitiate && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => removeFee.mutate(f.id)}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {editable && canInitiate && (
              <div className="form-grid" style={{ marginTop: 12 }}>
                <label className="field">
                  <span>Type</span>
                  <select
                    value={feeType}
                    onChange={(e) => setFeeType(e.target.value)}
                  >
                    {RELEASE_FEE_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Montant</span>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={feeAmount}
                    onChange={(e) => setFeeAmount(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Payeur</span>
                  <select
                    value={feePayer}
                    onChange={(e) => setFeePayer(e.target.value)}
                  >
                    <option value="CLIENT">Client</option>
                    <option value="INSTITUTION">Institution</option>
                  </select>
                </label>
                <label className="field">
                  <span>Libellé</span>
                  <input
                    value={feeLabel}
                    onChange={(e) => setFeeLabel(e.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!feeAmount || addFee.isPending}
                  onClick={() => addFee.mutate()}
                >
                  <Plus size={14} />
                  Ajouter frais
                </button>
              </div>
            )}
          </Card>

          <Card
            title={
              <>
                <Gavel size={17} /> Circuit & décision
              </>
            }
          >
            {!workflow.data?.instance ? (
              <EmptyState
                message={
                  editable
                    ? "Circuit non démarré — joignez la demande, générez l'acte, puis soumettez."
                    : "Aucun circuit associé."
                }
              />
            ) : (
              <dl className="def-list two">
                <div>
                  <dt>Circuit</dt>
                  <dd>{workflow.data.instance.definition_code || "—"}</dd>
                </div>
                <div>
                  <dt>Statut circuit</dt>
                  <dd>
                    <Badge value={workflow.data.instance.status} />
                  </dd>
                </div>
                <div>
                  <dt>Clôturée le</dt>
                  <dd>
                    {r.completed_at ? formatDate(r.completed_at) : "—"}
                  </dd>
                </div>
              </dl>
            )}
            {myTask && (
              <div style={{ marginTop: 16 }}>
                <h4 className="section-subtitle">
                  Décision — {myTask.step_name}
                </h4>
                <DecisionPanel task={myTask} />
              </div>
            )}
          </Card>
        </div>

        {schedule.length > 0 && (
          <div className="detail-sections-row full">
            <Card
              title={
                <>
                  <UserRound size={17} /> Échéancier CBS (crd/situation)
                </>
              }
            >
              <div className="table-scroll">
                <table className="table">
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
                    {schedule.map((row, idx) => (
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
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
