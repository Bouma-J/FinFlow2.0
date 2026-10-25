import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  Check,
  FileSignature,
  FileUp,
  FolderOpen,
  Gavel,
  Landmark,
  Plus,
  Receipt,
  Scale,
  ScrollText,
  Search,
  ShieldCheck,
  Stamp,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type {
  ApprovalTask,
  CreditApplication,
  FormalizationComposeContext,
  FormalizationFee,
  GuaranteeFormalizationRequest,
  GedDocument,
  Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  PERM_CLIENTS,
  PERM_CREDITS,
  PERM_GUARANTEES,
} from "@/auth/routePerms";
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

const EDITABLE_STATUSES = ["DRAFT", "IN_PROGRESS", "RETURNED"];

const LEGAL_STAGES = [
  { value: "NOT_SENT", label: "Non soumis chez le notaire", short: "Non soumis" },
  { value: "AT_NOTARY", label: "Chez le notaire", short: "Chez notaire" },
  {
    value: "AWAITING_SIGNATURE",
    label: "En attente de signature",
    short: "Signature",
  },
  { value: "SIGNED", label: "Acte signé", short: "Signé" },
  {
    value: "PENDING_REGISTRATION",
    label: "Enregistrement / publicité en cours",
    short: "Enregistrement",
  },
  { value: "REGISTERED", label: "Enregistré", short: "Enregistré" },
  { value: "DONE", label: "Formalisation terminée", short: "Terminée" },
];

const LEGAL_STAGE_ORDER = LEGAL_STAGES.map((s) => s.value);

const FEE_TYPES = [
  { value: "NOTARY", label: "Notaire / acte" },
  { value: "REGISTRATION", label: "Enregistrement / publicité" },
  { value: "BAILIFF", label: "Huissier" },
  { value: "ADMIN", label: "Frais administratifs" },
  { value: "OTHER", label: "Divers" },
];

const DOC_CATS = [
  { value: "FORM_PROJET_ACTE", label: "Projet d'acte de constitution" },
  { value: "FORM_ACTE_SIGNE", label: "Acte de constitution signé" },
  { value: "FORM_ENREGISTREMENT", label: "Preuve d'enregistrement / publicité" },
  { value: "FORM_EXPERTISE", label: "Expertise / évaluation" },
  { value: "FORM_TITRE", label: "Titre / pièce du bien" },
  { value: "FORM_ID", label: "Pièce d'identité / quitus" },
  { value: "FORM_OTHER", label: "Autre pièce formalisation" },
];

const COMPLETABLE_STAGES = [
  "SIGNED",
  "PENDING_REGISTRATION",
  "REGISTERED",
  "DONE",
];

function legalStageLabel(value: string, display?: string) {
  return (
    display ||
    LEGAL_STAGES.find((s) => s.value === value)?.label ||
    value ||
    "—"
  );
}

function errMsg(err: unknown, fallback: string) {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  const raw =
    data && typeof data === "object" && "errors" in data
      ? (data as { errors: unknown }).errors
      : data;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) return raw.map(String).join(" · ");
  if (data && typeof data === "object") {
    const parts = Object.values(data as Record<string, unknown>)
      .flatMap((v) => (Array.isArray(v) ? v : [v]))
      .map(String)
      .filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  return fallback;
}

export function FormalizationsPage() {
  const navigate = useNavigate();
  const { user, activeTenant } = useAuth();
  const { clientFilter, clearClientFilter } = useClientSearchParam();
  const canInitiate = hasPerm(
    user,
    "guarantees.initiate_guaranteeformalizationrequest",
  );
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [legalStage, setLegalStage] = useState("");
  const [agency, setAgency] = useState("");

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  const list = useQuery({
    queryKey: [
      "guarantee-formalizations",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      search,
      status,
      legalStage,
      agency,
      clientFilter,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<GuaranteeFormalizationRequest>>(
          "/guarantee-formalizations/",
          {
            params: {
              page,
              page_size: LIST_PAGE_SIZE,
              ...(search.trim() ? { search: search.trim() } : {}),
              ...(status ? { status } : {}),
              ...(legalStage ? { legal_stage: legalStage } : {}),
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
          icon={Stamp}
          title="Formalisations"
          subtitle="Constitution juridique des garanties — parallèle au crédit"
          actions={
            canInitiate ? (
              <Link className="btn btn-primary" to="/formalisations/nouvelle">
                <Plus />
                Nouvelle formalisation
              </Link>
            ) : undefined
          }
        />

        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={setFilter(setSearch)}
              placeholder="Réf., notaire, n° enregistrement, client…"
            />
          }
          activeCount={countActive(
            search,
            status,
            legalStage,
            agency,
            clientFilter,
          )}
          onReset={() => {
            setSearch("");
            setStatus("");
            setLegalStage("");
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
          <FilterField label="Stade juridique" active={!!legalStage}>
            <FilterSelect
              value={legalStage}
              onChange={setFilter(setLegalStage)}
            >
              <option value="">Tous stades juridiques</option>
              <option value="NOT_SENT">Non soumis chez le notaire</option>
              <option value="AT_NOTARY">Chez le notaire</option>
              <option value="AWAITING_SIGNATURE">En attente de signature</option>
              <option value="SIGNED">Acte signé</option>
              <option value="PENDING_REGISTRATION">
                Enregistrement en cours
              </option>
              <option value="REGISTERED">Enregistré</option>
              <option value="DONE">Formalisation terminée</option>
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
          emptyMessage="Aucune formalisation ne correspond à ces critères."
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
                    <th>Étape juridique</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {(list.data?.results ?? []).map((r) => (
                    <tr
                      key={r.id}
                      className="row-clickable"
                      onClick={() => navigate(`/formalisations/${r.id}`)}
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
                        <Badge
                          value={r.legal_stage}
                          label={legalStageLabel(
                            r.legal_stage,
                            r.legal_stage_display,
                          )}
                        />
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

function CreditApplicationAutocomplete({
  value,
  onChange,
  initialLabel,
}: {
  value: string;
  onChange: (id: string, label: string, app?: CreditApplication | null) => void;
  initialLabel?: string;
}) {
  const [query, setQuery] = useState(initialLabel ?? "");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(Boolean(value));
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const { data, isFetching } = useQuery({
    queryKey: ["credit-apps-search-form", debounced],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditApplication>>("/credit-applications/", {
          params: { search: debounced, page_size: 8 },
        })
      ).data,
    enabled: open && debounced.length >= 1 && !selected,
  });

  function pick(app: CreditApplication) {
    const label = `${app.reference || app.id.slice(0, 8)} — ${app.client_display}`;
    setQuery(label);
    setSelected(true);
    setOpen(false);
    onChange(app.id, label, app);
  }

  function clear() {
    setQuery("");
    setSelected(false);
    onChange("", "", null);
  }

  return (
    <div className="client-ac" ref={ref}>
      <div className={`ac-input${selected ? " picked" : ""}`}>
        {selected ? <Check size={16} /> : <Search size={16} />}
        <input
          value={query}
          placeholder="Référence dossier, nom client…"
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(false);
            setOpen(true);
          }}
          onFocus={() => !selected && setOpen(true)}
        />
        {(query || value) && (
          <button type="button" className="ac-clear" onClick={clear}>
            <X size={14} />
          </button>
        )}
      </div>
      {open && !selected && debounced.length >= 1 && (
        <ul className="ac-dropdown">
          {isFetching && <li className="muted small">Recherche…</li>}
          {!isFetching && (data?.results.length ?? 0) === 0 && (
            <li className="muted small">Aucun dossier trouvé.</li>
          )}
          {(data?.results ?? []).map((app) => (
            <li key={app.id}>
              <button type="button" onClick={() => pick(app)}>
                <strong>{app.reference || app.id.slice(0, 8)}</strong>
                <span className="muted small">
                  {" "}
                  — {app.client_display} · {app.product_label}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function FormalizationNewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [searchMode, setSearchMode] = useState<"client" | "credit">(
    searchParams.get("application") ? "credit" : "client",
  );
  const [clientId, setClientId] = useState(searchParams.get("client") || "");
  const [applicationId, setApplicationId] = useState(
    searchParams.get("application") || "",
  );
  const [guaranteeId, setGuaranteeId] = useState(
    searchParams.get("guarantee") || "",
  );
  const [notaryName, setNotaryName] = useState("");
  const [notaryReference, setNotaryReference] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const contextParams = useMemo(() => {
    if (applicationId) return { application: applicationId };
    if (clientId) return { client: clientId };
    return null;
  }, [clientId, applicationId]);

  const context = useQuery({
    queryKey: ["formalization-compose-context", contextParams],
    queryFn: async () =>
      (
        await api.get<FormalizationComposeContext>(
          "/guarantee-formalizations/compose-context/",
          { params: contextParams! },
        )
      ).data,
    enabled: !!contextParams,
  });

  const credits = context.data?.credits ?? [];
  const allGuarantees = context.data?.guarantees ?? [];

  const visibleGuarantees = useMemo(() => {
    if (!applicationId) return allGuarantees;
    return allGuarantees.filter((g) => g.application === applicationId);
  }, [allGuarantees, applicationId]);

  useEffect(() => {
    const gParam = searchParams.get("guarantee");
    if (!gParam || !context.data) return;
    if (context.data.guarantees.some((g) => g.id === gParam)) {
      setGuaranteeId(gParam);
    }
  }, [context.data, searchParams]);

  useEffect(() => {
    if (!guaranteeId) return;
    if (!visibleGuarantees.some((g) => g.id === guaranteeId)) {
      setGuaranteeId("");
    }
  }, [visibleGuarantees, guaranteeId]);

  // Auto-sélection si un seul dossier / une seule garantie libre
  useEffect(() => {
    if (!context.data) return;
    if (!applicationId && context.data.credits.length === 1) {
      setApplicationId(context.data.credits[0].application_id);
    }
  }, [context.data, applicationId]);

  useEffect(() => {
    const free = visibleGuarantees.filter((g) => !g.formalization_busy);
    if (free.length === 1 && !guaranteeId) {
      setGuaranteeId(free[0].id);
    }
  }, [visibleGuarantees, guaranteeId]);

  const canSubmit = !!guaranteeId;

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<GuaranteeFormalizationRequest>(
          "/guarantee-formalizations/",
          {
            guarantee: guaranteeId,
            notary_name: notaryName,
            notary_reference: notaryReference,
            comment,
            as_draft: true,
          },
        )
      ).data,
    onSuccess: (data) => navigate(`/formalisations/${data.id}`),
    onError: (err: unknown) =>
      setError(
        errMsg(
          err,
          "Création impossible (garantie hors dossier ou formalisation ouverte).",
        ),
      ),
  });

  function resetSelection() {
    setGuaranteeId("");
    setError(null);
  }

  function onClientPicked(id: string) {
    setClientId(id);
    setApplicationId("");
    resetSelection();
  }

  function onCreditPicked(id: string, _label: string, app?: CreditApplication | null) {
    setApplicationId(id);
    if (app?.client) setClientId(app.client);
    resetSelection();
  }

  if (!hasPerm(user, "guarantees.initiate_guaranteeformalizationrequest")) {
    return (
      <div>
        <PageHeader icon={Stamp} title="Nouvelle formalisation" />
        <EmptyState message="Vous n'avez pas le droit d'initier une formalisation." />
      </div>
    );
  }

  return (
    <div className="page-shell dation-compose">
      <PageHeader
        icon={Stamp}
        title="Nouvelle formalisation"
        subtitle="Recherchez un client ou un dossier — les garanties attachées apparaissent automatiquement"
        actions={
          <Link className="btn btn-ghost" to="/formalisations">
            <ArrowLeft />
            Retour
          </Link>
        }
      />

      <div className="callout callout-info" style={{ marginBottom: 14 }}>
        La formalisation concerne uniquement les garanties mises en place sur
        un dossier de crédit. Elle suit un circuit juridique parallèle et ne
        bloque pas la mise en place du crédit.
      </div>

      <form
        className="dation-compose-form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (!canSubmit) return;
          setError(null);
          create.mutate();
        }}
      >
        <div className="dation-compose-layout">
          <div className="dation-compose-main">
            <section className="card form-section">
              <div className="card-title form-section-head">
                <span className="form-section-icon">
                  <Search size={18} />
                </span>
                <div className="form-section-heading">
                  <span className="form-section-title">1. Recherche</span>
                  <span className="form-section-desc">
                    Par client ou par dossier de crédit.
                  </span>
                </div>
              </div>
              <div className="type-toggle compact" style={{ marginBottom: 14 }}>
                <button
                  type="button"
                  className={`type-choice${searchMode === "client" ? " active" : ""}`}
                  onClick={() => {
                    setSearchMode("client");
                    setApplicationId("");
                    resetSelection();
                  }}
                >
                  <UserRound size={16} /> Client
                </button>
                <button
                  type="button"
                  className={`type-choice${searchMode === "credit" ? " active" : ""}`}
                  onClick={() => {
                    setSearchMode("credit");
                    resetSelection();
                  }}
                >
                  <FolderOpen size={16} /> Dossier de crédit
                </button>
              </div>
              {searchMode === "client" ? (
                <ClientAutocomplete
                  value={clientId}
                  onChange={(id) => onClientPicked(id)}
                />
              ) : (
                <CreditApplicationAutocomplete
                  value={applicationId}
                  onChange={onCreditPicked}
                />
              )}
            </section>

            {!contextParams ? (
              <section className="card form-section dation-compose-empty">
                <EmptyState message="Sélectionnez un client ou un dossier pour afficher les garanties attachées." />
              </section>
            ) : context.isLoading ? (
              <Spinner />
            ) : context.isError ? (
              <div className="form-error">
                Impossible de charger le contexte (client / dossier).
              </div>
            ) : (
              <>
                {searchMode === "client" && credits.length > 0 && (
                  <section className="card form-section">
                    <div className="card-title form-section-head">
                      <span className="form-section-icon">
                        <FolderOpen size={18} />
                      </span>
                      <div className="form-section-heading">
                        <span className="form-section-title">
                          2. Dossier de crédit
                        </span>
                        <span className="form-section-desc">
                          Filtrez sur le dossier dont les garanties seront
                          formalisées.
                        </span>
                      </div>
                    </div>
                    <div className="dation-guarantee-list" role="list">
                      {credits.map((c) => {
                        const checked = applicationId === c.application_id;
                        return (
                          <label
                            key={c.application_id}
                            role="listitem"
                            className={`dation-guarantee-row${checked ? " selected" : ""}`}
                          >
                            <input
                              type="radio"
                              name="formalization-credit"
                              checked={checked}
                              onChange={() => {
                                setApplicationId(c.application_id);
                                resetSelection();
                              }}
                            />
                            <span className="dation-guarantee-body">
                              <span className="dation-guarantee-title">
                                {c.application_reference ||
                                  c.application_id.slice(0, 8)}
                                <span className="muted small">
                                  {" "}
                                  — {c.product_label}
                                </span>
                              </span>
                              <span className="muted small">
                                {c.guarantees_count} garantie
                                {c.guarantees_count > 1 ? "s" : ""} attachée
                                {c.guarantees_count > 1 ? "s" : ""}
                              </span>
                            </span>
                            <span className="dation-guarantee-meta">
                              <strong>
                                {formatMoney(c.amount, c.currency)}
                              </strong>
                              <Badge
                                value={c.application_status}
                                label={c.application_status_display}
                              />
                            </span>
                          </label>
                        );
                      })}
                    </div>
                    {applicationId && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        style={{ marginTop: 8 }}
                        onClick={() => {
                          setApplicationId("");
                          resetSelection();
                        }}
                      >
                        Voir toutes les garanties du client
                      </button>
                    )}
                  </section>
                )}

                <section className="card form-section">
                  <div className="card-title form-section-head">
                    <span className="form-section-icon">
                      <FileSignature size={18} />
                    </span>
                    <div className="form-section-heading">
                      <span className="form-section-title">
                        {searchMode === "client" && credits.length > 0
                          ? "3. Garantie à formaliser"
                          : "2. Garantie à formaliser"}
                      </span>
                      <span className="form-section-desc">
                        Garanties attachées au dossier de crédit — sélectionnez
                        celle à mettre dans le circuit.
                      </span>
                    </div>
                    <div className="form-section-action">
                      <span className="muted small">
                        {visibleGuarantees.length} garantie
                        {visibleGuarantees.length > 1 ? "s" : ""}
                      </span>
                    </div>
                  </div>
                  {visibleGuarantees.length === 0 ? (
                    <EmptyState message="Aucune garantie active attachée à un dossier de crédit." />
                  ) : (
                    <div className="dation-guarantee-list" role="list">
                      {visibleGuarantees.map((g) => {
                        const busy = Boolean(
                          g.process_busy || g.formalization_busy,
                        );
                        const checked = guaranteeId === g.id;
                        return (
                          <label
                            key={g.id}
                            role="listitem"
                            className={`dation-guarantee-row${checked ? " selected" : ""}${busy ? " muted" : ""}`}
                          >
                            <input
                              type="radio"
                              name="formalization-guarantee"
                              checked={checked}
                              disabled={busy}
                              onChange={() => setGuaranteeId(g.id)}
                            />
                            <span className="dation-guarantee-body">
                              <span className="dation-guarantee-title">
                                {g.type_display}
                                <span className="muted small">
                                  {" "}
                                  —{" "}
                                  <code>
                                    {g.reference || g.id.slice(0, 8)}
                                  </code>
                                </span>
                              </span>
                              {g.application_reference && (
                                <span className="muted small">
                                  Dossier {g.application_reference}
                                </span>
                              )}
                              {g.description && (
                                <span className="dation-guarantee-desc">
                                  {g.description.slice(0, 140)}
                                </span>
                              )}
                              {busy && (
                                <span className="muted small">
                                  {g.process_busy?.label ||
                                    "Formalisation déjà ouverte"}
                                </span>
                              )}
                            </span>
                            <span className="dation-guarantee-meta">
                              <strong>{formatMoney(g.current_value)}</strong>
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
                      <Stamp size={18} />
                    </span>
                    <div className="form-section-heading">
                      <span className="form-section-title">
                        Notaire & commentaire
                      </span>
                      <span className="form-section-desc">
                        Optionnel à la création — modifiable ensuite.
                      </span>
                    </div>
                  </div>
                  <div className="form-grid">
                    <label className="field">
                      <span>Notaire / étude</span>
                      <input
                        value={notaryName}
                        onChange={(e) => setNotaryName(e.target.value)}
                        placeholder="Optionnel"
                      />
                    </label>
                    <label className="field">
                      <span>Réf. dossier notaire</span>
                      <input
                        value={notaryReference}
                        onChange={(e) => setNotaryReference(e.target.value)}
                        placeholder="Optionnel"
                      />
                    </label>
                    <label className="field" style={{ gridColumn: "1 / -1" }}>
                      <span>Commentaire</span>
                      <textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        rows={3}
                        placeholder="Observations, pièces à prévoir…"
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
                <Stamp size={18} />
                <strong>Récapitulatif</strong>
              </div>
              {!contextParams ? (
                <p className="muted small">
                  Recherchez un client ou un dossier.
                </p>
              ) : (
                <dl className="def-list">
                  <div>
                    <dt>Client</dt>
                    <dd>{context.data?.client_display || "…"}</dd>
                  </div>
                  <div>
                    <dt>Dossiers</dt>
                    <dd>{credits.length}</dd>
                  </div>
                  <div>
                    <dt>Garanties attachées</dt>
                    <dd>{visibleGuarantees.length}</dd>
                  </div>
                  <div>
                    <dt>Sélection</dt>
                    <dd>
                      {guaranteeId
                        ? visibleGuarantees.find((g) => g.id === guaranteeId)
                            ?.reference || guaranteeId.slice(0, 8)
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
                {create.isPending ? "Création…" : "Mettre dans le circuit"}
              </button>
              <Link className="btn btn-ghost" to="/formalisations">
                Annuler
              </Link>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
}

export function FormalizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { user } = useAuth();
  const canInitiate = hasPerm(
    user,
    "guarantees.initiate_guaranteeformalizationrequest",
  );

  const [feeType, setFeeType] = useState("NOTARY");
  const [feeAmount, setFeeAmount] = useState("");
  const [feePayer, setFeePayer] = useState("CLIENT");
  const [feeLabel, setFeeLabel] = useState("");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docName, setDocName] = useState("");
  const [docCat, setDocCat] = useState("FORM_PROJET_ACTE");
  const [actionError, setActionError] = useState<string | null>(null);

  const [draftNotaryName, setDraftNotaryName] = useState("");
  const [draftNotaryRef, setDraftNotaryRef] = useState("");
  const [draftSentAt, setDraftSentAt] = useState("");
  const [draftExpectedReturn, setDraftExpectedReturn] = useState("");
  const [draftRegNumber, setDraftRegNumber] = useState("");
  const [draftRegDate, setDraftRegDate] = useState("");
  const [draftRegAuth, setDraftRegAuth] = useState("");
  const [draftComment, setDraftComment] = useState("");
  const [draftSynced, setDraftSynced] = useState(false);

  const [advanceStage, setAdvanceStage] = useState("");
  const [advanceNotaryName, setAdvanceNotaryName] = useState("");
  const [advanceNotaryRef, setAdvanceNotaryRef] = useState("");
  const [advanceRegNumber, setAdvanceRegNumber] = useState("");
  const [advanceRegDate, setAdvanceRegDate] = useState("");
  const [advanceRegAuth, setAdvanceRegAuth] = useState("");

  const detail = useQuery({
    queryKey: ["guarantee-formalization", id],
    queryFn: async () =>
      (
        await api.get<GuaranteeFormalizationRequest>(
          `/guarantee-formalizations/${id}/`,
        )
      ).data,
    enabled: !!id,
  });

  useEffect(() => {
    setDraftSynced(false);
  }, [id]);

  useEffect(() => {
    if (!detail.data || draftSynced) return;
    const d = detail.data;
    setDraftNotaryName(d.notary_name || "");
    setDraftNotaryRef(d.notary_reference || "");
    setDraftSentAt(d.sent_to_notary_at || "");
    setDraftExpectedReturn(d.expected_return_date || "");
    setDraftRegNumber(d.registration_number || "");
    setDraftRegDate(d.registration_date || "");
    setDraftRegAuth(d.registration_authority || "");
    setDraftComment(d.comment || "");
    setAdvanceStage(d.legal_stage || "NOT_SENT");
    setAdvanceNotaryName(d.notary_name || "");
    setAdvanceNotaryRef(d.notary_reference || "");
    setAdvanceRegNumber(d.registration_number || "");
    setAdvanceRegDate(d.registration_date || "");
    setAdvanceRegAuth(d.registration_authority || "");
    setDraftSynced(true);
  }, [detail.data, draftSynced]);

  const docs = useQuery({
    queryKey: ["guarantee-formalization-docs", id],
    queryFn: async () =>
      (
        await api.get<GedDocument[]>(
          `/guarantee-formalizations/${id}/documents/`,
        )
      ).data,
    enabled: !!id,
  });

  const workflow = useQuery({
    queryKey: ["guarantee-formalization-workflow", id],
    queryFn: async () =>
      (
        await api.get<{
          instance: { status: string; definition_code?: string } | null;
        }>(`/guarantee-formalizations/${id}/workflow/`)
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
    qc.invalidateQueries({ queryKey: ["guarantee-formalization", id] });
    qc.invalidateQueries({ queryKey: ["guarantee-formalization-docs", id] });
    qc.invalidateQueries({
      queryKey: ["guarantee-formalization-workflow", id],
    });
    qc.invalidateQueries({ queryKey: ["guarantee-formalizations"] });
    qc.invalidateQueries({ queryKey: ["guarantees"] });
    qc.invalidateQueries({ queryKey: ["guarantee"] });
    setDraftSynced(false);
  }

  const updateDraft = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/guarantee-formalizations/${id}/update-draft/`, {
          notary_name: draftNotaryName,
          notary_reference: draftNotaryRef,
          sent_to_notary_at: draftSentAt || null,
          expected_return_date: draftExpectedReturn || null,
          registration_number: draftRegNumber,
          registration_date: draftRegDate || null,
          registration_authority: draftRegAuth,
          comment: draftComment,
        })
      ).data,
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Mise à jour impossible.")),
  });

  const start = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-formalizations/${id}/start/`)).data,
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Démarrage impossible.")),
  });

  const advance = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = { legal_stage: advanceStage };
      if (advanceNotaryName) body.notary_name = advanceNotaryName;
      if (advanceNotaryRef) body.notary_reference = advanceNotaryRef;
      if (advanceRegNumber) body.registration_number = advanceRegNumber;
      if (advanceRegDate) body.registration_date = advanceRegDate;
      if (advanceRegAuth) body.registration_authority = advanceRegAuth;
      return (
        await api.post(
          `/guarantee-formalizations/${id}/advance-stage/`,
          body,
        )
      ).data;
    },
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) =>
      setActionError(errMsg(e, "Avancement de l'étape impossible.")),
  });

  const submit = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-formalizations/${id}/submit/`)).data,
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Soumission impossible.")),
  });

  const cancel = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/guarantee-formalizations/${id}/cancel/`, {
          comment: "Annulé",
        })
      ).data,
    onSuccess: () => invalidateAll(),
    onError: (e) => setActionError(errMsg(e, "Annulation impossible.")),
  });

  const complete = useMutation({
    mutationFn: async () =>
      (await api.post(`/guarantee-formalizations/${id}/complete/`)).data,
    onSuccess: () => {
      setActionError(null);
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Clôture impossible.")),
  });

  const addFee = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/guarantee-formalizations/${id}/add-fee/`, {
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
      (
        await api.post(
          `/guarantee-formalizations/${id}/remove-fee/${feeId}/`,
        )
      ).data,
    onSuccess: () => invalidateAll(),
  });

  const uploadDoc = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (docFile) fd.append("file", docFile);
      fd.append("name", docName || docFile?.name || "Document");
      fd.append("category", docCat);
      return (
        await api.post(`/guarantee-formalizations/${id}/documents/`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      ).data;
    },
    onSuccess: () => {
      setDocFile(null);
      setDocName("");
      invalidateAll();
    },
    onError: (e) => setActionError(errMsg(e, "Upload impossible.")),
  });

  if (detail.isLoading) return <Spinner />;
  if (detail.isError || !detail.data)
    return (
      <ErrorState
        message="Impossible de charger la formalisation."
        onRetry={() => detail.refetch()}
      />
    );
  const r = detail.data;
  const editable = EDITABLE_STATUSES.includes(r.status);
  const canCancel =
    canInitiate &&
    ["DRAFT", "IN_PROGRESS", "RETURNED", "IN_APPROVAL"].includes(r.status);
  const canStart =
    canInitiate && ["DRAFT", "RETURNED"].includes(r.status);
  const canSubmit =
    canInitiate &&
    ["DRAFT", "IN_PROGRESS", "RETURNED"].includes(r.status);
  const canComplete =
    canInitiate &&
    r.status === "APPROVED" &&
    COMPLETABLE_STAGES.includes(r.legal_stage);
  const canUploadDocs =
    canInitiate &&
    !["COMPLETED", "CANCELLED", "REJECTED"].includes(r.status);
  const myTask =
    myTasks?.results.find(
      (t) =>
        t.target_meta?.kind === "FORMALISATION" && t.target_meta.id === r.id,
    ) ?? null;
  const fees: FormalizationFee[] = r.fees ?? [];
  const stageIdx = LEGAL_STAGE_ORDER.indexOf(r.legal_stage);
  const closed =
    r.status === "COMPLETED" || r.legal_stage === "DONE";
  const cancelled = ["CANCELLED", "REJECTED"].includes(r.status);
  const proofLinks = [
    r.acte_file_url
      ? { label: "Projet / acte", href: r.acte_file_url }
      : null,
    r.acte_signed_file_url
      ? { label: "Acte signé", href: r.acte_signed_file_url }
      : null,
    r.registration_proof_url
      ? { label: "Preuve d'enregistrement", href: r.registration_proof_url }
      : null,
  ].filter(Boolean) as { label: string; href: string }[];

  return (
    <div className="page-shell detail-banner-page">
      <div className="client-banner">
        <div className="client-banner-main">
          <div className="client-banner-info">
            <span className="client-banner-icon">
              <Stamp size={26} />
            </span>
            <div className="client-banner-identity">
              <h2 className="client-banner-name">
                {r.client_display || "Formalisation"}
              </h2>
              <p className="client-banner-ref">
                Formalisation <code>{r.reference || "—"}</code>
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
                    fallback={
                      r.application_reference ? (
                        <span className="muted">
                          · Crédit {r.application_reference}
                        </span>
                      ) : null
                    }
                  >
                    · Dossier crédit{" "}
                    {r.application_reference || r.application.slice(0, 8)}
                  </PermLink>
                )}
              </p>
              <div className="client-banner-meta">
                <Badge value={r.status} label={r.status_display} />
                <Badge
                  value={r.legal_stage}
                  label={legalStageLabel(r.legal_stage, r.legal_stage_display)}
                />
              </div>
            </div>
          </div>

          <div className="client-banner-actions">
            <Link className="btn btn-banner" to="/formalisations">
              <ArrowLeft size={15} />
              Retour
            </Link>
            {canStart && (
              <button
                type="button"
                className="btn btn-banner"
                onClick={() => start.mutate()}
                disabled={start.isPending}
              >
                Démarrer
              </button>
            )}
            {canCancel && (
              <button
                type="button"
                className="btn btn-banner btn-banner-danger"
                onClick={() => {
                  if (
                    r.status === "IN_APPROVAL" &&
                    !window.confirm(
                      "Annuler cette formalisation en cours de validation ? Le circuit sera interrompu.",
                    )
                  ) {
                    return;
                  }
                  cancel.mutate();
                }}
                disabled={cancel.isPending}
              >
                Annuler
              </button>
            )}
            {canComplete && (
              <button
                type="button"
                className="btn btn-banner btn-banner-primary"
                onClick={() => {
                  if (
                    !window.confirm(
                      "Clôturer cette formalisation et reporter les preuves sur la garantie ?",
                    )
                  ) {
                    return;
                  }
                  complete.mutate();
                }}
                disabled={complete.isPending}
              >
                Clôturer
              </button>
            )}
            {canSubmit && (
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

      {r.status === "IN_APPROVAL" && !myTask && (
        <div className="muted small" style={{ marginBottom: 12 }}>
          Dossier en circuit de validation. Vous pouvez encore l&apos;annuler si
          besoin.
        </div>
      )}

      <div className="process-steps" aria-label="Parcours juridique">
        {LEGAL_STAGES.map((s, i) => {
          const done =
            !cancelled && (closed || (stageIdx >= 0 && i < stageIdx));
          const current =
            !cancelled && !closed && stageIdx === i;
          return (
            <div
              key={s.value}
              className={`process-step${done ? " done" : ""}${
                current ? " current" : ""
              }`}
            >
              <span className="step-num">{i + 1}</span>
              <span>
                <strong>{s.short}</strong>
                {current ? "En cours" : done ? "Fait" : "À venir"}
              </span>
            </div>
          );
        })}
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
                <dt>Étape juridique</dt>
                <dd>
                  <Badge
                    value={r.legal_stage}
                    label={legalStageLabel(
                      r.legal_stage,
                      r.legal_stage_display,
                    )}
                  />
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
                <dd>
                  {r.client ? (
                    <PermLink
                      user={user}
                      anyOf={PERM_CLIENTS}
                      to={`/clients/${r.client}`}
                    >
                      {r.client_display}
                    </PermLink>
                  ) : (
                    r.client_display || "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Dossier crédit</dt>
                <dd>
                  {r.application ? (
                    <PermLink
                      user={user}
                      anyOf={PERM_CREDITS}
                      to={`/dossiers/${r.application}`}
                    >
                      {r.application_reference || r.application.slice(0, 8)}
                    </PermLink>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Créée le</dt>
                <dd>{formatDate(r.created_at)}</dd>
              </div>
              <div>
                <dt>Frais client</dt>
                <dd>{formatMoney(r.fees_client_total ?? null)}</dd>
              </div>
              <div>
                <dt>Frais institution</dt>
                <dd>{formatMoney(r.fees_institution_total ?? null)}</dd>
              </div>
              {r.completed_at && (
                <div>
                  <dt>Clôturée le</dt>
                  <dd>{formatDate(r.completed_at)}</dd>
                </div>
              )}
            </dl>
            {!editable && r.comment && (
              <p className="muted small" style={{ marginTop: 12 }}>
                {r.comment}
              </p>
            )}
          </Card>

          <Card
            title={
              <>
                <Scale size={17} /> Circuit
              </>
            }
          >
            {!workflow.data?.instance ? (
              <EmptyState
                message={
                  editable
                    ? "Circuit non démarré — soumettez le dossier."
                    : "Aucun circuit associé."
                }
              />
            ) : (
              <dl className="def-list two">
                <div>
                  <dt>Statut circuit</dt>
                  <dd>
                    <Badge value={workflow.data.instance.status} />
                  </dd>
                </div>
                {workflow.data.instance.definition_code && (
                  <div>
                    <dt>Définition</dt>
                    <dd>
                      <code>{workflow.data.instance.definition_code}</code>
                    </dd>
                  </div>
                )}
              </dl>
            )}
            {myTask && (
              <div style={{ marginTop: 14 }}>
                <p className="section-subtitle">
                  <Gavel size={14} /> Décision — {myTask.step_name}
                </p>
                <DecisionPanel task={myTask} onDone={invalidateAll} />
              </div>
            )}
          </Card>
        </div>

        <div className="detail-sections-row">
          <Card
            title={
              <>
                <Building2 size={17} /> Notaire &amp; enregistrement
              </>
            }
          >
            {editable && canInitiate ? (
              <div className="form-grid">
                <label className="field">
                  <span>Notaire / étude</span>
                  <input
                    value={draftNotaryName}
                    onChange={(e) => setDraftNotaryName(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Réf. dossier notaire</span>
                  <input
                    value={draftNotaryRef}
                    onChange={(e) => setDraftNotaryRef(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Transmis au notaire le</span>
                  <input
                    type="date"
                    value={draftSentAt}
                    onChange={(e) => setDraftSentAt(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Retour prévu</span>
                  <input
                    type="date"
                    value={draftExpectedReturn}
                    onChange={(e) => setDraftExpectedReturn(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>N° d&apos;enregistrement</span>
                  <input
                    value={draftRegNumber}
                    onChange={(e) => setDraftRegNumber(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Date d&apos;enregistrement</span>
                  <input
                    type="date"
                    value={draftRegDate}
                    onChange={(e) => setDraftRegDate(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Organisme</span>
                  <input
                    value={draftRegAuth}
                    onChange={(e) => setDraftRegAuth(e.target.value)}
                  />
                </label>
                <label className="field" style={{ gridColumn: "1 / -1" }}>
                  <span>Commentaire</span>
                  <textarea
                    value={draftComment}
                    onChange={(e) => setDraftComment(e.target.value)}
                    rows={3}
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={updateDraft.isPending}
                  onClick={() => updateDraft.mutate()}
                >
                  Enregistrer
                </button>
              </div>
            ) : (
              <dl className="def-list two">
                <div>
                  <dt>Notaire</dt>
                  <dd>{r.notary_name || "—"}</dd>
                </div>
                <div>
                  <dt>Réf. notaire</dt>
                  <dd>{r.notary_reference || "—"}</dd>
                </div>
                <div>
                  <dt>Transmis le</dt>
                  <dd>
                    {r.sent_to_notary_at
                      ? formatDate(r.sent_to_notary_at)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Retour prévu</dt>
                  <dd>
                    {r.expected_return_date
                      ? formatDate(r.expected_return_date)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>N° enregistrement</dt>
                  <dd>{r.registration_number || "—"}</dd>
                </div>
                <div>
                  <dt>Date enregistrement</dt>
                  <dd>
                    {r.registration_date
                      ? formatDate(r.registration_date)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Organisme</dt>
                  <dd>{r.registration_authority || "—"}</dd>
                </div>
              </dl>
            )}
          </Card>

          <Card
            title={
              <>
                <Landmark size={17} /> Avancer l&apos;étape
              </>
            }
          >
            {editable && canInitiate ? (
              <>
                <p className="muted small">
                  Faites progresser le parcours juridique. Les champs
                  contextuels s&apos;affichent selon l&apos;étape choisie.
                </p>
                <div className="form-grid" style={{ marginTop: 10 }}>
                  <label className="field full-span">
                    <span>Nouvelle étape</span>
                    <select
                      value={advanceStage}
                      onChange={(e) => setAdvanceStage(e.target.value)}
                    >
                      {LEGAL_STAGES.filter((s) => s.value !== "DONE").map(
                        (s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  {(advanceStage === "AT_NOTARY" ||
                    advanceStage === "AWAITING_SIGNATURE") && (
                    <>
                      <label className="field">
                        <span>Notaire / étude</span>
                        <input
                          value={advanceNotaryName}
                          onChange={(e) =>
                            setAdvanceNotaryName(e.target.value)
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Réf. notaire</span>
                        <input
                          value={advanceNotaryRef}
                          onChange={(e) =>
                            setAdvanceNotaryRef(e.target.value)
                          }
                        />
                      </label>
                    </>
                  )}
                  {(advanceStage === "PENDING_REGISTRATION" ||
                    advanceStage === "REGISTERED") && (
                    <>
                      <label className="field">
                        <span>N° d&apos;enregistrement</span>
                        <input
                          value={advanceRegNumber}
                          onChange={(e) =>
                            setAdvanceRegNumber(e.target.value)
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Date d&apos;enregistrement</span>
                        <input
                          type="date"
                          value={advanceRegDate}
                          onChange={(e) => setAdvanceRegDate(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Organisme</span>
                        <input
                          value={advanceRegAuth}
                          onChange={(e) => setAdvanceRegAuth(e.target.value)}
                        />
                      </label>
                    </>
                  )}
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={
                      !advanceStage ||
                      advanceStage === r.legal_stage ||
                      advance.isPending
                    }
                    onClick={() => advance.mutate()}
                  >
                    Avancer l&apos;étape
                  </button>
                </div>
              </>
            ) : (
              <dl className="def-list two">
                <div>
                  <dt>Étape actuelle</dt>
                  <dd>
                    {legalStageLabel(r.legal_stage, r.legal_stage_display)}
                  </dd>
                </div>
                <div>
                  <dt>Modification</dt>
                  <dd className="muted">
                    {cancelled
                      ? "Dossier clôturé / annulé"
                      : closed
                        ? "Parcours terminé"
                        : "Lecture seule (en validation)"}
                  </dd>
                </div>
              </dl>
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
                      <span className="num">{formatMoney(f.amount)}</span>
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
                    {FEE_TYPES.map((t) => (
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
                <ScrollText size={17} /> Pièces &amp; preuves
              </>
            }
          >
            {proofLinks.length > 0 && (
              <ul className="link-list" style={{ marginBottom: 10 }}>
                {proofLinks.map((p) => (
                  <li
                    key={p.href}
                    className="row-clickable"
                    onClick={() =>
                      window.open(p.href, "_blank", "noopener,noreferrer")
                    }
                  >
                    <span>
                      <FileSignature size={14} /> {p.label}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {(docs.data ?? []).length === 0 && proofLinks.length === 0 ? (
              <p className="muted small">Aucune pièce jointe.</p>
            ) : (docs.data ?? []).length > 0 ? (
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
            ) : null}
            {canUploadDocs && (
              <div className="form-grid" style={{ marginTop: 12 }}>
                <label className="field">
                  <span>Fichier</span>
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,.tiff,.docx"
                    onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                <label className="field">
                  <span>Nom</span>
                  <input
                    value={docName}
                    onChange={(e) => setDocName(e.target.value)}
                    placeholder="Optionnel"
                  />
                </label>
                <label className="field">
                  <span>Catégorie</span>
                  <select
                    value={docCat}
                    onChange={(e) => setDocCat(e.target.value)}
                  >
                    {DOC_CATS.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!docFile || uploadDoc.isPending}
                  onClick={() => uploadDoc.mutate()}
                >
                  <FileUp size={14} />
                  Joindre
                </button>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
