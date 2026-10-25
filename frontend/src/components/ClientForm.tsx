import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Contact,
  ExternalLink,
  FileText,
  Heart,
  Landmark,
  Phone,
  Plus,
  Trash2,
  UploadCloud,
  User,
  UserRound,
  Users,
} from "lucide-react";
import { createContext, useContext, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { Client, CreditApplication, Paginated } from "@/api/types";
import { Card } from "@/components/ui";
import { CustomFields } from "@/components/CustomFields";
import { useAuth } from "@/auth/AuthContext";
import type { ClientReferences, EffectiveConfiguration } from "@/api/configuration";
import { hasPerm } from "@/auth/permissions";

const ClientReferencesContext = createContext<ClientReferences | undefined>(undefined);

type ClientType = "INDIVIDUAL" | "PROFESSIONAL" | "CORPORATE";

const CIVILITY = [
  { value: "MR", label: "Monsieur" },
  { value: "MRS", label: "Madame" },
  { value: "MISS", label: "Mademoiselle" },
];
const MARITAL = [
  { value: "SINGLE", label: "Célibataire" },
  { value: "MARRIED", label: "Marié(e)" },
  { value: "DIVORCED", label: "Divorcé(e)" },
  { value: "WIDOWED", label: "Veuf/Veuve" },
];
const ID_DOCS = [
  { value: "PASSPORT", label: "Passeport" },
  { value: "CNI", label: "Carte nationale d'identité" },
  { value: "DRIVING_LICENSE", label: "Permis de conduire" },
  { value: "CONSULAR_CARD", label: "Carte consulaire" },
];
const LEGAL_FORMS = [
  { value: "SARL", label: "SARL" },
  { value: "SA", label: "SA" },
  { value: "ASSOCIATION", label: "Association" },
  { value: "INDIVIDUAL", label: "Entreprise individuelle" },
  { value: "SASU", label: "SASU" },
  { value: "SAS", label: "SAS" },
  { value: "EURL", label: "EURL" },
  { value: "SNC_SCS", label: "SNC / SCS" },
];

const TEXT_KEYS = [
  "civility", "first_name", "last_name", "birth_date", "birth_country",
  "country", "city", "address", "email", "phone", "marital_status",
  "nationality", "profession", "id_document_type", "national_id",
  "id_document_issue_date", "id_document_expiry_date",
  "spouse_last_name", "spouse_first_name", "spouse_phone", "spouse_profession",
  "father_last_name", "father_first_name", "mother_last_name",
  "mother_first_name",
  "company_name", "legal_form", "ifu", "rccm",
  "manager_last_name", "manager_first_name", "manager_phone",
  "manager_email", "manager_address", "manager_id_document_type",
  "manager_id_document_number", "manager_id_document_issue_date",
  "manager_id_document_expiry_date", "manager_position",
  "manager_birth_date", "manager_birth_country", "manager_birth_city",
  "cbs_client_id", "cbs_account_number",
] as const;

type TextKey = (typeof TEXT_KEYS)[number];
type TextState = Record<TextKey, string>;

const DATE_KEYS = new Set<TextKey>([
  "birth_date",
  "id_document_issue_date",
  "id_document_expiry_date",
  "manager_id_document_issue_date",
  "manager_id_document_expiry_date",
  "manager_birth_date",
]);

const FILE_KEYS = [
  "id_document_scan", "photo", "ifu_scan", "rccm_scan",
  "manager_id_document_scan",
] as const;

type FileKey = (typeof FILE_KEYS)[number];
type FileState = Record<FileKey, File | null>;

const emptyText = () =>
  Object.fromEntries(TEXT_KEYS.map((k) => [k, ""])) as TextState;
const emptyFiles = () =>
  Object.fromEntries(FILE_KEYS.map((k) => [k, null])) as FileState;

const fromClient = (c: Client): TextState => {
  const rec = c as unknown as Record<string, unknown>;
  return Object.fromEntries(
    TEXT_KEYS.map((k) => [k, rec[k] == null ? "" : String(rec[k])]),
  ) as TextState;
};

export function ClientForm({
  initial,
  onSuccess,
  onCancel,
}: {
  initial?: Client;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const qc = useQueryClient();
  const { user, activeTenant } = useAuth();
  const isEdit = Boolean(initial);
  const [type, setType] = useState<ClientType>(
    initial?.client_type ?? "INDIVIDUAL",
  );
  const [text, setText] = useState<TextState>(
    initial ? fromClient(initial) : emptyText(),
  );
  const [files, setFiles] = useState<FileState>(emptyFiles());
  const [extraPhones, setExtraPhones] = useState<string[]>(
    initial?.phones?.map((p) => p.number) ?? [],
  );
  const [error, setError] = useState<string | null>(null);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>((initial as Client & { custom_fields?: Record<string, unknown> })?.custom_fields || {});
  const [configurationApplication, setConfigurationApplication] = useState("");
  const dossiers = useQuery({ queryKey: ["client-form-dossiers", activeTenant || user?.tenant, initial?.id], enabled: !!initial && hasPerm(user, "credits.view_creditapplication"),
    queryFn: async () => { const result: CreditApplication[] = []; let page = 1; while (true) { const response = await api.get<Paginated<CreditApplication>>("/credit-applications/", { params: { client: initial?.id, page, page_size: 200 } }); result.push(...response.data.results.filter((item) => item.client === initial?.id)); if (!response.data.next) return result; page++; } } });
  const configuration = useQuery({ queryKey: ["client-form-configuration", activeTenant || user?.tenant, type, initial?.agency, configurationApplication],
    queryFn: async () => (await api.get<EffectiveConfiguration>("/clients/form-configuration/", { params: { client_type: type, agency: initial?.agency || undefined, application: configurationApplication || undefined, client: initial?.id } })).data });

  const isCorporate = type === "CORPORATE" || type === "PROFESSIONAL";
  const isMarried = text.marital_status === "MARRIED";
  const fileUrls = initial as unknown as Record<string, string | null>;

  const mutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("client_type", type);
      for (const key of TEXT_KEYS) {
        const value = text[key].trim();
        if (isEdit) {
          // En modification, on envoie les champs vides pour permettre de les
          // effacer — sauf les dates (une chaîne vide casserait la validation).
          if (DATE_KEYS.has(key)) {
            if (value) fd.append(key, value);
          } else {
            fd.append(key, value);
          }
        } else if (value) {
          fd.append(key, value);
        }
      }
      for (const key of FILE_KEYS) {
        const file = files[key];
        if (file) fd.append(key, file);
      }
      const phones = extraPhones.map((p) => p.trim()).filter(Boolean);
      fd.append("additional_phones", JSON.stringify(phones));
      fd.append("custom_fields", JSON.stringify(customFields));
      if (configurationApplication) fd.append("configuration_application", configurationApplication);

      if (isEdit && initial) {
        return (await api.patch(`/clients/${initial.id}/`, fd)).data;
      }
      return (await api.post("/clients/", fd)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      if (initial) {
        qc.invalidateQueries({ queryKey: ["client", initial.id] });
        qc.invalidateQueries({ queryKey: ["client-audit", initial.id] });
      }
      onSuccess();
    },
    onError: (e: unknown) => {
      const data = (
        e as { response?: { data?: Record<string, unknown> } }
      )?.response?.data;
      const errors = (data?.errors ?? data) as
        | Record<string, unknown>
        | undefined;
      setError(
        errors && typeof errors === "object"
          ? Object.entries(errors)
              .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
              .join(" · ")
          : "Enregistrement impossible. Vérifiez les champs requis.",
      );
    },
  });

  const set = (key: TextKey) => (value: string) =>
    setText((prev) => ({ ...prev, [key]: value }));
  const setFile = (key: FileKey) => (file: File | null) =>
    setFiles((prev) => ({ ...prev, [key]: file }));

  function submit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  const fieldProps = {
    text,
    files,
    set,
    setFile,
    extraPhones,
    setExtraPhones,
    fileUrls,
  };

  return (
    <ClientReferencesContext.Provider value={configuration.data?.references}>
    <form className="stack" onSubmit={submit}>
      {!!dossiers.data?.length && <Card title="Contexte des exigences"><label className="field"><span>Règles de la fiche client ou d'un dossier accessible</span><select value={configurationApplication} onChange={(event) => setConfigurationApplication(event.target.value)}><option value="">Fiche client — sans produit</option>{dossiers.data.map((item) => <option key={item.id} value={item.id}>{item.reference}</option>)}</select></label><p className="muted">Un dossier soumis utilise ses règles conservées. Les données client restent communes à ses dossiers.</p></Card>}
      <Card
        title={
          <>
            <User size={17} /> Type de client
          </>
        }
      >
        <div className="type-toggle">
          {(
            [
              ["INDIVIDUAL", "Personne physique", UserRound],
              ["PROFESSIONAL", "Groupement", Users],
              ["CORPORATE", "Personne morale", Building2],
            ] as const
          ).map(([value, lbl, Icon]) => (
            <button
              type="button"
              key={value}
              className={`type-choice${type === value ? " active" : ""}`}
              onClick={() => setType(value)}
            >
              <Icon size={20} />
              {lbl}
            </button>
          ))}
        </div>
        <p className="muted small" style={{ marginTop: 10, marginBottom: 0 }}>
          {isEdit
            ? `Matricule : ${initial?.reference || "—"} (non modifiable).`
            : "Le matricule est généré automatiquement à l'enregistrement."}
        </p>
      </Card>

      {isCorporate ? (
        <CorporateFields {...fieldProps} />
      ) : (
        <IndividualFields {...fieldProps} isMarried={isMarried} />
      )}
      {configuration.data?.kyc && <Card title="Exigences KYC applicables"><p className="muted">Contexte de la fiche client sans produit. Les exigences d'un dossier peuvent être complétées selon son produit.</p>
        <p>Informations requises : {configuration.data.kyc.required_fields.join(", ") || "Aucune exigence additionnelle"}.</p>
        <p>Pièces requises : {configuration.data.kyc.required_documents.join(", ") || "Aucune exigence additionnelle"}.</p>
        {configuration.data.kyc.check_expiry && <p>La pièce d'identité doit avoir une date d'expiration renseignée et non échue.</p>}
        {!!configuration.data.kyc.validity_days && <p>Validité de la revue : {configuration.data.kyc.validity_days} jours.</p>}
      </Card>}
      {!!configuration.data?.forms?.client_fields.length && <Card title="Informations complémentaires"><CustomFields definitions={configuration.data.forms.client_fields} value={customFields} onChange={setCustomFields} /></Card>}
      {configuration.isError && <p className="form-error">Impossible de charger la configuration de la fiche client. Rechargez le formulaire.</p>}

      {error && <div className="form-error">{error}</div>}
      <div className="page-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Annuler
        </button>
        <button className="btn btn-primary" disabled={mutation.isPending || configuration.isLoading || configuration.isError}>
          {mutation.isPending
            ? "Enregistrement…"
            : isEdit
              ? "Enregistrer les modifications"
              : "Enregistrer le client"}
        </button>
      </div>
    </form>
    </ClientReferencesContext.Provider>
  );
}

/* -------------------------------------------------------------------- */
/* Champs réutilisables                                                  */
/* -------------------------------------------------------------------- */

function Text({
  label,
  value,
  onChange,
  type = "text",
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span>
        {label}
        {required && <em className="req"> *</em>}
      </span>
      <input
        type={type}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  placeholder = "— Sélectionner —",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
}) {
  const references = useContext(ClientReferencesContext);
  const key = options === CIVILITY ? "civility" : options === MARITAL ? "marital_status" : options === ID_DOCS ? "id_document_type" : options === LEGAL_FORMS ? "legal_form" : null;
  const configured = key && references ? references[key] : undefined;
  const choices = configured ? configured.filter((entry) => entry.active || entry.code === value).map((entry) => ({ value: entry.code, label: entry.label + (entry.active ? "" : " (désactivé)") })) : options;
  const retained = value && !choices.some((entry) => entry.value === value) ? [...choices, { value, label: `${value} (valeur historique)` }] : choices;
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{placeholder}</option>
        {retained.map((o) => (
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
  currentUrl,
  accept,
}: {
  label: string;
  file: File | null;
  onChange: (f: File | null) => void;
  currentUrl?: string | null;
  accept?: string;
}) {
  return (
    <label className="field file-field">
      <span>{label}</span>
      <div className={`file-drop${file ? " has-file" : ""}`}>
        <UploadCloud size={18} />
        <span className="file-name">
          {file
            ? file.name
            : currentUrl
              ? "Remplacer le fichier…"
              : "Choisir un fichier…"}
        </span>
        <input
          type="file"
          accept={accept}
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
        />
      </div>
      {currentUrl && !file && (
        <a
          className="current-file"
          href={currentUrl}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={13} />
          Fichier actuel
        </a>
      )}
    </label>
  );
}

function PhonesEditor({
  primary,
  onPrimary,
  extra,
  onExtra,
}: {
  primary: string;
  onPrimary: (v: string) => void;
  extra: string[];
  onExtra: (v: string[]) => void;
}) {
  return (
    <div className="phones-editor">
      <label className="field">
        <span>Téléphone principal</span>
        <input value={primary} onChange={(e) => onPrimary(e.target.value)} />
      </label>
      {extra.map((num, i) => (
        <label className="field" key={i}>
          <span>Numéro additionnel {i + 1}</span>
          <div className="phone-row">
            <input
              value={num}
              onChange={(e) => {
                const next = [...extra];
                next[i] = e.target.value;
                onExtra(next);
              }}
            />
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => onExtra(extra.filter((_, j) => j !== i))}
              aria-label="Supprimer"
            >
              <Trash2 size={15} />
            </button>
          </div>
        </label>
      ))}
      <button
        type="button"
        className="btn btn-ghost btn-sm add-phone"
        onClick={() => onExtra([...extra, ""])}
      >
        <Plus size={15} />
        Ajouter un numéro
      </button>
    </div>
  );
}

interface FieldProps {
  text: TextState;
  files: FileState;
  set: (k: TextKey) => (v: string) => void;
  setFile: (k: FileKey) => (f: File | null) => void;
  extraPhones: string[];
  setExtraPhones: (v: string[]) => void;
  fileUrls?: Record<string, string | null>;
}

function IndividualFields({
  text,
  files,
  set,
  setFile,
  isMarried,
  extraPhones,
  setExtraPhones,
  fileUrls,
}: FieldProps & { isMarried: boolean }) {
  return (
    <>
      <Card
        title={
          <>
            <User size={17} /> Identité
          </>
        }
      >
        <div className="form-grid two-col">
          <Select label="Civilité" value={text.civility} onChange={set("civility")} options={CIVILITY} />
          <Text label="Nom" value={text.last_name} onChange={set("last_name")} required />
          <Text label="Prénom" value={text.first_name} onChange={set("first_name")} />
          <Text label="Date de naissance" type="date" value={text.birth_date} onChange={set("birth_date")} />
          <Text label="Pays de naissance" value={text.birth_country} onChange={set("birth_country")} />
          <Text label="Nationalité" value={text.nationality} onChange={set("nationality")} />
          <Select label="Situation matrimoniale" value={text.marital_status} onChange={set("marital_status")} options={MARITAL} />
          <Text label="Profession" value={text.profession} onChange={set("profession")} />
        </div>
      </Card>

      <Card
        title={
          <>
            <Phone size={17} /> Coordonnées
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Pays" value={text.country} onChange={set("country")} />
          <Text label="Ville" value={text.city} onChange={set("city")} />
          <Text label="Adresse" value={text.address} onChange={set("address")} />
          <Text label="Email" type="email" value={text.email} onChange={set("email")} />
        </div>
        <PhonesEditor
          primary={text.phone}
          onPrimary={set("phone")}
          extra={extraPhones}
          onExtra={setExtraPhones}
        />
      </Card>

      <Card
        title={
          <>
            <Landmark size={17} /> Core Banking
          </>
        }
      >
        <div className="form-grid two-col">
          <Text
            label="Matricule du client (Core Banking)"
            value={text.cbs_client_id}
            onChange={set("cbs_client_id")}
          />
          <Text
            label="N° de compte Core Banking"
            value={text.cbs_account_number}
            onChange={set("cbs_account_number")}
          />
        </div>
      </Card>

      {isMarried && (
        <Card
          title={
            <>
              <Heart size={17} /> Conjoint
            </>
          }
        >
          <div className="form-grid two-col">
            <Text label="Nom du conjoint" value={text.spouse_last_name} onChange={set("spouse_last_name")} />
            <Text label="Prénom du conjoint" value={text.spouse_first_name} onChange={set("spouse_first_name")} />
            <Text label="Téléphone du conjoint" value={text.spouse_phone} onChange={set("spouse_phone")} />
            <Text label="Profession du conjoint" value={text.spouse_profession} onChange={set("spouse_profession")} />
          </div>
        </Card>
      )}

      <Card
        title={
          <>
            <Users size={17} /> Parents
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Nom du père" value={text.father_last_name} onChange={set("father_last_name")} />
          <Text label="Prénom du père" value={text.father_first_name} onChange={set("father_first_name")} />
          <Text label="Nom de la mère" value={text.mother_last_name} onChange={set("mother_last_name")} />
          <Text label="Prénom de la mère" value={text.mother_first_name} onChange={set("mother_first_name")} />
        </div>
      </Card>

      <Card
        title={
          <>
            <FileText size={17} /> Pièce d'identité & photo
          </>
        }
      >
        <div className="form-grid two-col">
          <Select label="Type de pièce" value={text.id_document_type} onChange={set("id_document_type")} options={ID_DOCS} />
          <Text label="Numéro de la pièce" value={text.national_id} onChange={set("national_id")} />
          <Text label="Date d'établissement" type="date" value={text.id_document_issue_date} onChange={set("id_document_issue_date")} />
          <Text label="Date d'expiration" type="date" value={text.id_document_expiry_date} onChange={set("id_document_expiry_date")} />
          <FileField label="Scan de la pièce" file={files.id_document_scan} onChange={setFile("id_document_scan")} currentUrl={fileUrls?.id_document_scan} accept="image/*,application/pdf" />
          <FileField label="Photo" file={files.photo} onChange={setFile("photo")} currentUrl={fileUrls?.photo} accept="image/*" />
        </div>
      </Card>
    </>
  );
}

function CorporateFields({
  text,
  files,
  set,
  setFile,
  extraPhones,
  setExtraPhones,
  fileUrls,
}: FieldProps) {
  return (
    <>
      <Card
        title={
          <>
            <Building2 size={17} /> Entreprise
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Raison sociale" value={text.company_name} onChange={set("company_name")} required />
          <Select label="Statut juridique" value={text.legal_form} onChange={set("legal_form")} options={LEGAL_FORMS} />
          <Text label="Numéro IFU" value={text.ifu} onChange={set("ifu")} />
          <Text label="Numéro RCCM" value={text.rccm} onChange={set("rccm")} />
          <FileField label="Scan IFU" file={files.ifu_scan} onChange={setFile("ifu_scan")} currentUrl={fileUrls?.ifu_scan} accept="image/*,application/pdf" />
          <FileField label="Scan RCCM" file={files.rccm_scan} onChange={setFile("rccm_scan")} currentUrl={fileUrls?.rccm_scan} accept="image/*,application/pdf" />
        </div>
      </Card>

      <Card
        title={
          <>
            <Phone size={17} /> Coordonnées
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Adresse" value={text.address} onChange={set("address")} />
          <Text label="Ville" value={text.city} onChange={set("city")} />
          <Text label="Email" type="email" value={text.email} onChange={set("email")} />
        </div>
        <PhonesEditor
          primary={text.phone}
          onPrimary={set("phone")}
          extra={extraPhones}
          onExtra={setExtraPhones}
        />
      </Card>

      <Card
        title={
          <>
            <Landmark size={17} /> Core Banking
          </>
        }
      >
        <div className="form-grid two-col">
          <Text
            label="Matricule du client (Core Banking)"
            value={text.cbs_client_id}
            onChange={set("cbs_client_id")}
          />
          <Text
            label="N° de compte Core Banking"
            value={text.cbs_account_number}
            onChange={set("cbs_account_number")}
          />
        </div>
      </Card>

      <Card
        title={
          <>
            <Contact size={17} /> Gérant
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Nom du gérant" value={text.manager_last_name} onChange={set("manager_last_name")} />
          <Text label="Prénom du gérant" value={text.manager_first_name} onChange={set("manager_first_name")} />
          <Text label="Poste dans l'entreprise" value={text.manager_position} onChange={set("manager_position")} />
          <Text label="Téléphone du gérant" value={text.manager_phone} onChange={set("manager_phone")} />
          <Text label="Email du gérant" type="email" value={text.manager_email} onChange={set("manager_email")} />
          <Text label="Adresse du gérant" value={text.manager_address} onChange={set("manager_address")} />
          <Text label="Date de naissance (gérant)" type="date" value={text.manager_birth_date} onChange={set("manager_birth_date")} />
          <Text label="Pays de naissance (gérant)" value={text.manager_birth_country} onChange={set("manager_birth_country")} />
          <Text label="Ville de naissance (gérant)" value={text.manager_birth_city} onChange={set("manager_birth_city")} />
          <Select label="Type de pièce (gérant)" value={text.manager_id_document_type} onChange={set("manager_id_document_type")} options={ID_DOCS} />
          <Text label="N° de pièce (gérant)" value={text.manager_id_document_number} onChange={set("manager_id_document_number")} />
          <Text label="Date d'établissement (gérant)" type="date" value={text.manager_id_document_issue_date} onChange={set("manager_id_document_issue_date")} />
          <Text label="Date d'expiration (gérant)" type="date" value={text.manager_id_document_expiry_date} onChange={set("manager_id_document_expiry_date")} />
          <FileField label="Scan pièce (gérant)" file={files.manager_id_document_scan} onChange={setFile("manager_id_document_scan")} currentUrl={fileUrls?.manager_id_document_scan} accept="image/*,application/pdf" />
        </div>
      </Card>
    </>
  );
}
