import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Contact,
  ExternalLink,
  FileText,
  HandCoins,
  Phone,
  Plus,
  Trash2,
  UploadCloud,
  UserRound,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { Surety } from "@/api/types";
import {
  FreeDocumentsEditor,
  appendFreeDocuments,
  type FreeDocumentDraft,
} from "@/components/FreeDocumentsEditor";
import { Card, formatMoney } from "@/components/ui";

type SuretyKind = "PHYSICAL" | "MORAL";

const ID_DOCS = [
  { value: "CNI", label: "Carte nationale d'identité" },
  { value: "PASSPORT", label: "Passeport" },
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
  // Physique
  "last_name", "first_name", "birth_date", "birth_country",
  "activity", "estimated_income",
  "id_document_type", "national_id", "id_document_issue_date",
  "id_document_expiry_date",
  // Entreprise
  "company_name", "legal_form", "ifu", "rccm", "city",
  // Gérant
  "manager_last_name", "manager_first_name", "manager_phone",
  "manager_email", "manager_address", "manager_id_document_type",
  "manager_id_document_number", "manager_id_document_issue_date",
  "manager_id_document_expiry_date", "manager_position",
  "manager_birth_date", "manager_birth_country", "manager_birth_city",
  // Commun
  "email", "address", "phone",
] as const;

type TextKey = (typeof TEXT_KEYS)[number];
type TextState = Record<TextKey, string>;

const OMIT_IF_EMPTY = new Set<TextKey>([
  "birth_date",
  "id_document_issue_date",
  "id_document_expiry_date",
  "estimated_income",
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

const fromSurety = (s: Surety): TextState => {
  const rec = s as unknown as Record<string, unknown>;
  return Object.fromEntries(
    TEXT_KEYS.map((k) => [k, rec[k] == null ? "" : String(rec[k])]),
  ) as TextState;
};

export function SuretyForm({
  initial,
  onSuccess,
  onCancel,
}: {
  initial?: Surety;
  onSuccess: (surety: Surety) => void;
  onCancel: () => void;
}) {
  const qc = useQueryClient();
  const isEdit = Boolean(initial);
  const [suretyType, setSuretyType] = useState<SuretyKind>(
    initial?.surety_type ?? "PHYSICAL",
  );
  const [text, setText] = useState<TextState>(
    initial ? fromSurety(initial) : emptyText(),
  );
  const [files, setFiles] = useState<FileState>(emptyFiles());
  const [extraPhones, setExtraPhones] = useState<string[]>(
    initial?.phones?.map((p) => p.number) ?? [],
  );
  const [docDrafts, setDocDrafts] = useState<FreeDocumentDraft[]>([]);
  const [deletedDocIds, setDeletedDocIds] = useState<string[]>([]);
  const [ceiling, setCeiling] = useState(
    initial?.commitment_ceiling != null
      ? String(initial.commitment_ceiling)
      : "0",
  );
  const [error, setError] = useState<string | null>(null);
  const fileUrls = initial as unknown as Record<string, string | null>;
  const isMoral = suretyType === "MORAL";

  const mutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("surety_type", suretyType);
      for (const key of TEXT_KEYS) {
        const value = text[key].trim();
        if (isEdit) {
          if (OMIT_IF_EMPTY.has(key)) {
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
      fd.append("commitment_ceiling", ceiling.trim() || "0");
      appendFreeDocuments(fd, docDrafts, deletedDocIds);

      if (isEdit && initial) {
        return (await api.patch(`/sureties/${initial.id}/`, fd)).data;
      }
      return (await api.post("/sureties/", fd)).data;
    },
    onSuccess: (data: Surety) => {
      qc.invalidateQueries({ queryKey: ["sureties"] });
      if (initial) {
        qc.invalidateQueries({ queryKey: ["surety", initial.id] });
      }
      onSuccess(data);
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

  return (
    <form className="stack" onSubmit={submit}>
      <Card
        title={
          <>
            <UserRound size={17} /> Type de caution
          </>
        }
      >
        <div className="type-toggle">
          <button
            type="button"
            className={`type-choice${suretyType === "PHYSICAL" ? " active" : ""}`}
            onClick={() => setSuretyType("PHYSICAL")}
            disabled={isEdit}
          >
            <UserRound size={15} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Personne physique
          </button>
          <button
            type="button"
            className={`type-choice${suretyType === "MORAL" ? " active" : ""}`}
            onClick={() => setSuretyType("MORAL")}
            disabled={isEdit}
          >
            <Building2 size={15} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Entreprise
          </button>
        </div>
      </Card>

      {isMoral ? (
        <>
          <Card
            title={
              <>
                <Building2 size={17} /> Entreprise de caution
              </>
            }
          >
            <div className="form-grid two-col">
              <Text label="Raison sociale" value={text.company_name} onChange={set("company_name")} required />
              <Select label="Forme juridique" value={text.legal_form} onChange={set("legal_form")} options={LEGAL_FORMS} />
              <Text label="N° IFU / NINEA" value={text.ifu} onChange={set("ifu")} />
              <Text label="N° RCCM" value={text.rccm} onChange={set("rccm")} />
              <Text label="Activité" value={text.activity} onChange={set("activity")} />
              <Text label="Ville" value={text.city} onChange={set("city")} />
              <FileField label="Scan IFU" file={files.ifu_scan} onChange={setFile("ifu_scan")} currentUrl={fileUrls?.ifu_scan} accept="image/*,application/pdf" />
              <FileField label="Scan RCCM" file={files.rccm_scan} onChange={setFile("rccm_scan")} currentUrl={fileUrls?.rccm_scan} accept="image/*,application/pdf" />
            </div>
          </Card>

          <Card
            title={
              <>
                <Contact size={17} /> Gérant de l&apos;entreprise
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
              <Text label="Date de naissance" type="date" value={text.manager_birth_date} onChange={set("manager_birth_date")} />
              <Text label="Pays de naissance" value={text.manager_birth_country} onChange={set("manager_birth_country")} />
              <Text label="Ville de naissance" value={text.manager_birth_city} onChange={set("manager_birth_city")} />
              <Select label="Type de pièce" value={text.manager_id_document_type} onChange={set("manager_id_document_type")} options={ID_DOCS} />
              <Text label="N° de pièce" value={text.manager_id_document_number} onChange={set("manager_id_document_number")} />
              <Text label="Date d'établissement" type="date" value={text.manager_id_document_issue_date} onChange={set("manager_id_document_issue_date")} />
              <Text label="Date d'expiration" type="date" value={text.manager_id_document_expiry_date} onChange={set("manager_id_document_expiry_date")} />
              <FileField label="Scan pièce (gérant)" file={files.manager_id_document_scan} onChange={setFile("manager_id_document_scan")} currentUrl={fileUrls?.manager_id_document_scan} accept="image/*,application/pdf" />
            </div>
          </Card>
        </>
      ) : (
        <>
          <Card
            title={
              <>
                <UserRound size={17} /> Identité de la caution
              </>
            }
          >
            <div className="form-grid two-col">
              <Text label="Nom" value={text.last_name} onChange={set("last_name")} required />
              <Text label="Prénom" value={text.first_name} onChange={set("first_name")} />
              <Text label="Date de naissance" type="date" value={text.birth_date} onChange={set("birth_date")} />
              <Text label="Pays de naissance" value={text.birth_country} onChange={set("birth_country")} />
              <Text label="Activité de la caution" value={text.activity} onChange={set("activity")} />
              <Text label="Estimation de revenu (XOF)" type="number" value={text.estimated_income} onChange={set("estimated_income")} />
            </div>
          </Card>

          <Card
            title={
              <>
                <FileText size={17} /> Pièce d&apos;identité & photo
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
      )}

      <Card
        title={
          <>
            <Phone size={17} /> Coordonnées {isMoral ? "de l'entreprise" : ""}
          </>
        }
      >
        <div className="form-grid two-col">
          <Text label="Email" type="email" value={text.email} onChange={set("email")} />
          <Text label="Adresse" value={text.address} onChange={set("address")} />
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
            <HandCoins size={17} /> Plafond d&apos;engagement
          </>
        }
      >
        <p className="muted small" style={{ marginBottom: 12 }}>
          Montant maximum que cette caution peut couvrir au total. Laissez 0
          pour ne pas limiter.
        </p>
        <div className="form-grid two-col">
          <label className="field">
            <span>Plafond (XOF)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={ceiling}
              onChange={(e) => setCeiling(e.target.value)}
            />
          </label>
          {isEdit && initial && (
            <>
              <div className="field">
                <span>Déjà engagé</span>
                <strong>{formatMoney(initial.total_committed)}</strong>
              </div>
              <div className="field">
                <span>Disponible</span>
                <strong>{formatMoney(initial.available_ceiling)}</strong>
              </div>
            </>
          )}
        </div>
      </Card>

      <Card
        title={
          <>
            <FileText size={17} /> Documents complémentaires
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
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Annuler
        </button>
        <button className="btn btn-primary" disabled={mutation.isPending}>
          {mutation.isPending
            ? "Enregistrement…"
            : isEdit
              ? "Enregistrer les modifications"
              : "Enregistrer la caution"}
        </button>
      </div>
    </form>
  );
}

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
