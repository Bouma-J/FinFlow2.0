import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Banknote,
  Briefcase,
  ClipboardList,
  ExternalLink,
  FileText,
  HeartPulse,
  History,
  Home,
  Images,
  NotebookPen,
  Paperclip,
  Plus,
  ShieldCheck,
  Store,
  Trash2,
  UploadCloud,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import {
  useMemo,
  useState,
  useEffect,
  type FormEvent,
  type ReactNode,
} from "react";

import { api } from "@/api/client";
import { allCbsReferences } from "@/api/cbs";
import type { EffectiveConfiguration } from "@/api/configuration";
import type {
  Agency,
  CbsCatalogItem,
  ChecklistItem,
  Client,
  CreditApplication,
  CreditDocument,
  CreditProduct,
  Paginated,
} from "@/api/types";
import {
  ClientAutocomplete,
  clientOptionLabel,
} from "@/components/ClientAutocomplete";
import { useAuth } from "@/auth/AuthContext";

const PERIODICITY_FALLBACK = [
  { value: "DAILY", label: "Journalier" },
  { value: "WEEKLY", label: "Hebdomadaire" },
  { value: "BIMONTHLY", label: "Bimensuelle" },
  { value: "MONTHLY", label: "Mensuelle" },
  { value: "QUARTERLY", label: "Trimestrielle" },
  { value: "SEMIANNUAL", label: "Semestrielle" },
  { value: "ANNUAL", label: "Annuelle" },
];
const MECHANISM_FALLBACK = [
  { value: "DEGRESSIVE", label: "Amortissement dégressif" },
  { value: "IN_FINE", label: "In fine (capital à terme)" },
  { value: "BULLET", label: "Remboursement unique (bullet)" },
];
const CURRENCIES_FALLBACK = [
  { value: "XOF", label: "F CFA (XOF)" },
  { value: "XAF", label: "F CFA (XAF)" },
  { value: "EUR", label: "Euro (EUR)" },
  { value: "USD", label: "Dollar US (USD)" },
  { value: "GNF", label: "Franc guinéen (GNF)" },
  { value: "MAD", label: "Dirham marocain (MAD)" },
];
const TAX_REGIME = [
  { value: "SYNTHETIC", label: "Impôt synthétique" },
  { value: "REAL", label: "Régime réel" },
  { value: "SPECIFIC_EXEMPTION", label: "Exonérations spécifiques" },
  { value: "INFORMAL", label: "Secteur informel" },
];
const CATCHMENT = [
  { value: "LOCAL", label: "Local" },
  { value: "NATIONAL", label: "National" },
  { value: "EXPORT", label: "Export" },
];
const PREMISES = [
  { value: "OWNER", label: "Propriétaire" },
  { value: "TENANT", label: "Locataire" },
];

const TEXT_KEYS = [
  "product", "agency", "currency",
  "amount_requested", "amount_proposed", "interest_rate",
  "fees_rate", "mandatory_savings_rate",
  "periodicity", "duration_months", "first_due_date",
  "repayment_mechanism", "purpose_type", "financing_object", "purpose",
  "project_total_cost", "personal_contribution",
  "activity_start_date", "exact_address", "clientele",
  "tax_regime",
  "avg_client_payment_days", "avg_supplier_payment_days",
  "catchment_area",
  "premises_status",
  "employer_name", "contract_type", "dependents_count",
  "client_account_number", "relationship_start_date",
  "avg_monthly_credit_movements",
  "insurance_company", "insurance_premium", "insurance_policy_number", "insurance_expiry_date",
  "special_conditions", "suspensive_conditions",
  "beneficial_owner", "funds_origin",
] as const;

type TextKey = (typeof TEXT_KEYS)[number];
type TextState = Record<TextKey, string>;

const BOOL_KEYS = [
  "salary_domiciliation",
  "has_credit_insurance", "is_pep",
] as const;
type BoolKey = (typeof BOOL_KEYS)[number];
type BoolState = Record<BoolKey, boolean>;

// Champs texte libres où une valeur vide est valide côté backend (blank=True).
const TEXT_ONLY_KEYS = new Set<string>([
  "purpose", "exact_address", "clientele",
  "employer_name", "client_account_number",
  "insurance_company", "insurance_policy_number", "special_conditions",
  "suspensive_conditions", "beneficial_owner", "funds_origin",
]);

const CONTRACT_TYPES = [
  { value: "CDI", label: "CDI" },
  { value: "CDD", label: "CDD" },
  { value: "CIVIL_SERVANT", label: "Fonctionnaire" },
  { value: "INDEPENDENT", label: "Indépendant" },
  { value: "RETIRED", label: "Retraité" },
  { value: "OTHER", label: "Autre" },
];
const PURPOSE_TYPES = [
  { value: "WORKING_CAPITAL", label: "Fonds de roulement" },
  { value: "EQUIPMENT", label: "Investissement / équipement" },
  { value: "STOCK", label: "Achat de stock" },
  { value: "REAL_ESTATE", label: "Immobilier" },
  { value: "TREASURY", label: "Trésorerie" },
  { value: "CONSUMPTION", label: "Consommation" },
  { value: "OTHER", label: "Autre" },
];

/** Vision code → PurposeType FinFlow (aligné backend ref_sync._PURPOSE_HINTS) */
const PURPOSE_TYPES_CORPORATE = new Set(
  PURPOSE_TYPES.filter((p) => p.value !== "CONSUMPTION").map((p) => p.value),
);
const PURPOSE_TYPES_INDIVIDUAL = new Set([
  "CONSUMPTION",
  "REAL_ESTATE",
  "EQUIPMENT",
  "TREASURY",
  "OTHER",
]);

const CHECKLIST_COMMON = [
  "Pièce d'identité",
  "Justificatif de domicile",
  "Lettre de demande",
  "Relevés bancaires (6 mois)",
];
const CHECKLIST_INDIVIDUAL = [
  "Justificatifs de revenus / bulletins de salaire",
  "Attestation de travail",
];
const CHECKLIST_CORPORATE = [
  "RCCM",
  "IFU / NINEA",
  "États financiers (2 derniers exercices)",
  "Statuts de la société",
  "PV autorisant l'emprunt",
];

const emptyText = (): TextState =>
  ({
    ...Object.fromEntries(TEXT_KEYS.map((k) => [k, ""])),
    currency: "XOF",
    periodicity: "MONTHLY",
    duration_months: "12",
  }) as TextState;

const FIELD_LABELS: Record<string, string> = {
  client: "Client",
  product: "Type de crédit",
  agency: "Agence",
  currency: "Devise",
  amount_requested: "Montant demandé",
  amount_proposed: "Montant proposé",
  interest_rate: "Taux d'intérêt",
  fees_rate: "Frais de dossier",
  mandatory_savings_rate: "Taux d'épargne obligatoire",
  periodicity: "Périodicité",
  duration_months: "Durée du crédit",
  first_due_date: "Date de première échéance",
  repayment_mechanism: "Mécanisme de remboursement",
  purpose: "Détails de la demande",
  request_letter_scan: "Scan de la lettre de demande",
  activity_start_date: "Date de création",
  exact_address: "Adresse exacte",
  clientele: "Clientèle",
  tax_regime: "Régime fiscal",
  avg_client_payment_days: "Délai moyen paiement clients",
  avg_supplier_payment_days: "Délai moyen paiement fournisseurs",
  catchment_area: "Zone de chalandise",
  premises_status: "Statut d'occupation des locaux",
  purpose_type: "Objet du financement",
  financing_object: "Objet de financement CBS",
  project_total_cost: "Coût total du projet",
  personal_contribution: "Apport personnel",
  employer_name: "Employeur",
  contract_type: "Type de contrat",
  dependents_count: "Personnes à charge",
  client_account_number: "Numéro de compte",
  relationship_start_date: "Début de la relation",
  avg_monthly_credit_movements: "Mouvements créditeurs mensuels moyens",
  insurance_company: "Compagnie d'assurance",
  insurance_premium: "Prime d'assurance",
  special_conditions: "Conditions particulières",
  suspensive_conditions: "Conditions suspensives",
  beneficial_owner: "Bénéficiaire effectif",
  funds_origin: "Origine des fonds / apport",
};

const REQUIRED_FIELDS: { key: string; label: string }[] = [
  { key: "client", label: FIELD_LABELS.client },
  { key: "product", label: FIELD_LABELS.product },
  { key: "amount_requested", label: FIELD_LABELS.amount_requested },
  { key: "duration_months", label: FIELD_LABELS.duration_months },
];

const PERIODS_PER_YEAR: Record<string, number> = {
  DAILY: 360,
  WEEKLY: 52,
  BIMONTHLY: 24,
  MONTHLY: 12,
  QUARTERLY: 4,
  SEMIANNUAL: 2,
  ANNUAL: 1,
};

function computeLastDueDate(
  firstDue: string,
  periodicity: string,
  durationMonths: number,
  periodsPerYearMap: Record<string, number> = PERIODS_PER_YEAR,
): string {
  if (!firstDue || !periodicity || !durationMonths) return "";
  const perYear = periodsPerYearMap[periodicity];
  if (!perYear) return "";
  const count = Math.max(1, Math.ceil((durationMonths / 12) * perYear));
  const steps = count - 1;
  const d = new Date(firstDue);
  if (Number.isNaN(d.getTime())) return "";
  if (periodicity === "DAILY") d.setDate(d.getDate() + steps);
  else if (periodicity === "WEEKLY") d.setDate(d.getDate() + steps * 7);
  else if (periodicity === "BIMONTHLY") d.setDate(d.getDate() + steps * 15);
  else {
    const monthsMap: Record<string, number> = {
      MONTHLY: 1,
      QUARTERLY: 3,
      SEMIANNUAL: 6,
      ANNUAL: 12,
    };
    const months = monthsMap[periodicity] ?? Math.max(1, Math.round(12 / perYear));
    d.setMonth(d.getMonth() + steps * months);
  }
  return d.toISOString().slice(0, 10);
}

function textFromApp(app: CreditApplication): TextState {
  const state = emptyText();
  for (const key of TEXT_KEYS) {
    const value = (app as unknown as Record<string, unknown>)[key];
    state[key] = value === null || value === undefined ? "" : String(value);
  }
  state.financing_object = app.financing_object || app.cbs_refs?.financing_object?.id || "";
  return state;
}

export function CreditApplicationForm({
  initial,
  defaultClientId,
  onCreated,
  onCancel,
}: {
  initial?: CreditApplication;
  defaultClientId?: string;
  onCreated: (app: CreditApplication) => void;
  onCancel: () => void;
}) {
  const qc = useQueryClient();
  const { user, activeTenant } = useAuth();
  const isEdit = !!initial;
  const [client, setClient] = useState(initial?.client ?? defaultClientId ?? "");
  const [text, setText] = useState<TextState>(
    initial ? textFromApp(initial) : emptyText(),
  );
  const [bools, setBools] = useState<BoolState>(() => {
    const src = initial as unknown as Record<string, unknown> | undefined;
    return Object.fromEntries(
      BOOL_KEYS.map((k) => [k, Boolean(src?.[k])]),
    ) as BoolState;
  });
  const [checklist, setChecklist] = useState<ChecklistItem[]>(
    initial?.document_checklist ?? [],
  );
  const [newItem, setNewItem] = useState("");
  const [letter, setLetter] = useState<File | null>(null);
  const [stockPhotos, setStockPhotos] = useState<File[]>([]);
  // Scans en attente d'envoi, indexés par libellé de pièce.
  const [pendingFiles, setPendingFiles] = useState<Record<string, File>>({});
  // Pièces déjà scannées (mode édition), indexées par libellé.
  const [documents, setDocuments] = useState<CreditDocument[]>(
    initial?.documents ?? [],
  );
  const [extraFees, setExtraFees] = useState<
    { key: string; label: string; mode: "PERCENT" | "AMOUNT"; value: string }[]
  >(() =>
    (initial?.extra_fees ?? []).map((f, i) => ({
      key: f.id || `fee-${i}`,
      label: f.label,
      mode: f.mode === "PERCENT" ? "PERCENT" : "AMOUNT",
      value: f.value ?? "",
    })),
  );
  const [error, setError] = useState<string | null>(null);

  const docByLabel = useMemo(() => {
    const map: Record<string, CreditDocument> = {};
    for (const doc of documents) if (doc.label) map[doc.label] = doc;
    return map;
  }, [documents]);

  const { data: products } = useQuery({
    queryKey: ["credit-products"],
    queryFn: async () =>
      (await api.get<Paginated<CreditProduct>>("/credit-products/")).data,
  });

  const { data: agencies } = useQuery({
    queryKey: ["agencies"],
    queryFn: async () =>
      (await api.get<Paginated<Agency>>("/agencies/", { params: { page_size: 100 } }))
        .data,
  });

  const { data: periodicities } = useQuery({
    queryKey: ["loan-periodicities", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/loan-periodicities/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });

  const { data: repaymentMethods } = useQuery({
    queryKey: ["repayment-methods", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/repayment-methods/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });

  const { data: currencies } = useQuery({
    queryKey: ["currencies", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/currencies/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });

  const financingObjectsQuery = useQuery({
    queryKey: ["financing-objects", activeTenant],
    queryFn: () => allCbsReferences<CbsCatalogItem>("/financing-objects/", { is_active: true }),
  });
  const financingObjects = financingObjectsQuery.data ?? [];
  const financingObjectOptions = useMemo(
    () => financingObjects
      .filter((row) => row.cbs_code.trim())
      .map((row) => ({ value: row.id, label: `${row.label} — ${row.cbs_code}` })),
    [financingObjects],
  );

  const periodicityOptions = useMemo(() => {
    const rows = periodicities?.results ?? [];
    if (!rows.length) return PERIODICITY_FALLBACK;
    return rows.map((r) => ({
      value: r.code,
      label: r.cbs_code ? `${r.label} (${r.cbs_code})` : r.label,
    }));
  }, [periodicities]);

  const mechanismOptions = useMemo(() => {
    const rows = repaymentMethods?.results ?? [];
    if (!rows.length) return MECHANISM_FALLBACK;
    return rows.map((r) => ({
      value: r.code,
      label: r.label,
    }));
  }, [repaymentMethods]);

  const currencyOptions = useMemo(() => {
    const rows = currencies?.results ?? [];
    if (!rows.length) return CURRENCIES_FALLBACK;
    return rows.map((r) => ({
      value: r.code,
      label: r.cbs_code ? `${r.label} (${r.cbs_code})` : r.label,
    }));
  }, [currencies]);

  const periodsPerYear = useMemo(() => {
    const map: Record<string, number> = { ...PERIODS_PER_YEAR };
    for (const row of periodicities?.results ?? []) {
      if (row.periods_per_year) map[row.code] = row.periods_per_year;
    }
    return map;
  }, [periodicities]);

  const selectedClientQuery = useQuery({
    queryKey: ["client", client],
    enabled: !!client,
    queryFn: async () => (await api.get<Client>(`/clients/${client}/`)).data,
  });
  const selectedClient = selectedClientQuery.data;

  const clientType = selectedClient?.client_type ?? initial?.client_type;
  const isCorporate = clientType === "CORPORATE";
  const isGroupement = clientType === "PROFESSIONAL";
  const isLegalEntity = isCorporate || isGroupement;
  const isIndividual = clientType === "INDIVIDUAL";
  const showTypedSections = !!clientType;
  const configuration = useQuery({
    queryKey: ["credit-configuration-context", initial?.id, text.product, text.agency, clientType],
    enabled: !!text.product && !!clientType,
    queryFn: async () => {
      const unchangedContext = initial?.id && text.product === initial.product && (text.agency || "") === (initial.agency || "") && client === initial.client;
      return (await api.get<EffectiveConfiguration>(unchangedContext ? `/credit-applications/${initial.id}/configuration/` : "/credit-applications/configuration-context/", {
        params: unchangedContext ? {} : { product: text.product, agency: text.agency, client_type: clientType },
      })).data;
    },
  });

  const purposeOptions = useMemo(() => {
    const allowed = isLegalEntity
      ? PURPOSE_TYPES_CORPORATE
      : isIndividual
        ? PURPOSE_TYPES_INDIVIDUAL
        : null;
    return PURPOSE_TYPES.filter((p) => !allowed || allowed.has(p.value));
  }, [isLegalEntity, isIndividual]);

  const canPickAgency =
    user?.is_group_level || user?.data_scope === "TENANT";

  // Sections de navigation, filtrées selon le type de client.
  const navSections = useMemo(
    () =>
      [
        { id: "sec-conditions", icon: Banknote, label: "Conditions du crédit", show: true },
        { id: "sec-financing", icon: Wallet, label: "Plan de financement", show: showTypedSections },
        { id: "sec-activity", icon: Store, label: isGroupement ? "Activité du groupement" : "Activité de l'entreprise", show: showTypedSections && isLegalEntity },
        { id: "sec-market", icon: Users, label: "Environnement commercial", show: showTypedSections && isLegalEntity },
        { id: "sec-applicant", icon: Briefcase, label: "Profil du demandeur", show: showTypedSections && isIndividual },
        { id: "sec-banking", icon: History, label: "Relation bancaire", show: showTypedSections },
        { id: "sec-insurance", icon: HeartPulse, label: "Assurance", show: showTypedSections },
        { id: "sec-compliance", icon: ShieldCheck, label: "Conformité (LBC-FT)", show: showTypedSections },
        { id: "sec-special", icon: NotebookPen, label: "Conditions particulières", show: showTypedSections },
        { id: "sec-documents", icon: ClipboardList, label: "Pièces du dossier", show: showTypedSections },
      ].filter((s) => s.show),
    [showTypedSections, isLegalEntity, isIndividual, isGroupement],
  );

  const [activeSection, setActiveSection] = useState("sec-conditions");

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
        if (visible[0]) setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [navSections.length]);

  function scrollToSection(id: string) {
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    if (!isEdit && user?.agency && !text.agency) {
      setText((prev) => ({ ...prev, agency: user.agency! }));
    }
  }, [isEdit, user?.agency, text.agency]);

  useEffect(() => {
    if (isEdit || !clientType) return;
    const labels = [
      ...CHECKLIST_COMMON,
      ...(isLegalEntity ? CHECKLIST_CORPORATE : CHECKLIST_INDIVIDUAL),
    ];
    setChecklist((prev) =>
      labels.map((label) => {
        const existing = prev.find((item) => item.label === label);
        return { label, provided: existing?.provided ?? false };
      }),
    );
  }, [isEdit, clientType, isLegalEntity]);

  function loadDefaultChecklist() {
    const labels = [
      ...CHECKLIST_COMMON,
      ...(isLegalEntity ? CHECKLIST_CORPORATE : CHECKLIST_INDIVIDUAL),
    ];
    setChecklist((prev) => {
      const existing = new Set(prev.map((i) => i.label));
      const added = labels
        .filter((l) => !existing.has(l))
        .map((label) => ({ label, provided: false }));
      return [...prev, ...added];
    });
  }

  function addChecklistItem() {
    const label = newItem.trim();
    if (!label) return;
    setChecklist((prev) => [...prev, { label, provided: false }]);
    setNewItem("");
  }

  function attachScan(label: string, file: File | null) {
    setPendingFiles((prev) => {
      const next = { ...prev };
      if (file) next[label] = file;
      else delete next[label];
      return next;
    });
    if (file) {
      setChecklist((prev) =>
        prev.map((it) => (it.label === label ? { ...it, provided: true } : it)),
      );
    }
  }

  function removeExistingDoc(doc: CreditDocument) {
    setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
    api.delete(`/credit-documents/${doc.id}/`).catch(() => {
      // En cas d'échec, on recharge la liste réelle depuis le serveur.
      qc.invalidateQueries({ queryKey: ["credit-application", initial?.id] });
    });
  }

  const lastDue = useMemo(
    () =>
      computeLastDueDate(
        text.first_due_date,
        text.periodicity,
        Number(text.duration_months),
        periodsPerYear,
      ),
    [text.first_due_date, text.periodicity, text.duration_months, periodsPerYear],
  );

  const mutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("client", client);
      for (const key of TEXT_KEYS) {
        const value = text[key].trim();
        // Champs texte : on autorise l'effacement en édition ; les champs
        // numériques/date vides ne sont pas envoyés (évite les erreurs).
        if (value) fd.append(key, value);
        else if (isEdit && TEXT_ONLY_KEYS.has(key)) fd.append(key, "");
      }
      if (isEdit && !text.financing_object) fd.set("financing_object", "");
      for (const key of BOOL_KEYS) {
        fd.append(key, bools[key] ? "true" : "false");
      }
      fd.append("document_checklist", JSON.stringify(checklist));
      fd.append(
        "extra_fees",
        JSON.stringify(
          extraFees
            .filter((f) => f.label.trim() && f.value.trim())
            .map((f) => ({
              label: f.label.trim(),
              mode: f.mode,
              value: f.value.trim(),
            })),
        ),
      );
      if (letter) fd.append("request_letter_scan", letter);
      for (const photo of stockPhotos) fd.append("stock_photos", photo);
      const app = isEdit
        ? (
            await api.patch<CreditApplication>(
              `/credit-applications/${initial!.id}/`,
              fd,
            )
          ).data
        : (await api.post<CreditApplication>("/credit-applications/", fd)).data;

      // Envoi des scans joints à chaque pièce, une fois le dossier enregistré.
      const entries = Object.entries(pendingFiles);
      for (const [label, file] of entries) {
        const docFd = new FormData();
        docFd.append("application", app.id);
        docFd.append("label", label);
        docFd.append("file", file);
        await api.post("/credit-documents/", docFd);
      }
      return app;
    },
    onSuccess: (app) => {
      setPendingFiles({});
      qc.invalidateQueries({ queryKey: ["credit-applications"] });
      qc.invalidateQueries({ queryKey: ["credit-application", app.id] });
      onCreated(app);
    },
    onError: (e: unknown) => {
      const resp = (
        e as { response?: { status?: number; data?: unknown } }
      )?.response;
      const data = resp?.data;
      const errors =
        data && typeof data === "object" && "errors" in data
          ? (data as { errors: unknown }).errors
          : data;
      // Erreurs de validation champ par champ (objet clé -> messages).
      if (
        errors &&
        typeof errors === "object" &&
        !Array.isArray(errors)
      ) {
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
      // Réponses non-JSON (nginx, erreurs serveur) : message contextualisé.
      const status = resp?.status;
      if (status === 413) {
        setError(
          "Les fichiers joints sont trop volumineux. Réduisez leur taille (photos/scan) puis réessayez.",
        );
      } else if (status && status >= 500) {
        setError(
          "Erreur serveur lors de l'enregistrement. Réessayez ou contactez l'administrateur.",
        );
      } else if (!resp) {
        setError("Connexion au serveur impossible. Vérifiez votre réseau.");
      } else {
        setError(
          isEdit
            ? "Modification impossible. Vérifiez les champs."
            : "Création impossible. Vérifiez les champs requis.",
        );
      }
    },
  });

  const set = (key: TextKey) => (value: string) =>
    setText((prev) => ({ ...prev, [key]: value }));
  const setBool = (key: BoolKey) => (value: boolean) =>
    setBools((prev) => ({ ...prev, [key]: value }));

  const quotaPreview = useMemo(() => {
    const cost = Number(text.project_total_cost);
    const base = Number(text.amount_proposed || text.amount_requested);
    if (!cost || !base) return "";
    return `${((base / cost) * 100).toFixed(1)} %`;
  }, [text.project_total_cost, text.amount_proposed, text.amount_requested]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const missing = REQUIRED_FIELDS.filter(({ key }) =>
      key === "client" ? !client : !text[key as TextKey]?.trim(),
    ).map(({ label }) => label);
    if (missing.length > 0) {
      setError(
        `Veuillez renseigner ${
          missing.length > 1 ? "les champs obligatoires" : "le champ obligatoire"
        } : ${missing.join(", ")}.`,
      );
      return;
    }
    if (client && !clientType) {
      setError(selectedClientQuery.isError
        ? "Impossible de charger le profil du client. Rechargez-le avant de créer le dossier."
        : "Chargement du profil du client en cours. Réessayez dans un instant.");
      return;
    }
    if (text.product && client && (
      configuration.isLoading || configuration.isError || !configuration.data
    )) {
      setError(configuration.isError
        ? "Impossible de charger les exigences du dossier. Réessayez avant l’enregistrement."
        : "Chargement des exigences du dossier en cours. Réessayez dans un instant.");
      return;
    }
    if (configuration.data?.financing_object_required) {
      if (financingObjectsQuery.isLoading) {
        setError("Chargement du référentiel des objets de financement en cours. Réessayez dans un instant.");
        return;
      }
      if (financingObjectsQuery.isError) {
        setError("Impossible de charger le référentiel des objets de financement. Réessayez avant l’enregistrement.");
        return;
      }
      if (financingObjectOptions.length === 0) {
        setError("Le connecteur est en mode CBS, mais aucun objet de financement CBS actif avec un code importé n’est disponible. L’administrateur doit charger le référentiel avant la création.");
        return;
      }
      if (!text.financing_object) {
        setError("Sélectionnez l’objet de financement CBS exact pour cette demande.");
        return;
      }
    }
    setError(null);
    mutation.mutate();
  }

  return (
    <form className="credit-form" onSubmit={submit} noValidate>
      <aside className="credit-form-nav">
        <div className="credit-form-nav-inner">
          <p className="credit-form-nav-title">Sections</p>
          {navSections.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`credit-nav-item${activeSection === s.id ? " active" : ""}`}
              onClick={() => scrollToSection(s.id)}
            >
              <s.icon size={15} />
              <span>{s.label}</span>
            </button>
          ))}
        </div>
      </aside>

      <div className="credit-form-main stack">
        {configuration.data && <div className="card"><div className="card-body">
          <strong>Exigences applicables à la demande</strong>
          <p className="muted">{configuration.data.sources.map((source) => `${source.name} v${source.version}`).join(" → ") || "Politique de la filiale"}.
            Le profil salarié, indépendant ou mixte précisera les exigences lors de l'analyse financière.</p>
        </div></div>}
        <FormSection
          id="sec-conditions"
          icon={Banknote}
          title="Conditions du crédit"
          description="Client, produit et paramètres financiers de la demande."
        >
          <label className="field">
            <span>
              Client <em className="req"> *</em>
            </span>
            <ClientAutocomplete
              value={client}
              onChange={(id) => setClient(id)}
              required
              initialLabel={
                selectedClient ? clientOptionLabel(selectedClient) : undefined
              }
            />
          </label>
          {!client && (
            <p className="muted small" style={{ marginTop: 0 }}>
              Sélectionnez un client pour afficher les sections adaptées au
              profil (particulier, groupement ou entreprise).
            </p>
          )}
          {showTypedSections && (
            <div
              className={`profile-banner ${isLegalEntity ? "corp" : "indiv"}`}
            >
              {isCorporate ? (
                <Store size={16} />
              ) : isGroupement ? (
                <Users size={16} />
              ) : (
                <Briefcase size={16} />
              )}
              <span>
                Profil détecté :{" "}
                <strong>
                  {isCorporate
                    ? "Entreprise"
                    : isGroupement
                      ? "Groupement"
                      : "Particulier"}
                </strong>
                {selectedClient?.display_name
                  ? ` — ${selectedClient.display_name}`
                  : ""}
              </span>
            </div>
          )}
          <div className="form-grid two-col">
            <Select label="Type de crédit" value={text.product} onChange={set("product")} options={products?.results.map((p) => ({ value: p.id, label: p.label })) ?? []} required />
            {canPickAgency ? (
              <Select
                label="Agence"
                value={text.agency}
                onChange={set("agency")}
                options={
                  agencies?.results.map((a) => ({
                    value: a.id,
                    label: a.name,
                  })) ?? []
                }
              />
            ) : (
              <label className="field">
                <span>Agence</span>
                <input
                  value={
                    agencies?.results.find((a) => a.id === text.agency)?.name ??
                    "—"
                  }
                  readOnly
                  className="readonly"
                />
              </label>
            )}
            <Text label="Montant demandé" type="number" value={text.amount_requested} onChange={set("amount_requested")} required />
            <Text label="Montant proposé" type="number" value={text.amount_proposed} onChange={set("amount_proposed")} />
            <Select label="Devise" value={text.currency} onChange={set("currency")} options={currencyOptions} placeholder={null} />
            <Text label="Taux d'intérêt (%) — annuel" type="number" value={text.interest_rate} onChange={set("interest_rate")} />
            <Text label="Frais de dossier (%)" type="number" value={text.fees_rate} onChange={set("fees_rate")} />
            <Text label="Taux d'épargne obligatoire (%)" type="number" value={text.mandatory_savings_rate} onChange={set("mandatory_savings_rate")} />
            {configuration.data?.pricing.tariff.engine === "CONFIGURED" && <p className="muted small" style={{ gridColumn: "1 / -1" }}>
              Barème {configuration.data.pricing.tariff.currency} : les taux laissés vides sont déterminés par le produit et la tranche de montant / durée, puis fixés à la soumission. {configuration.data.pricing.tariff.charges.length} frais complémentaires configurés s'ajoutent automatiquement au détail des frais. Les taux non négociables et les plafonds sont contrôlés avant soumission.
              {!configuration.data.pricing.tariff.allow_manual_fees && " Les frais manuels sont interdits ; retirez les lignes manuelles existantes avant de soumettre."}
            </p>}
            <div className="field" style={{ gridColumn: "1 / -1" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <span style={{ fontWeight: 600 }}>Autres frais</span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={extraFees.length >= 100 || (configuration.data?.pricing.tariff.engine === "CONFIGURED" && !configuration.data.pricing.tariff.allow_manual_fees)}
                  onClick={() =>
                    setExtraFees((prev) => [
                      ...prev,
                      {
                        key: `${Date.now()}-${prev.length}`,
                        label: "",
                        mode: "AMOUNT" as const,
                        value: "",
                      },
                    ])
                  }
                >
                  <Plus size={14} />
                  Ajouter un frais
                </button>
              </div>
              <p className="muted small" style={{ marginTop: 0 }}>
                Le pourcentage s’applique sur le montant proposé / accordé.
                Les prélèvements sont réalisés dans le CBS. Fin Flow transmet le montant accordé et présente le détail des frais.
              </p>
              {extraFees.length === 0 ? (
                <p className="muted small">Aucun frais additionnel.</p>
              ) : (
                <div className="extra-fees-list">
                  {extraFees.map((fee, idx) => (
                    <div key={fee.key} className="extra-fee-row">
                      <label className="field">
                        <span>Intitulé</span>
                        <input
                          value={fee.label}
                          onChange={(e) => {
                            const v = e.target.value;
                            setExtraFees((prev) =>
                              prev.map((f, i) =>
                                i === idx ? { ...f, label: v } : f,
                              ),
                            );
                          }}
                          placeholder="Ex. commission, assurance…"
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Type</span>
                        <select
                          value={fee.mode}
                          onChange={(e) => {
                            const v = e.target.value as "PERCENT" | "AMOUNT";
                            setExtraFees((prev) =>
                              prev.map((f, i) =>
                                i === idx ? { ...f, mode: v } : f,
                              ),
                            );
                          }}
                        >
                          <option value="AMOUNT">Montant</option>
                          <option value="PERCENT">Pourcentage (%)</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>
                          {fee.mode === "PERCENT" ? "Taux (%)" : "Montant"}
                        </span>
                        <input
                          type="number"
                          min={0}
                          step="0.001"
                          value={fee.value}
                          onChange={(e) => {
                            const v = e.target.value;
                            setExtraFees((prev) =>
                              prev.map((f, i) =>
                                i === idx ? { ...f, value: v } : f,
                              ),
                            );
                          }}
                          required
                        />
                      </label>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() =>
                          setExtraFees((prev) =>
                            prev.filter((_, i) => i !== idx),
                          )
                        }
                        aria-label="Retirer"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <Select label="Périodicité" value={text.periodicity} onChange={set("periodicity")} options={periodicityOptions} placeholder={null} />
            <Text label="Durée du crédit (mois)" type="number" value={text.duration_months} onChange={set("duration_months")} required />
            <Text label="Date de première échéance" type="date" value={text.first_due_date} onChange={set("first_due_date")} />
            <label className="field">
              <span>Date de dernière échéance (auto)</span>
              <input value={lastDue || "—"} readOnly className="readonly" />
            </label>
            <Select label="Mécanisme de remboursement" value={text.repayment_mechanism} onChange={set("repayment_mechanism")} options={mechanismOptions} />
            <Select
              label="Type de besoin"
              value={text.purpose_type}
              onChange={set("purpose_type")}
              options={purposeOptions}
            />
            <Select
              label="Objet de financement CBS exact"
              required={configuration.data?.financing_object_required === true}
              value={text.financing_object}
              onChange={set("financing_object")}
              options={financingObjectOptions}
            />
            {configuration.isError && <p className="form-error" role="alert">
              Impossible de déterminer les exigences CBS du dossier.
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => configuration.refetch()}>Réessayer</button>
            </p>}
            {configuration.data?.financing_object_required && financingObjectsQuery.isLoading && <p className="muted" role="status">Chargement du référentiel CBS des objets de financement…</p>}
            {configuration.data?.financing_object_required && financingObjectsQuery.isError && <p className="form-error" role="alert">
              Référentiel des objets de financement impossible à charger.
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => financingObjectsQuery.refetch()}>Réessayer</button>
            </p>}
            {configuration.data?.financing_object_required && !financingObjectsQuery.isLoading && !financingObjectsQuery.isError && financingObjectOptions.length === 0 && <p className="form-error" role="alert">Le connecteur est en mode CBS, mais aucun objet de financement actif avec un code CBS importé n’est disponible. L’administrateur doit charger le référentiel.</p>}
            {configuration.data && !configuration.data.financing_object_required && !financingObjectsQuery.isLoading && !financingObjectsQuery.isError && financingObjectOptions.length === 0 && <p className="muted" role="status">Aucun objet CBS n’est importé. Le champ est facultatif dans la configuration actuelle ; l’administrateur devra charger le référentiel avant toute activation du mode CBS réel.</p>}
          </div>
          <label className="field">
            <span>Détails de la demande</span>
            <textarea rows={3} value={text.purpose} onChange={(e) => set("purpose")(e.target.value)} />
          </label>
          <FileField label="Scan de la lettre de demande" file={letter} onChange={setLetter} accept="image/*,application/pdf" />
        </FormSection>

        {showTypedSections && (
          <FormSection
            id="sec-financing"
            icon={Wallet}
            title="Plan de financement"
            description={
              isLegalEntity
                ? isGroupement
                  ? "Coût du projet et apport du groupement."
                  : "Coût du projet et apport de l'entreprise."
                : "Coût du besoin et apport personnel du demandeur."
            }
          >
            <div className="form-grid two-col">
              <Text
                label={isLegalEntity ? "Coût total du projet" : "Coût total du besoin"}
                type="number"
                value={text.project_total_cost}
                onChange={set("project_total_cost")}
              />
              <Text
                label={
                  isGroupement
                    ? "Apport du groupement"
                    : isCorporate
                      ? "Apport de l'entreprise"
                      : "Apport personnel"
                }
                type="number"
                value={text.personal_contribution}
                onChange={set("personal_contribution")}
              />
              <label className="field">
                <span>Quotité financée (auto)</span>
                <input value={quotaPreview || "—"} readOnly className="readonly" />
              </label>
            </div>
            <p className="muted small" style={{ marginBottom: 0 }}>
              La quotité financée = montant demandé / coût total
              {isLegalEntity ? " du projet" : " du besoin"}.
            </p>
          </FormSection>
        )}

        {showTypedSections && isLegalEntity && (
          <FormSection
            id="sec-activity"
            icon={Store}
            title={isGroupement ? "Activité du groupement" : "Activité de l'entreprise"}
            description="Contexte opérationnel. Le diagnostic sectoriel et l'effectif se saisissent dans l'analyse financière."
          >
            <div className="form-grid two-col">
              <Text label="Date de création" type="date" value={text.activity_start_date} onChange={set("activity_start_date")} />
              <Text label="Adresse de l'établissement" value={text.exact_address} onChange={set("exact_address")} />
              <Text label="Clientèle" value={text.clientele} onChange={set("clientele")} />
              <Select label="Régime fiscal" value={text.tax_regime} onChange={set("tax_regime")} options={TAX_REGIME} />
              <Select label="Statut d'occupation des locaux" value={text.premises_status} onChange={set("premises_status")} options={PREMISES} />
              <Text label="Délai moyen paiement clients (jours)" type="number" value={text.avg_client_payment_days} onChange={set("avg_client_payment_days")} />
              <Text label="Délai moyen paiement fournisseurs (jours)" type="number" value={text.avg_supplier_payment_days} onChange={set("avg_supplier_payment_days")} />
            </div>
            <MultiFileField label="Photos du stock" files={stockPhotos} onChange={setStockPhotos} />
            <p className="muted small" style={{ marginBottom: 0 }}>
              Secteur, saisonnalité, concurrence, effectif et chiffres
              (CA, marge, bilan) : saisis dans l&apos;analyse financière.
            </p>
          </FormSection>
        )}

        {showTypedSections && isLegalEntity && (
          <FormSection
            id="sec-market"
            icon={Users}
            title="Environnement commercial"
            description="Zone de chalandise. Concurrence et fournisseurs : analyse financière."
          >
            <div className="form-grid two-col">
              <Select label="Zone de chalandise" value={text.catchment_area} onChange={set("catchment_area")} options={CATCHMENT} />
            </div>
          </FormSection>
        )}

        {showTypedSections && isIndividual && (
          <FormSection
            id="sec-applicant"
            icon={Briefcase}
            title="Profil du demandeur"
            description="Situation professionnelle et logement. Ancienneté et revenus : analyse financière."
          >
            <div className="subsection-label">
              <Briefcase size={14} /> Emploi
            </div>
            <div className="form-grid two-col">
              <Text label="Employeur" value={text.employer_name} onChange={set("employer_name")} />
              <Select label="Type de contrat" value={text.contract_type} onChange={set("contract_type")} options={CONTRACT_TYPES} />
              <Text label="Personnes à charge" type="number" value={text.dependents_count} onChange={set("dependents_count")} />
            </div>
            <Check label="Domiciliation du salaire dans l'institution" checked={bools.salary_domiciliation} onChange={setBool("salary_domiciliation")} />
            <div className="subsection-label">
              <Home size={14} /> Logement
            </div>
            <div className="form-grid two-col">
              <Select label="Statut d'occupation du logement" value={text.premises_status} onChange={set("premises_status")} options={PREMISES} />
            </div>
          </FormSection>
        )}

        {showTypedSections && (
          <FormSection
            id="sec-banking"
            icon={History}
            title="Relation bancaire"
            description="Compte dans l'institution. Centrale des risques et incidents : analyse financière."
          >
            <div className="form-grid two-col">
              <Text label="Numéro de compte dans l'institution" value={text.client_account_number} onChange={set("client_account_number")} />
              <Text label="Début de la relation" type="date" value={text.relationship_start_date} onChange={set("relationship_start_date")} />
              <Text label="Mouvements créditeurs mensuels moyens" type="number" value={text.avg_monthly_credit_movements} onChange={set("avg_monthly_credit_movements")} />
            </div>
          </FormSection>
        )}

        {showTypedSections && (
          <FormSection
            id="sec-insurance"
            icon={HeartPulse}
            title="Assurance"
            description="Couverture décès-invalidité du crédit."
          >
            <Check label="Assurance décès-invalidité (ADI)" checked={bools.has_credit_insurance} onChange={setBool("has_credit_insurance")} />
            <div className="form-grid two-col">
              <Text label="Compagnie d'assurance" value={text.insurance_company} onChange={set("insurance_company")} />
              <Text label="Numéro de police" value={text.insurance_policy_number} onChange={set("insurance_policy_number")} />
              <Text label="Fin de couverture" type="date" value={text.insurance_expiry_date} onChange={set("insurance_expiry_date")} />
              <Text label="Prime d'assurance" type="number" value={text.insurance_premium} onChange={set("insurance_premium")} />
            </div>
          </FormSection>
        )}

        {showTypedSections && (
          <FormSection
            id="sec-compliance"
            icon={ShieldCheck}
            title="Conformité (LBC-FT)"
            description="Lutte contre le blanchiment et le financement du terrorisme."
          >
            <div className="form-grid two-col">
              {isLegalEntity && (
                <Text label="Bénéficiaire effectif" value={text.beneficial_owner} onChange={set("beneficial_owner")} />
              )}
              <Text label="Origine des fonds / apport" value={text.funds_origin} onChange={set("funds_origin")} />
            </div>
            <Check label="Personne politiquement exposée (PPE)" checked={bools.is_pep} onChange={setBool("is_pep")} />
          </FormSection>
        )}

        {showTypedSections && (
          <FormSection
            id="sec-special"
            icon={NotebookPen}
            title="Conditions particulières"
            description="Clauses spécifiques et conditions préalables à la mise en place."
          >
            <label className="field">
              <span>Conditions particulières</span>
              <textarea rows={2} value={text.special_conditions} onChange={(e) => set("special_conditions")(e.target.value)} />
            </label>
            <label className="field">
              <span>Conditions suspensives (avant mise en place)</span>
              <textarea rows={2} value={text.suspensive_conditions} onChange={(e) => set("suspensive_conditions")(e.target.value)} />
            </label>
          </FormSection>
        )}

        {showTypedSections && (
          <FormSection
            id="sec-documents"
            icon={ClipboardList}
            title="Pièces du dossier"
            description="Liste des pièces requises, avec scan à joindre."
          >
            <div className="checklist">
              {checklist.length === 0 && (
                <p className="muted small">Aucune pièce listée pour le moment.</p>
              )}
              {checklist.map((item, idx) => {
                const existingDoc = docByLabel[item.label];
                const pending = pendingFiles[item.label];
                return (
                  <div className="checklist-row" key={`${item.label}-${idx}`}>
                    <label className="check-inline">
                      <input
                        type="checkbox"
                        checked={item.provided}
                        onChange={(e) =>
                          setChecklist((prev) =>
                            prev.map((it, i) =>
                              i === idx ? { ...it, provided: e.target.checked } : it,
                            ),
                          )
                        }
                      />
                      <span>{item.label}</span>
                    </label>
                    <div className="checklist-doc">
                      {existingDoc ? (
                        <>
                          <a
                            className="doc-chip"
                            href={existingDoc.file}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <ExternalLink size={14} />
                            Voir le scan
                          </a>
                          <button
                            type="button"
                            className="btn btn-ghost btn-icon"
                            onClick={() => removeExistingDoc(existingDoc)}
                            aria-label="Retirer le scan"
                          >
                            <Trash2 size={15} />
                          </button>
                        </>
                      ) : pending ? (
                        <>
                          <span className="doc-chip">
                            <FileText size={14} />
                            {pending.name}
                          </span>
                          <button
                            type="button"
                            className="btn btn-ghost btn-icon"
                            onClick={() => attachScan(item.label, null)}
                            aria-label="Retirer le scan"
                          >
                            <Trash2 size={15} />
                          </button>
                        </>
                      ) : (
                        <label className="scan-btn">
                          <Paperclip size={14} />
                          Joindre un scan
                          <input
                            type="file"
                            accept="image/*,application/pdf"
                            onChange={(e) =>
                              attachScan(item.label, e.target.files?.[0] ?? null)
                            }
                          />
                        </label>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-icon"
                      onClick={() =>
                        setChecklist((prev) => prev.filter((_, i) => i !== idx))
                      }
                      aria-label="Supprimer la pièce"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="checklist-add">
              <input
                value={newItem}
                placeholder="Ajouter une pièce…"
                onChange={(e) => setNewItem(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addChecklistItem();
                  }
                }}
              />
              <button type="button" className="btn btn-ghost" onClick={addChecklistItem}>
                Ajouter
              </button>
              <button type="button" className="btn btn-ghost" onClick={loadDefaultChecklist}>
                Liste type{" "}
                {isGroupement
                  ? "groupement"
                  : isCorporate
                    ? "entreprise"
                    : "particulier"}
              </button>
            </div>
          </FormSection>
        )}

        {error && <div className="form-error">{error}</div>}
        <div className="credit-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Annuler
          </button>
          <button className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending
              ? "Enregistrement…"
              : isEdit
                ? "Enregistrer les modifications"
                : "Enregistrer le dossier"}
          </button>
        </div>
      </div>
    </form>
  );
}

function FormSection({
  id,
  icon: Icon,
  title,
  description,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="card form-section">
      <div className="card-title form-section-head">
        <span className="form-section-icon">
          <Icon size={18} />
        </span>
        <div className="form-section-heading">
          <span className="form-section-title">{title}</span>
          {description && (
            <span className="form-section-desc">{description}</span>
          )}
        </div>
      </div>
      <div className="card-body">{children}</div>
    </section>
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
        onChange={(e) => onChange(e.target.value)}
        required={required}
      />
    </label>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="check-inline field">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  placeholder = "— Sélectionner —",
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string | null;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span>
        {label}
        {required && <em className="req"> *</em>}
      </span>
      <select required={required} value={value} onChange={(e) => onChange(e.target.value)}>
        {placeholder !== null && <option value="">{placeholder}</option>}
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
  accept,
}: {
  label: string;
  file: File | null;
  onChange: (f: File | null) => void;
  accept?: string;
}) {
  return (
    <label className="field file-field">
      <span>{label}</span>
      <div className={`file-drop${file ? " has-file" : ""}`}>
        <UploadCloud size={18} />
        <span className="file-name">{file ? file.name : "Choisir un fichier…"}</span>
        <input type="file" accept={accept} onChange={(e) => onChange(e.target.files?.[0] ?? null)} />
      </div>
    </label>
  );
}

function MultiFileField({
  label,
  files,
  onChange,
}: {
  label: string;
  files: File[];
  onChange: (f: File[]) => void;
}) {
  return (
    <label className="field file-field">
      <span>
        <Images size={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />
        {label}
      </span>
      <div className={`file-drop${files.length ? " has-file" : ""}`}>
        <UploadCloud size={18} />
        <span className="file-name">
          {files.length
            ? `${files.length} photo(s) sélectionnée(s)`
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
