import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Banknote,
  Car,
  ExternalLink,
  Gem,
  Images,
  Landmark,
  Plus,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  UploadCloud,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { Guarantee } from "@/api/types";
import {
  FreeDocumentsEditor,
  appendFreeDocuments,
  type FreeDocumentDraft,
} from "@/components/FreeDocumentsEditor";
import { SuretyAutocomplete } from "@/components/SuretyAutocomplete";
import { Card } from "@/components/ui";

const CATEGORIES = [
  {
    value: "MORTGAGE",
    label: "Hypothèque",
    hint: "Garantie réelle immobilière",
    icon: Landmark,
  },
  {
    value: "PLEDGE",
    label: "Gage",
    hint: "Garantie réelle mobilière corporelle",
    icon: Car,
  },
  {
    value: "FINANCIAL",
    label: "Garantie financière",
    hint: "DAT, épargne, titres",
    icon: Banknote,
  },
];

const MORTGAGE_DOCUMENT_TYPES = [
  { value: "LAND_TITLE", label: "Titre foncier" },
  { value: "ATTRIBUTION_CERT", label: "Attestation d'attribution" },
  { value: "EXPLOITATION_PERMIT", label: "Permis d'exploiter" },
  { value: "BUILDING_PERMIT", label: "Permis de construire" },
  { value: "OCCUPANCY_PERMIT", label: "Permis d'habiter" },
  { value: "LEASEHOLD", label: "Bail emphytéotique" },
  { value: "SURFACE_RIGHT", label: "Droit de superficie" },
  { value: "SALES_DEED", label: "Acte de vente / compromis" },
  { value: "CADASTRAL_EXTRACT", label: "Extrait cadastral" },
  { value: "CUSTOMARY_TITLE", label: "Titre / certificat coutumier" },
  { value: "URBAN_CERT", label: "Certificat d'urbanisme" },
  { value: "OTHER_REAL_ESTATE", label: "Autre titre immobilier" },
];
const VEHICLE_DOCUMENT_TYPES = [
  { value: "REGISTRATION_CARD", label: "Carte grise" },
  { value: "PURCHASE_INVOICE", label: "Facture d'achat" },
  { value: "CUSTOMS_CLEARANCE", label: "Déclaration en douane" },
  { value: "TRANSFER_CERT", label: "Certificat de cession" },
  { value: "INSURANCE_CERT", label: "Attestation d'assurance" },
  { value: "TECH_INSPECTION", label: "Visite technique" },
  { value: "OTHER_VEHICLE", label: "Autre document véhicule" },
];
const MARITAL = [
  { value: "SINGLE", label: "Célibataire" },
  { value: "MARRIED", label: "Marié(e)" },
  { value: "DIVORCED", label: "Divorcé(e)" },
  { value: "WIDOWED", label: "Veuf/Veuve" },
];
const MATRIMONIAL_REGIME = [
  { value: "COMMUNITY", label: "Communauté de biens" },
  { value: "SEPARATION", label: "Séparation de biens" },
];
const OCCUPANCY = [
  { value: "FREE", label: "Libre" },
  { value: "FAMILY_HOME", label: "Domicile familial" },
  { value: "DEVELOPER", label: "Occupé par le promoteur" },
  { value: "RENTED", label: "En location" },
];
const FINANCIAL_TYPES = [
  { value: "DAT", label: "Dépôt à terme (DAT)" },
  { value: "SAVINGS", label: "Épargne" },
  { value: "SECURITY", label: "Titre" },
];

const TEXT_KEYS = [
  "reference", "description", "owners", "expertise_value",
  // Propriétaire
  "owner_last_name", "owner_first_name", "owner_marital_status",
  "matrimonial_regime",
  // Hypothèque
  "document_type", "document_number", "document_issue_date",
  "document_validity_date", "address",
  "expertise_date", "expertise_firm", "expert_name", "expertise_reference",
  "value_to_consider",
  "occupancy_status",
  // Gage — moyen roulant
  "chassis_number", "engine_number", "brand", "model_name", "registration",
  "power", "first_registration_year", "acquisition_date", "acquisition_value",
  "resale_value", "estimation_date", "additional_info",
  // Gage — objet de valeur
  "raw_material_price",
  // Garantie financière
  "financial_type", "account_number", "balance", "remuneration_rate",
  "deposit_maturity_date", "isin_code", "volatility_history", "security_discount",
] as const;

type TextKey = (typeof TEXT_KEYS)[number];
type TextState = Record<TextKey, string>;

const FIELD_LABELS: Record<string, string> = {
  guarantee_type: "Type de garantie",
  client: "Client",
  application: "Dossier",
  reference: "Référence",
  description: "Description",
  expertise_value: "Valeur expertisée / estimée",
  value_to_consider: "Valeur à considérer",
  ltv_ratio: "Taux de couverture",
  document_type: "Type de document",
  document_number: "Numéro du document",
  document_issue_date: "Date d'établissement",
  document_validity_date: "Date de validité",
  owner_last_name: "Nom du propriétaire",
  owner_first_name: "Prénom du propriétaire",
  address: "Adresse du bien",
  expertise_date: "Date de l'expertise",
  expertise_firm: "Cabinet d'expertise",
  expert_name: "Nom de l'expert",
  expertise_reference: "Référence du rapport",
  occupancy_status: "Statut d'occupation",
  chassis_number: "Numéro de châssis",
  engine_number: "Numéro du moteur",
  brand: "Marque",
  model_name: "Modèle",
  registration: "Immatriculation",
  power: "Puissance",
  first_registration_year: "Année de 1re mise en circulation",
  acquisition_date: "Date d'acquisition",
  acquisition_value: "Valeur d'acquisition",
  resale_value: "Valeur estimée à la revente",
  estimation_date: "Date d'estimation",
  raw_material_price: "Cours de la matière première",
  financial_type: "Type de garantie financière",
  account_number: "Numéro de compte",
  balance: "Solde",
  remuneration_rate: "Taux de rémunération",
  deposit_maturity_date: "Date d'échéance du dépôt",
  isin_code: "Code ISIN / nom de la valeur",
  security_discount: "Décote de sécurité",
  photos: "Photos",
  belongs_to_applicant: "Propriété du bien",
  surety: "Caution (propriétaire du bien)",
  documents: "Documents",
};

const FILE_KEYS = [
  "document_scan", "expertise_report_scan", "lease_contract_scan",
  "legal_situation_certificate_scan", "registration_card_scan",
  "mechanical_expertise_scan", "technical_inspection_scan", "insurance_scan",
  "purchase_invoice_scan", "expertise_certificate_scan",
  "origin_certificate_scan", "pledge_deed_scan",
] as const;

type FileKey = (typeof FILE_KEYS)[number];
type FileState = Record<FileKey, File | null>;

type AlreadyTaken = {
  code?: string;
  message: string;
  id?: string;
  reference?: string;
  client_display?: string;
  application_id?: string | null;
  application_reference?: string;
};

function firstText(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) return firstText(value[0]);
  return String(value).trim();
}

function parseAlreadyTaken(errors: unknown): AlreadyTaken | null {
  if (!errors || typeof errors !== "object" || Array.isArray(errors)) return null;
  const raw = (errors as { already_taken?: unknown }).already_taken;
  const payload = Array.isArray(raw) ? raw[0] : raw;
  if (payload && typeof payload === "object" && payload !== null) {
    const row = payload as Record<string, unknown>;
    const message = firstText(row.message || row.detail);
    if (!message) return null;
    return {
      code: firstText(row.code) || undefined,
      message,
      id: firstText(row.id) || undefined,
      reference: firstText(row.reference) || undefined,
      client_display: firstText(row.client_display) || undefined,
      application_id: firstText(row.application_id) || null,
      application_reference: firstText(row.application_reference) || undefined,
    };
  }
  if (typeof payload === "string" && payload.trim()) {
    return { message: payload.trim() };
  }
  return null;
}

interface JewelryItem {
  nature: string;
  weight: string;
  description: string;
}

const emptyFiles = (): FileState =>
  Object.fromEntries(FILE_KEYS.map((k) => [k, null])) as FileState;

function initJewelry(initial?: Guarantee): JewelryItem[] {
  const items = initial?.jewelry_items;
  if (!items || !items.length) {
    return [{ nature: "", weight: "", description: "" }];
  }
  return items.map((it) => ({
    nature: it.nature ?? "",
    weight: it.weight === null || it.weight === undefined ? "" : String(it.weight),
    description: it.description ?? "",
  }));
}

function initText(initial?: Guarantee): TextState {
  const state = Object.fromEntries(TEXT_KEYS.map((k) => [k, ""])) as TextState;
  if (!initial) return state;
  for (const key of TEXT_KEYS) {
    const value = (initial as unknown as Record<string, unknown>)[key];
    state[key] = value === null || value === undefined ? "" : String(value);
  }
  return state;
}

export interface GuaranteeFormProps {
  mode: "create" | "edit";
  /** Identifiant de la garantie (mode édition). */
  guaranteeId?: string;
  /** Garantie existante à pré-remplir (mode édition). */
  initial?: Guarantee;
  /** Client rattaché (mode création). */
  clientId?: string;
  /** Dossier rattaché (mode création). */
  applicationId?: string;
  /** Montant du prêt pour le calcul du ratio LTV. */
  loanAmount?: number;
  /** Lien de retour / annulation. */
  backTo: string;
  onSaved: () => void;
}

export function GuaranteeForm({
  mode,
  guaranteeId,
  initial,
  clientId,
  applicationId,
  loanAmount = 0,
  backTo,
  onSaved,
}: GuaranteeFormProps) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [existingAlert, setExistingAlert] = useState<AlreadyTaken | null>(null);

  const [gType, setGType] = useState(initial?.guarantee_type || "MORTGAGE");
  const [pledgeCat, setPledgeCat] = useState(
    initial?.pledge_category || "VEHICLE",
  );
  const [isInsured, setIsInsured] = useState(initial?.is_insured ?? false);
  const [text, setText] = useState<TextState>(() => initText(initial));
  const [files, setFiles] = useState<FileState>(emptyFiles());
  const [photos, setPhotos] = useState<File[]>([]);
  const [jewelry, setJewelry] = useState<JewelryItem[]>(() =>
    initJewelry(initial),
  );
  const [belongsToApplicant, setBelongsToApplicant] = useState(
    initial?.belongs_to_applicant ?? true,
  );
  const [suretyId, setSuretyId] = useState(initial?.surety ?? "");
  const [docDrafts, setDocDrafts] = useState<FreeDocumentDraft[]>([]);
  const [deletedDocIds, setDeletedDocIds] = useState<string[]>([]);

  const existing = (key: FileKey): string | null =>
    (initial?.[key] as string | null) ?? null;

  const ltv = useMemo(() => {
    const v = Number(text.value_to_consider);
    if (!v || !loanAmount) return null;
    return v / loanAmount;
  }, [text.value_to_consider, loanAmount]);

  const mutation = useMutation({
    mutationFn: async (acceptExisting?: boolean) => {
      const fd = new FormData();
      if (acceptExisting) fd.append("accept_existing", "true");
      fd.append("guarantee_type", gType);
      if (gType === "PLEDGE") fd.append("pledge_category", pledgeCat);
      fd.append("is_insured", isInsured ? "true" : "false");
      fd.append("belongs_to_applicant", belongsToApplicant ? "true" : "false");
      if (!belongsToApplicant && suretyId) {
        fd.append("surety", suretyId);
      }
      if (mode === "create") {
        if (clientId) fd.append("client", clientId);
        if (applicationId) fd.append("application", applicationId);
      }
      for (const key of TEXT_KEYS) {
        const value = text[key].trim();
        if (value) fd.append(key, value);
      }
      for (const key of FILE_KEYS) {
        const f = files[key];
        if (f) fd.append(key, f);
      }
      for (const p of photos) fd.append("photos", p);
      appendFreeDocuments(fd, docDrafts, deletedDocIds);
      if (gType === "PLEDGE" && pledgeCat === "VALUABLE") {
        const cleaned = jewelry
          .map((j) => ({
            nature: j.nature.trim(),
            weight: j.weight.trim(),
            description: j.description.trim(),
          }))
          .filter((j) => j.nature || j.weight || j.description);
        fd.append("jewelry_items", JSON.stringify(cleaned));
      }
      if (mode === "edit" && guaranteeId) {
        return (await api.patch(`/guarantees/${guaranteeId}/`, fd)).data;
      }
      return (await api.post("/guarantees/", fd)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["guarantees"] });
      if (guaranteeId)
        qc.invalidateQueries({ queryKey: ["guarantee", guaranteeId] });
      onSaved();
    },
    onError: (e: unknown) => {
      const resp = (e as { response?: { status?: number; data?: unknown } })
        ?.response;
      const data = resp?.data;
      const errors =
        data && typeof data === "object" && "errors" in data
          ? (data as { errors: unknown }).errors
          : data;
      const taken = parseAlreadyTaken(errors);
      if (taken) {
        setExistingAlert(taken);
        return;
      }
      setExistingAlert(null);
      if (errors && typeof errors === "object" && !Array.isArray(errors)) {
        setError(
          Object.entries(errors as Record<string, unknown>)
            .map(([k, v]) => {
              const label = FIELD_LABELS[k] ?? k;
              const msg = Array.isArray(v) ? v.join(", ") : String(v);
              return `${label} : ${msg}`;
            })
            .join(" · "),
        );
        return;
      }
      if (Array.isArray(errors) && errors.length) {
        setError(errors.map((v) => String(v)).join(" · "));
        return;
      }
      if (typeof errors === "string" && errors && !errors.startsWith("<")) {
        setError(errors);
        return;
      }
      const status = resp?.status;
      if (status === 413) {
        setError(
          "Les fichiers joints (scans/photos) sont trop volumineux. Réduisez leur taille puis réessayez.",
        );
      } else if (status && status >= 500) {
        setError(
          "Erreur serveur lors de l'enregistrement. Réessayez ou contactez l'administrateur.",
        );
      } else if (!resp) {
        setError("Connexion au serveur impossible. Vérifiez votre réseau.");
      } else {
        setError("Enregistrement impossible. Vérifiez les champs.");
      }
    },
  });

  const set = (key: TextKey) => (value: string) =>
    setText((prev) => ({ ...prev, [key]: value }));
  const setFile = (key: FileKey) => (f: File | null) =>
    setFiles((prev) => ({ ...prev, [key]: f }));
  const isMarried = text.owner_marital_status === "MARRIED";

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!belongsToApplicant && !suretyId) {
      setError(
        "Indiquez la caution : le bien n'appartient pas au client demandeur.",
      );
      return;
    }
    const needsTitle = gType === "MORTGAGE" || (gType === "PLEDGE" && pledgeCat === "VEHICLE");
    if (needsTitle) {
      if (!text.document_type || !text.document_number.trim()) {
        setError("Indiquez le type et le numéro du document pris en garantie.");
        return;
      }
      if (mode === "create" && !text.document_issue_date) {
        setError("Indiquez la date d'établissement du document.");
        return;
      }
      if (mode === "create" && !text.expertise_value.trim()) {
        setError("Indiquez la valeur d'expertise.");
        return;
      }
      if (mode === "create" && !text.expertise_date) {
        setError("Indiquez la date de l'expertise.");
        return;
      }
      if (
        mode === "create" &&
        !text.expert_name.trim() &&
        !text.expertise_firm.trim()
      ) {
        setError("Indiquez l'expert ou le cabinet d'expertise.");
        return;
      }
    }
    if (gType === "PLEDGE" && pledgeCat === "VEHICLE" && !text.chassis_number.trim()) {
      setError("Le numéro de châssis est obligatoire pour un gage véhicule.");
      return;
    }
    mutation.mutate(false);
  }

  return (
    <form className="stack" onSubmit={submit}>
      {existingAlert &&
        createPortal(
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() =>
            !mutation.isPending && setExistingAlert(null)
          }
        >
          <div
            className="modal-card"
            role="dialog"
            aria-labelledby="already-taken-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="already-taken-title">
              <TriangleAlert size={18} /> Garantie déjà prise
            </h3>
            <div className="notice-warning" style={{ marginBottom: 12 }}>
              <TriangleAlert size={16} />
              <span>{existingAlert.message}</span>
            </div>
            {(existingAlert.reference ||
              existingAlert.client_display ||
              existingAlert.application_reference) && (
              <ul className="link-list" style={{ marginTop: 4 }}>
                {existingAlert.reference ? (
                  <li>
                    <span>Garantie {existingAlert.reference}</span>
                  </li>
                ) : null}
                {existingAlert.client_display ? (
                  <li>
                    <span>Client {existingAlert.client_display}</span>
                  </li>
                ) : null}
                {existingAlert.application_reference ? (
                  <li>
                    <span>
                      Dossier {existingAlert.application_reference}
                    </span>
                  </li>
                ) : null}
              </ul>
            )}
            <p className="muted small">
              Vous pouvez laisser cette garantie telle quelle, ou
              continuer pour l&apos;enregistrer quand même.
            </p>
            <div className="row-actions" style={{ marginTop: 16 }}>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={mutation.isPending}
                onClick={() => setExistingAlert(null)}
              >
                Laisser
              </button>
              {existingAlert.id ? (
                <Link
                  className="btn btn-ghost"
                  to={`/garanties/${existingAlert.id}`}
                >
                  Voir l&apos;existante
                </Link>
              ) : null}
              <button
                type="button"
                className="btn btn-primary"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate(true)}
              >
                {mutation.isPending
                  ? "Enregistrement…"
                  : "Continuer quand même"}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
      <Card
        title={
          <>
            <ShieldCheck size={17} /> Type de garantie
          </>
        }
      >
        <div className="category-grid">
          {CATEGORIES.map((c) => {
            const Icon = c.icon;
            return (
              <button
                key={c.value}
                type="button"
                className={`category-card${gType === c.value ? " active" : ""}`}
                onClick={() => {
                  setGType(c.value);
                  if (c.value === "PLEDGE") {
                    setText((prev) => {
                      const mortgageCodes = new Set(
                        MORTGAGE_DOCUMENT_TYPES.map((d) => d.value),
                      );
                      if (
                        !prev.document_type ||
                        mortgageCodes.has(prev.document_type)
                      ) {
                        return { ...prev, document_type: "REGISTRATION_CARD" };
                      }
                      return prev;
                    });
                  }
                }}
              >
                <Icon size={22} />
                <strong>{c.label}</strong>
                <span>{c.hint}</span>
              </button>
            );
          })}
        </div>
        <div className="form-grid two-col" style={{ marginTop: 16 }}>
          <Text label="Référence (optionnel)" value={text.reference} onChange={set("reference")} />
        </div>
      </Card>

      <Card
        title={
          <>
            <ShieldCheck size={17} /> Propriété du bien
          </>
        }
      >
        <label className="field">
          <span>Ce bien appartient-il au client demandeur ?</span>
          <div className="type-toggle compact">
            <button
              type="button"
              className={`type-choice${belongsToApplicant ? " active" : ""}`}
              onClick={() => {
                setBelongsToApplicant(true);
                setSuretyId("");
              }}
            >
              Oui
            </button>
            <button
              type="button"
              className={`type-choice${!belongsToApplicant ? " active" : ""}`}
              onClick={() => setBelongsToApplicant(false)}
            >
              Non
            </button>
          </div>
        </label>
        {!belongsToApplicant && (
          <div style={{ marginTop: 14 }}>
            <p className="muted small" style={{ marginBottom: 8 }}>
              Sélectionnez la caution propriétaire du bien. Les cautions hors
              garantie (engagements) restent gérées séparément dans le dossier.
            </p>
            <SuretyAutocomplete
              value={suretyId}
              initialLabel={initial?.surety_display ?? ""}
              onChange={(id) => setSuretyId(id)}
            />
          </div>
        )}
      </Card>

      {gType === "MORTGAGE" && (
        <MortgageSection
          text={text}
          set={set}
          files={files}
          setFile={setFile}
          existing={existing}
          photos={photos}
          setPhotos={setPhotos}
          existingPhotos={initial?.photos}
          isInsured={isInsured}
          setIsInsured={setIsInsured}
          isMarried={isMarried}
          ltv={ltv}
        />
      )}

      {gType === "PLEDGE" && (
        <>
          <Card
            title={
              <>
                <Car size={17} /> Catégorie de gage
              </>
            }
          >
            <div className="type-toggle">
              <button
                type="button"
                className={`type-choice${pledgeCat === "VEHICLE" ? " active" : ""}`}
                onClick={() => setPledgeCat("VEHICLE")}
              >
                <Car size={15} style={{ verticalAlign: "-3px", marginRight: 6 }} />
                Moyen roulant
              </button>
              <button
                type="button"
                className={`type-choice${pledgeCat === "VALUABLE" ? " active" : ""}`}
                onClick={() => setPledgeCat("VALUABLE")}
              >
                <Gem size={15} style={{ verticalAlign: "-3px", marginRight: 6 }} />
                Objet de valeur
              </button>
            </div>
          </Card>
          {pledgeCat === "VEHICLE" ? (
            <VehicleSection text={text} set={set} files={files} setFile={setFile} existing={existing} />
          ) : (
            <ValuableSection
              text={text}
              set={set}
              files={files}
              setFile={setFile}
              existing={existing}
              photos={photos}
              setPhotos={setPhotos}
              existingPhotos={initial?.photos}
              jewelry={jewelry}
              setJewelry={setJewelry}
            />
          )}
        </>
      )}

      {gType === "FINANCIAL" && (
        <FinancialSection text={text} set={set} files={files} setFile={setFile} existing={existing} />
      )}

      <Card
        title={
          <>
            <UploadCloud size={17} /> Documents complémentaires
          </>
        }
      >
        <p className="muted small" style={{ marginBottom: 12 }}>
          Ajoutez ou retirez librement des documents (intitulé + scan).
        </p>
        <FreeDocumentsEditor
          existing={initial?.documents}
          drafts={docDrafts}
          onDraftsChange={setDocDrafts}
          deletedIds={deletedDocIds}
          onDeletedIdsChange={setDeletedDocIds}
        />
      </Card>

      {error && <div className="form-error">{error}</div>}
      <div className="page-actions">
        <Link className="btn btn-ghost" to={backTo}>
          Annuler
        </Link>
        <button className="btn btn-primary" disabled={mutation.isPending}>
          {mutation.isPending
            ? "Enregistrement…"
            : mode === "edit"
              ? "Enregistrer les modifications"
              : "Enregistrer la garantie"}
        </button>
      </div>
    </form>
  );
}

type SetText = (key: TextKey) => (v: string) => void;
type SetFile = (key: FileKey) => (f: File | null) => void;
type Existing = (key: FileKey) => string | null;

function MortgageSection({
  text,
  set,
  files,
  setFile,
  existing,
  photos,
  setPhotos,
  existingPhotos,
  isInsured,
  setIsInsured,
  isMarried,
  ltv,
}: {
  text: TextState;
  set: SetText;
  files: FileState;
  setFile: SetFile;
  existing: Existing;
  photos: File[];
  setPhotos: (f: File[]) => void;
  existingPhotos?: Guarantee["photos"];
  isInsured: boolean;
  setIsInsured: (b: boolean) => void;
  isMarried: boolean;
  ltv: number | null;
}) {
  return (
    <>
      <Card
        title={
          <>
            <Landmark size={17} /> Propriétaire du bien
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Nom du propriétaire" value={text.owner_last_name} onChange={set("owner_last_name")} />
          <Text label="Prénom du propriétaire" value={text.owner_first_name} onChange={set("owner_first_name")} />
          <Select label="Situation matrimoniale" value={text.owner_marital_status} onChange={set("owner_marital_status")} options={MARITAL} />
          {isMarried && (
            <Select label="Régime matrimonial" value={text.matrimonial_regime} onChange={set("matrimonial_regime")} options={MATRIMONIAL_REGIME} />
          )}
        </div>
      </Card>

      <Card
        title={
          <>
            <Landmark size={17} /> Bien immobilier
          </>
        }
      >
        <div className="form-grid two-col">
          <Select
            label="Type de document *"
            value={text.document_type}
            onChange={set("document_type")}
            options={MORTGAGE_DOCUMENT_TYPES}
          />
          <Text
            label="Numéro du document *"
            value={text.document_number}
            onChange={set("document_number")}
          />
          <Text
            label="Date d'établissement *"
            type="date"
            value={text.document_issue_date}
            onChange={set("document_issue_date")}
          />
          <Text
            label="Date de validité"
            type="date"
            value={text.document_validity_date}
            onChange={set("document_validity_date")}
          />
          <Text label="Adresse du bien" value={text.address} onChange={set("address")} />
          <Text
            label="Valeur expertisée (XOF) *"
            type="number"
            value={text.expertise_value}
            onChange={set("expertise_value")}
          />
          <Text
            label="Date de l'expertise *"
            type="date"
            value={text.expertise_date}
            onChange={set("expertise_date")}
          />
          <Text
            label="Cabinet d'expertise"
            value={text.expertise_firm}
            onChange={set("expertise_firm")}
          />
          <Text
            label="Nom de l'expert"
            value={text.expert_name}
            onChange={set("expert_name")}
          />
          <Text
            label="Référence du rapport"
            value={text.expertise_reference}
            onChange={set("expertise_reference")}
          />
          <Text label="Valeur à considérer (XOF)" type="number" value={text.value_to_consider} onChange={set("value_to_consider")} />
          <label className="field">
            <span>Taux de couverture (auto)</span>
            <input
              className="readonly"
              readOnly
              value={ltv !== null ? `${ltv.toFixed(2)} (${(ltv * 100).toFixed(0)} %)` : "—"}
            />
          </label>
          <Select label="Statut d'occupation" value={text.occupancy_status} onChange={set("occupancy_status")} options={OCCUPANCY} />
          <label className="field">
            <span>Le bien est-il assuré ?</span>
            <div className="type-toggle compact">
              <button type="button" className={`type-choice${!isInsured ? " active" : ""}`} onClick={() => setIsInsured(false)}>
                Non
              </button>
              <button type="button" className={`type-choice${isInsured ? " active" : ""}`} onClick={() => setIsInsured(true)}>
                Oui
              </button>
            </div>
          </label>
        </div>
      </Card>

      <Card
        title={
          <>
            <UploadCloud size={17} /> Pièces justificatives
          </>
        }
      >
        <div className="form-grid two-col">
          <FileField label="Scan du document" file={files.document_scan} onChange={setFile("document_scan")} existing={existing("document_scan")} />
          <FileField label="Scan du rapport d'expertise" file={files.expertise_report_scan} onChange={setFile("expertise_report_scan")} existing={existing("expertise_report_scan")} />
          <FileField label="Scan du contrat de bail (si en location)" file={files.lease_contract_scan} onChange={setFile("lease_contract_scan")} existing={existing("lease_contract_scan")} />
          <FileField label="Certificat de situation juridique (< 3 mois)" file={files.legal_situation_certificate_scan} onChange={setFile("legal_situation_certificate_scan")} existing={existing("legal_situation_certificate_scan")} />
        </div>
        <MultiFileField label="Photos du bien" files={photos} onChange={setPhotos} existingPhotos={existingPhotos} />
      </Card>
    </>
  );
}

function VehicleSection({
  text,
  set,
  files,
  setFile,
  existing,
}: {
  text: TextState;
  set: SetText;
  files: FileState;
  setFile: SetFile;
  existing: Existing;
}) {
  return (
    <>
      <Card
        title={
          <>
            <Car size={17} /> Moyen roulant
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Nom du propriétaire" value={text.owner_last_name} onChange={set("owner_last_name")} />
          <Text label="Prénom du propriétaire" value={text.owner_first_name} onChange={set("owner_first_name")} />
          <Text
            label="Numéro de châssis *"
            value={text.chassis_number}
            onChange={set("chassis_number")}
          />
          <Text label="Numéro du moteur" value={text.engine_number} onChange={set("engine_number")} />
          <Text label="Marque" value={text.brand} onChange={set("brand")} />
          <Text label="Modèle" value={text.model_name} onChange={set("model_name")} />
          <Text label="Immatriculation" value={text.registration} onChange={set("registration")} />
          <Text label="Puissance" value={text.power} onChange={set("power")} />
          <Text label="Année de 1re mise en circulation" type="number" value={text.first_registration_year} onChange={set("first_registration_year")} />
          <Text label="Date d'acquisition" type="date" value={text.acquisition_date} onChange={set("acquisition_date")} />
          <Text label="Valeur d'acquisition (XOF)" type="number" value={text.acquisition_value} onChange={set("acquisition_value")} />
          <Text label="Valeur estimée à la revente (XOF)" type="number" value={text.resale_value} onChange={set("resale_value")} />
          <Text label="Date d'estimation" type="date" value={text.estimation_date} onChange={set("estimation_date")} />
        </div>
      </Card>

      <Card
        title={
          <>
            <Landmark size={17} /> Document pris en garantie
          </>
        }
      >
        <div className="form-grid two-col">
          <Select
            label="Type de document *"
            value={text.document_type}
            onChange={set("document_type")}
            options={VEHICLE_DOCUMENT_TYPES}
          />
          <Text
            label="Numéro du document *"
            value={text.document_number}
            onChange={set("document_number")}
          />
          <Text
            label="Date d'établissement *"
            type="date"
            value={text.document_issue_date}
            onChange={set("document_issue_date")}
          />
          <Text
            label="Date de validité"
            type="date"
            value={text.document_validity_date}
            onChange={set("document_validity_date")}
          />
        </div>
      </Card>

      <Card
        title={
          <>
            <Banknote size={17} /> Expertise
          </>
        }
      >
        <div className="form-grid two-col">
          <Text
            label="Valeur expertisée (XOF) *"
            type="number"
            value={text.expertise_value}
            onChange={set("expertise_value")}
          />
          <Text
            label="Date de l'expertise *"
            type="date"
            value={text.expertise_date}
            onChange={set("expertise_date")}
          />
          <Text
            label="Cabinet d'expertise"
            value={text.expertise_firm}
            onChange={set("expertise_firm")}
          />
          <Text
            label="Nom de l'expert"
            value={text.expert_name}
            onChange={set("expert_name")}
          />
          <Text
            label="Référence du rapport"
            value={text.expertise_reference}
            onChange={set("expertise_reference")}
          />
        </div>
        <label className="field">
          <span>Information complémentaire</span>
          <textarea rows={3} value={text.additional_info} onChange={(e) => set("additional_info")(e.target.value)} />
        </label>
      </Card>

      <Card
        title={
          <>
            <UploadCloud size={17} /> Pièces justificatives
          </>
        }
      >
        <div className="form-grid two-col">
          <FileField label="Scan carte grise" file={files.registration_card_scan} onChange={setFile("registration_card_scan")} existing={existing("registration_card_scan")} />
          <FileField label="Scan rapport d'expertise mécanique" file={files.mechanical_expertise_scan} onChange={setFile("mechanical_expertise_scan")} existing={existing("mechanical_expertise_scan")} />
          <FileField label="Scan visite technique" file={files.technical_inspection_scan} onChange={setFile("technical_inspection_scan")} existing={existing("technical_inspection_scan")} />
          <FileField label="Scan assurance" file={files.insurance_scan} onChange={setFile("insurance_scan")} existing={existing("insurance_scan")} />
          <FileField label="Scan facture d'achat" file={files.purchase_invoice_scan} onChange={setFile("purchase_invoice_scan")} existing={existing("purchase_invoice_scan")} />
        </div>
      </Card>
    </>
  );
}

function ValuableSection({
  text,
  set,
  files,
  setFile,
  existing,
  photos,
  setPhotos,
  existingPhotos,
  jewelry,
  setJewelry,
}: {
  text: TextState;
  set: SetText;
  files: FileState;
  setFile: SetFile;
  existing: Existing;
  photos: File[];
  setPhotos: (f: File[]) => void;
  existingPhotos?: Guarantee["photos"];
  jewelry: JewelryItem[];
  setJewelry: (items: JewelryItem[] | ((prev: JewelryItem[]) => JewelryItem[])) => void;
}) {
  const updateItem = (idx: number, patch: Partial<JewelryItem>) =>
    setJewelry((arr) =>
      arr.map((item, i) => (i === idx ? { ...item, ...patch } : item)),
    );

  const addItem = () =>
    setJewelry((arr) => [...arr, { nature: "", weight: "", description: "" }]);

  const removeItem = (idx: number) =>
    setJewelry((arr) => arr.filter((_, i) => i !== idx));

  return (
    <>
      <Card
        title={
          <>
            <Gem size={17} /> Objet de valeur
          </>
        }
      >
        <label className="field">
          <span>Description générale (optionnel)</span>
          <textarea rows={2} value={text.description} onChange={(e) => set("description")(e.target.value)} />
        </label>
        <div className="form-grid two-col">
          <Text label="Valeur estimée (XOF)" type="number" value={text.expertise_value} onChange={set("expertise_value")} />
          <Text label="Date d'expertise" type="date" value={text.expertise_date} onChange={set("expertise_date")} />
          <Text label="Cabinet d'expertise" value={text.expertise_firm} onChange={set("expertise_firm")} />
          <Text label="Nom de l'expert" value={text.expert_name} onChange={set("expert_name")} />
          <Text label="Cours actuel de la matière première (XOF)" type="number" value={text.raw_material_price} onChange={set("raw_material_price")} />
        </div>
      </Card>

      <Card
        title={
          <>
            <Gem size={17} /> Composantes du gage (bijoux)
          </>
        }
      >
        <p className="muted small" style={{ marginBottom: 12 }}>
          Ajoutez chaque bijou de l&apos;ensemble (bague, bracelet, collier…) avec sa nature, son poids et une description.
        </p>
        {jewelry.map((item, idx) => (
          <div key={idx} className="jewelry-item-row">
            <Text
              label={`Nature du bijou #${idx + 1}`}
              value={item.nature}
              onChange={(v) => updateItem(idx, { nature: v })}
            />
            <Text
              label="Poids (g)"
              type="number"
              value={item.weight}
              onChange={(v) => updateItem(idx, { weight: v })}
            />
            <label className="field">
              <span>Description</span>
              <input
                value={item.description}
                onChange={(e) => updateItem(idx, { description: e.target.value })}
                placeholder="ex. or 18 carats, pierre…"
              />
            </label>
            <button
              type="button"
              className="btn btn-ghost btn-sm jewelry-item-remove"
              onClick={() => removeItem(idx)}
              title="Retirer ce bijou"
              aria-label="Retirer ce bijou"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost btn-sm" onClick={addItem}>
          <Plus size={14} />
          Ajouter un bijou
        </button>
      </Card>

      <Card
        title={
          <>
            <UploadCloud size={17} /> Pièces justificatives
          </>
        }
      >
        <div className="form-grid two-col">
          <FileField label="Scan certificat d'expertise" file={files.expertise_certificate_scan} onChange={setFile("expertise_certificate_scan")} existing={existing("expertise_certificate_scan")} />
          <FileField label="Scan certificat d'origine / facture" file={files.origin_certificate_scan} onChange={setFile("origin_certificate_scan")} existing={existing("origin_certificate_scan")} />
        </div>
        <MultiFileField label="Photos de l'objet" files={photos} onChange={setPhotos} existingPhotos={existingPhotos} />
      </Card>
    </>
  );
}

function FinancialSection({
  text,
  set,
  files,
  setFile,
  existing,
}: {
  text: TextState;
  set: SetText;
  files: FileState;
  setFile: SetFile;
  existing: Existing;
}) {
  const isDAT = text.financial_type === "DAT";
  const isSecurity = text.financial_type === "SECURITY";
  return (
    <>
      <Card
        title={
          <>
            <Banknote size={17} /> Garantie financière
          </>
        }
      >
        <div className="form-grid two-col">
          <Select label="Type" value={text.financial_type} onChange={set("financial_type")} options={FINANCIAL_TYPES} />
          <Text label="Numéro de compte" value={text.account_number} onChange={set("account_number")} />
          <Text label="Solde (XOF)" type="number" value={text.balance} onChange={set("balance")} />
          <Text label="Taux de rémunération (%)" type="number" value={text.remuneration_rate} onChange={set("remuneration_rate")} />
          {isDAT && (
            <Text label="Date d'échéance du dépôt" type="date" value={text.deposit_maturity_date} onChange={set("deposit_maturity_date")} />
          )}
          {isSecurity && (
            <>
              <Text label="Code ISIN / nom de la valeur" value={text.isin_code} onChange={set("isin_code")} />
              <Text label="Décote de sécurité (%)" type="number" value={text.security_discount} onChange={set("security_discount")} />
            </>
          )}
        </div>
        {isSecurity && (
          <label className="field">
            <span>Historique de volatilité (variations du cours sur 12 mois)</span>
            <textarea rows={3} value={text.volatility_history} onChange={(e) => set("volatility_history")(e.target.value)} />
          </label>
        )}
      </Card>

      <Card
        title={
          <>
            <UploadCloud size={17} /> Pièces justificatives
          </>
        }
      >
        <FileField label="Scan acte de nantissement / acte de blocage" file={files.pledge_deed_scan} onChange={setFile("pledge_deed_scan")} existing={existing("pledge_deed_scan")} />
      </Card>
    </>
  );
}

function Text({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">— Sélectionner —</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function FileField({
  label,
  file,
  onChange,
  existing,
}: {
  label: string;
  file: File | null;
  onChange: (f: File | null) => void;
  existing?: string | null;
}) {
  return (
    <label className="field file-field">
      <span>{label}</span>
      <div className={`file-drop${file ? " has-file" : ""}`}>
        <UploadCloud size={18} />
        <span className="file-name">{file ? file.name : "Choisir un fichier…"}</span>
        <input
          type="file"
          accept="image/*,application/pdf"
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
        />
      </div>
      {existing && !file && (
        <a className="file-existing" href={existing} target="_blank" rel="noreferrer">
          <ExternalLink size={12} /> Fichier actuel
        </a>
      )}
    </label>
  );
}

function MultiFileField({
  label,
  files,
  onChange,
  existingPhotos,
}: {
  label: string;
  files: File[];
  onChange: (f: File[]) => void;
  existingPhotos?: Guarantee["photos"];
}) {
  return (
    <label className="field file-field">
      <span>
        <Images size={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />
        {label}
      </span>
      {existingPhotos && existingPhotos.length > 0 && (
        <div className="photo-gallery small">
          {existingPhotos.map((p) => (
            <a key={p.id} href={p.image} target="_blank" rel="noreferrer">
              <img src={p.image} alt={p.caption || "Photo"} />
            </a>
          ))}
        </div>
      )}
      <div className={`file-drop${files.length ? " has-file" : ""}`}>
        <UploadCloud size={18} />
        <span className="file-name">
          {files.length
            ? `${files.length} photo(s) sélectionnée(s)`
            : existingPhotos && existingPhotos.length
              ? "Ajouter d'autres photos…"
              : "Ajouter des photos…"}
        </span>
        <input
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => onChange(Array.from(e.target.files ?? []))}
        />
      </div>
    </label>
  );
}
