import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Search,
  TriangleAlert,
  UserRound,
  X,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { Client } from "@/api/types";

type ClientType = "INDIVIDUAL" | "CORPORATE";
type Criterion =
  | "code_adherent"
  | "num_manuel"
  | "num_piece_identite"
  | "identification_nationale"
  | "num_carte_operateur";

type CbsIssue = {
  key: string;
  label: string;
  reason?: "missing" | "invalid" | "expired";
};

export type CbsPreview = {
  client_type?: ClientType;
  missing_required?: CbsIssue[];
  can_import?: boolean;
  import_block_message?: string;
  full_name: string;
  last_name?: string;
  first_name?: string;
  company_name?: string;
  sigle?: string;
  code_adherent: string;
  num_manuel: string;
  num_piece_identite: string;
  identification_nationale: string;
  num_carte_operateur?: string;
  num_ordre?: string;
  birth_date?: string;
  birth_place?: string;
  civility?: string;
  marital_status?: string;
  spouse_name?: string;
  id_document_issue_date?: string;
  id_document_expiry_date?: string;
  id_profession?: string;
  profession?: string;
  id_nationalite?: string;
  nationality?: string;
  date_creation?: string;
  head_office?: string;
  id_secteur_activite?: string;
  id_type_client?: string;
  id_zone?: string;
  id_produit_epg?: string;
  nbre_signature?: number | string | null;
  distance?: number | string | null;
  phone: string;
  email: string;
  boite_postale: string;
  city: string;
  address: string;
  date_inscription: string;
  limit_credit: string | null;
  est_valide: boolean;
  id_point_service: string;
  nom_point_service: string;
  context?: string;
  message?: string;
  kyc_alert: boolean;
};

function apiError(err: unknown): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })
    ?.response?.data;
  if (!data) return "Échec de l'appel CBS.";
  const nested = data.errors as
    | { detail?: unknown; client_type?: unknown }
    | undefined;
  const detail = nested?.detail ?? data.detail ?? nested?.client_type;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(String).join(" ");
  for (const v of Object.values(data)) {
    if (typeof v === "string") return v;
    if (Array.isArray(v)) return v.map(String).join(" ");
  }
  return "Échec de l'appel CBS.";
}

function isBlankPreview(value: string | number | null | undefined) {
  if (value === 0) return false;
  const text = String(value ?? "").trim();
  if (!text) return true;
  return ["N/A", "NA", "EMPTY"].includes(text.toUpperCase());
}

function PreviewFields({
  rows,
  missingKeys,
}: {
  rows: ReadonlyArray<
    readonly [string, string, string | number | null | undefined]
  >;
  missingKeys: Set<string>;
}) {
  return (
    <div className="cbs-preview-grid">
      {rows.map(([key, label, value]) => {
        const missing = missingKeys.has(key);
        const empty = isBlankPreview(value);
        return (
          <div
            className={`cbs-preview-item${missing ? " is-missing" : ""}`}
            key={key}
          >
            <span>{label}</span>
            <strong>{empty ? "—" : String(value)}</strong>
          </div>
        );
      })}
    </div>
  );
}

function commonCbsRows(preview: CbsPreview) {
  return [
    ["code_adherent", "Code adhérent", preview.code_adherent],
    ["num_manuel", "N° de compte (n° manuel)", preview.num_manuel],
    ["full_name", "Nom adhérent CBS", preview.full_name],
    ["num_ordre", "N° d'ordre CBS", preview.num_ordre],
    ["id_point_service", "Code point de service", preview.id_point_service],
    ["nom_point_service", "Libellé point de service", preview.nom_point_service],
    ["date_inscription", "Date d'inscription CBS", preview.date_inscription],
    ["date_creation", "Date de création CBS", preview.date_creation],
    ["limit_credit", "Limite de crédit CBS", preview.limit_credit],
    [
      "est_valide",
      "Adhérent valide CBS",
      preview.est_valide ? "Oui" : "Non",
    ],
    ["id_profession", "Id profession CBS", preview.id_profession],
    ["id_nationalite", "Id nationalité CBS", preview.id_nationalite],
    ["id_secteur_activite", "Id secteur d'activité CBS", preview.id_secteur_activite],
    ["id_type_client", "Id type client CBS", preview.id_type_client],
    ["id_zone", "Id zone CBS", preview.id_zone],
    ["id_produit_epg", "Id produit épargne CBS", preview.id_produit_epg],
    ["nbre_signature", "Nombre de signatures CBS", preview.nbre_signature],
    ["distance", "Distance CBS", preview.distance],
    ["phone", "Téléphone", preview.phone],
    ["email", "E-mail", preview.email],
    ["address", "Adresse", preview.address],
    ["head_office", "Siège social", preview.head_office],
    ["city", "Ville", preview.city],
    ["boite_postale", "Boîte postale", preview.boite_postale],
    ["context", "Contexte réponse CBS", preview.context],
    ["message", "Message réponse CBS", preview.message],
  ] as const;
}

const PHYSICAL_CRITERIA: { value: Criterion; label: string; placeholder: string }[] =
  [
    { value: "code_adherent", label: "Code adhérent", placeholder: "A0012345" },
    { value: "num_manuel", label: "N° dossier manuel", placeholder: "M00987" },
    {
      value: "num_piece_identite",
      label: "N° pièce d'identité",
      placeholder: "CI1234567890",
    },
  ];

const CORPORATE_CRITERIA: { value: Criterion; label: string; placeholder: string }[] =
  [
    { value: "code_adherent", label: "Code adhérent", placeholder: "E0012345" },
    { value: "num_manuel", label: "N° dossier manuel", placeholder: "M00987" },
    {
      value: "identification_nationale",
      label: "Identification nationale (IFU)",
      placeholder: "IFU…",
    },
    {
      value: "num_carte_operateur",
      label: "N° carte / RCCM",
      placeholder: "RCCM…",
    },
  ];

export function ClientCbsImportForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: (client: Client) => void;
  onCancel: () => void;
}) {
  const qc = useQueryClient();
  const [clientType, setClientType] = useState<ClientType>("INDIVIDUAL");
  const [criterion, setCriterion] = useState<Criterion>("code_adherent");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<CbsPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isCorporate = clientType === "CORPORATE";
  const criteria = isCorporate ? CORPORATE_CRITERIA : PHYSICAL_CRITERIA;
  const current = useMemo(
    () => criteria.find((c) => c.value === criterion) ?? criteria[0],
    [criteria, criterion],
  );

  function payload() {
    const value = query.trim();
    return {
      client_type: clientType,
      [current.value]: value,
    };
  }

  const lookup = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<CbsPreview>(
        "/clients/cbs-preview/",
        payload(),
      );
      return data;
    },
    onSuccess: (data) => {
      setPreview(data);
      setError(null);
    },
    onError: (err) => {
      setPreview(null);
      setError(apiError(err));
    },
  });

  const save = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Client & { kyc_alert?: boolean }>(
        "/clients/cbs-import/",
        {
          ...payload(),
          code_adherent:
            (criterion === "code_adherent" ? query.trim() : "") ||
            preview?.code_adherent,
        },
      );
      return data;
    },
    onSuccess: (client) => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      onSuccess(client);
    },
    onError: (err) => setError(apiError(err)),
  });

  function onLookup(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) {
      setError(`Saisissez un ${current.label.toLowerCase()}.`);
      return;
    }
    lookup.mutate();
  }

  function resetSearch() {
    setPreview(null);
    setError(null);
    setQuery("");
  }

  function chooseType(value: ClientType) {
    if (clientType === value) return;
    setClientType(value);
    setCriterion("code_adherent");
    resetSearch();
  }

  const missingIssues = preview?.missing_required ?? [];
  const missingKeys = new Set(missingIssues.map((issue) => issue.key));
  const canImport = preview?.can_import !== false && missingIssues.length === 0;
  const blockMessage =
    preview?.import_block_message ||
    (missingIssues.length
      ? `Impossible d'enregistrer ce client dans FinFlow : des informations obligatoires sont absentes ou incorrectes dans le CBS (${missingIssues
          .map((issue) => issue.label)
          .join(", ")}). Mettez à jour ces données dans le core banking, puis relancez la recherche.`
      : null);

  const physicalRows = preview
    ? ([
        ["last_name", "Nom", preview.last_name],
        ["first_name", "Prénoms", preview.first_name],
        ["civility", "Civilité", preview.civility],
        ["birth_date", "Date de naissance", preview.birth_date],
        ["birth_place", "Lieu de naissance", preview.birth_place],
        ["marital_status", "Statut matrimonial", preview.marital_status],
        ["spouse_name", "Conjoint", preview.spouse_name],
        ["num_piece_identite", "Pièce d'identité", preview.num_piece_identite],
        [
          "id_document_issue_date",
          "Établissement pièce",
          preview.id_document_issue_date,
        ],
        [
          "id_document_expiry_date",
          "Expiration pièce",
          preview.id_document_expiry_date,
        ],
        ["profession", "Profession", preview.profession],
        ["nationality", "Nationalité", preview.nationality],
        ...commonCbsRows(preview),
      ] as const)
    : [];

  const corporateRows = preview
    ? ([
        ["company_name", "Raison sociale", preview.company_name],
        ["sigle", "Sigle", preview.sigle],
        [
          "identification_nationale",
          "Identification nationale (IFU)",
          preview.identification_nationale,
        ],
        [
          "num_carte_operateur",
          "N° carte / RCCM",
          preview.num_carte_operateur,
        ],
        ...commonCbsRows(preview),
      ] as const)
    : [];

  return (
    <div className="cbs-import">
      <form className="cbs-search" onSubmit={onLookup} aria-label="Recherche CBS">
        <div
          className="cbs-search-segment"
          role="group"
          aria-label="Type de client"
        >
          <button
            type="button"
            className={clientType === "INDIVIDUAL" ? "is-on" : undefined}
            onClick={() => chooseType("INDIVIDUAL")}
          >
            <UserRound size={15} />
            Physique
          </button>
          <button
            type="button"
            className={clientType === "CORPORATE" ? "is-on" : undefined}
            onClick={() => chooseType("CORPORATE")}
          >
            <Building2 size={15} />
            Morale
          </button>
        </div>

        <label className="cbs-search-criterion">
          <span className="visually-hidden">Rechercher par</span>
          <select
            value={current.value}
            onChange={(e) => {
              setCriterion(e.target.value as Criterion);
              setPreview(null);
              setError(null);
            }}
            disabled={Boolean(preview)}
          >
            {criteria.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <div className={`cbs-search-field${query ? " has-value" : ""}`}>
          <Search size={16} />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={current.placeholder}
            disabled={Boolean(preview)}
            autoFocus
          />
          {query && !preview && (
            <button
              type="button"
              className="cbs-search-clear"
              aria-label="Effacer"
              onClick={() => setQuery("")}
            >
              <X size={14} />
            </button>
          )}
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={lookup.isPending || Boolean(preview)}
        >
          {lookup.isPending ? "Recherche…" : "Rechercher"}
        </button>
      </form>

      {error && (
        <div className="notice-warning">
          <TriangleAlert size={18} />
          <span>{error}</span>
        </div>
      )}

      {preview && (
        <section className="cbs-preview-card" aria-label="Prévisualisation CBS">
          {blockMessage && (
            <div className="notice-error" role="alert">
              <TriangleAlert size={18} />
              <span>{blockMessage}</span>
            </div>
          )}
          {preview.kyc_alert && canImport && (
            <div className="notice-warning">
              <TriangleAlert size={18} />
              <span>
                Compte CBS signalé comme non valide. L&apos;enregistrement reste
                possible : le KYC sera placé en alerte (à vérifier).
              </span>
            </div>
          )}
          <header className="cbs-preview-head">
            <h4>
              {isCorporate ? <Building2 size={16} /> : <UserRound size={16} />}
              {preview.company_name ||
                preview.full_name ||
                "Prévisualisation CBS"}
            </h4>
            <span className="filters-panel-badge">
              {isCorporate ? "Personne morale" : "Personne physique"}
            </span>
          </header>
          <PreviewFields
            rows={isCorporate ? corporateRows : physicalRows}
            missingKeys={
              missingKeys.has("address")
                ? new Set([...missingKeys, "head_office"])
                : missingKeys
            }
          />
          <div className="credit-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={save.isPending || !canImport}
              onClick={() => save.mutate()}
            >
              {save.isPending ? "Enregistrement…" : "Enregistrer le client"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={resetSearch}>
              Nouvelle recherche
            </button>
            <button type="button" className="btn btn-ghost" onClick={onCancel}>
              Annuler
            </button>
          </div>
        </section>
      )}

      {!preview && (
        <div className="credit-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Annuler
          </button>
        </div>
      )}
    </div>
  );
}
