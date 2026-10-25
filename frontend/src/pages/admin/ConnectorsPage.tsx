import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cable,
  KeyRound,
  PlugZap,
  Plus,
  Radio,
  Save,
  Settings2,
  X,
} from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { CbsConnector, IntegrationLog, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { isFinflowAdmin } from "@/auth/routePerms";
import {
  Badge,
  PageHeader,
  QueryStatus,
  TenantScopeNotice,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

/** Défauts Perfect alignés sur backend/apps/corebanking/perfect_defaults.py */
const PERFECT = {
  provider: "perfect",
  scope: "perfect",
  endpoints: {
    authentification: "gateway-perfect/authentification",
    adh_situation: "gateway-perfect/adh/situation",
    crd_simple: "gateway-perfect/crd/simple",
    crd_situation: "gateway-perfect/crd/situation",
    crd_impayes: "gateway-perfect/crd/impayes",
  },
  periodicity_map: {
    DAILY: "JOURNALIER",
    WEEKLY: "HEBDOMADAIRE",
    BIMONTHLY: "BIMENSUEL",
    MONTHLY: "MENSUEL",
    QUARTERLY: "TRIMESTRIEL",
    SEMIANNUAL: "SEMESTRIEL",
    ANNUAL: "ANNUEL",
  },
  purpose_map: {
    WORKING_CAPITAL: "FONDS_ROULEMENT",
    EQUIPMENT: "EQUIPEMENT",
    STOCK: "STOCK",
    REAL_ESTATE: "IMMOBILIER",
    TREASURY: "TRESORERIE",
    CONSUMPTION: "CONSOMMATION",
    OTHER: "AUTRE",
  },
  defaults: {
    idPointService: "PS01",
    idGestionnaire: "GEST01",
    idProduitRemb: "COMPTE-COURANT",
  },
} as const;

type ConnectorForm = {
  name: string;
  protocol: string;
  base_url: string;
  timeout_seconds: number;
  max_retries: number;
  is_active: boolean;
  verify_ssl: boolean;
  auth_username: string;
  auth_password: string;
  auth_token: string;
  auth_scope: string;
  auth_path: string;
  adh_situation_path: string;
  crd_simple_path: string;
  crd_situation_path: string;
  crd_impayes_path: string;
  disburse_mode: "LOCAL" | "CBS";
  id_point_service: string;
  id_gestionnaire: string;
  id_produit_remb: string;
  sim_loan_settled: boolean;
  sim_client_outstanding: string;
};

const EMPTY_FORM: ConnectorForm = {
  name: "CBS Perfect",
  protocol: "REST",
  base_url: "",
  timeout_seconds: 30,
  max_retries: 3,
  is_active: true,
  verify_ssl: true,
  auth_username: "",
  auth_password: "",
  auth_token: "",
  auth_scope: PERFECT.scope,
  auth_path: PERFECT.endpoints.authentification,
  adh_situation_path: PERFECT.endpoints.adh_situation,
  crd_simple_path: PERFECT.endpoints.crd_simple,
  crd_situation_path: PERFECT.endpoints.crd_situation,
  crd_impayes_path: PERFECT.endpoints.crd_impayes,
  disburse_mode: "LOCAL",
  id_point_service: PERFECT.defaults.idPointService,
  id_gestionnaire: PERFECT.defaults.idGestionnaire,
  id_produit_remb: PERFECT.defaults.idProduitRemb,
  sim_loan_settled: true,
  sim_client_outstanding: "0",
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function formFromConnector(c: CbsConnector): ConnectorForm {
  const rules = asRecord(c.mapping_rules);
  const endpoints = asRecord(rules.endpoints);
  const disbursement = asRecord(rules.disbursement);
  const defaults = asRecord(disbursement.defaults);
  const simulate = asRecord(rules.simulate);
  const mode = String(disbursement.mode || "").toUpperCase();
  return {
    name: c.name,
    protocol: c.protocol || "REST",
    base_url: c.base_url || "",
    timeout_seconds: c.timeout_seconds ?? 30,
    max_retries: c.max_retries ?? 3,
    is_active: c.is_active,
    verify_ssl: rules.verify_ssl !== false,
    auth_username: "",
    auth_password: "",
    auth_token: "",
    auth_scope: PERFECT.scope,
    auth_path: str(
      endpoints.authentification,
      PERFECT.endpoints.authentification,
    ),
    adh_situation_path: str(
      endpoints.adh_situation,
      PERFECT.endpoints.adh_situation,
    ),
    crd_simple_path: str(endpoints.crd_simple, PERFECT.endpoints.crd_simple),
    crd_situation_path: str(
      endpoints.crd_situation,
      PERFECT.endpoints.crd_situation,
    ),
    crd_impayes_path: str(
      endpoints.crd_impayes,
      PERFECT.endpoints.crd_impayes,
    ),
    disburse_mode: mode === "CBS" ? "CBS" : "LOCAL",
    id_point_service: str(
      defaults.idPointService,
      PERFECT.defaults.idPointService,
    ),
    id_gestionnaire: str(
      defaults.idGestionnaire,
      PERFECT.defaults.idGestionnaire,
    ),
    id_produit_remb: str(
      defaults.idProduitRemb,
      PERFECT.defaults.idProduitRemb,
    ),
    sim_loan_settled: simulate.loan_settled_default !== false,
    sim_client_outstanding: String(
      simulate.client_outstanding_default ?? "0",
    ),
  };
}

function buildPayload(
  form: ConnectorForm,
  opts: { includeAuth: boolean; existing?: CbsConnector | null },
) {
  const existingRules = asRecord(opts.existing?.mapping_rules);
  const existingDisb = asRecord(existingRules.disbursement);
  const existingPurpose = asRecord(existingDisb.purpose_map);
  const existingPeriod = asRecord(existingDisb.periodicity_map);
  const existingEndpoints = asRecord(existingRules.endpoints);

  const mapping_rules = {
    provider: PERFECT.provider,
    force_simulate: form.disburse_mode === "LOCAL",
    verify_ssl: form.verify_ssl,
    endpoints: {
      ...existingEndpoints,
      authentification:
        form.auth_path.trim() || PERFECT.endpoints.authentification,
      adh_situation:
        form.adh_situation_path.trim() || PERFECT.endpoints.adh_situation,
      crd_simple: form.crd_simple_path.trim() || PERFECT.endpoints.crd_simple,
      crd_situation:
        form.crd_situation_path.trim() || PERFECT.endpoints.crd_situation,
      crd_impayes:
        form.crd_impayes_path.trim() || PERFECT.endpoints.crd_impayes,
    },
    disbursement: {
      mode: form.disburse_mode,
      defaults: {
        idPointService: form.id_point_service.trim(),
        idGestionnaire: form.id_gestionnaire.trim(),
        idProduitRemb: form.id_produit_remb.trim(),
      },
      // Conserve les maps syncées CBS ; ne réinjecte Perfect strings qu'à la création
      periodicity_map:
        Object.keys(existingPeriod).length > 0
          ? existingPeriod
          : { ...PERFECT.periodicity_map },
      purpose_map:
        Object.keys(existingPurpose).length > 0
          ? existingPurpose
          : { ...PERFECT.purpose_map },
    },
    simulate: {
      loan_settled_default: form.sim_loan_settled,
      loan_outstanding_default: "0",
      client_outstanding_default: form.sim_client_outstanding,
    },
  };

  const payload: Record<string, unknown> = {
    name: form.name.trim(),
    protocol: form.protocol,
    base_url: form.base_url.trim(),
    timeout_seconds: form.timeout_seconds,
    max_retries: form.max_retries,
    is_active: form.is_active,
    mapping_rules,
  };

  if (opts.includeAuth) {
    const auth_config: Record<string, string> = {
      scope: form.auth_scope.trim() || PERFECT.scope,
    };
    if (form.auth_username.trim()) {
      auth_config.username = form.auth_username.trim();
    }
    if (form.auth_password) auth_config.password = form.auth_password;
    if (form.auth_token.trim()) {
      auth_config.access_token = form.auth_token.trim();
    }
    payload.auth_config = auth_config;
  }

  return payload;
}

function connectorProvider(c: CbsConnector): string {
  return str(asRecord(c.mapping_rules).provider, "—");
}

function connectorMode(c: CbsConnector): string {
  const rules = asRecord(c.mapping_rules);
  const mode = str(asRecord(rules.disbursement).mode).toUpperCase();
  if (mode === "CBS" || mode === "LOCAL") return mode;
  if (rules.force_simulate) return "LOCAL";
  return c.base_url ? "CBS" : "LOCAL";
}

export function AdminConnectorsPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canView = hasPerm(user, "corebanking.view_corebankingconnector");
  const canAdd = hasPerm(user, "corebanking.add_corebankingconnector");
  const canChange = hasPerm(user, "corebanking.change_corebankingconnector");
  const canViewLogs = hasPerm(user, "corebanking.view_integrationlog");
  const canImportCbs = isFinflowAdmin(user) && canChange;

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<CbsConnector | null>(null);
  const [form, setForm] = useState<ConnectorForm>({ ...EMPTY_FORM });
  const [error, setError] = useState<string | null>(null);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const dossierFileRef = useRef<HTMLInputElement>(null);
  const [dossierTargetId, setDossierTargetId] = useState<string | null>(null);

  const connectors = useQuery({
    queryKey: ["cbs-connectors", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsConnector>>("/cbs-connectors/", {
          params: { page_size: 100 },
        })
      ).data,
    enabled: !needsTenant && canView,
  });

  const logs = useQuery({
    queryKey: ["integration-logs", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<IntegrationLog>>("/integration-logs/", {
          params: { page_size: 30, ordering: "-created_at" },
        })
      ).data,
    enabled: !needsTenant && canViewLogs,
  });

  const opsMetrics = useQuery({
    queryKey: ["ops-status", activeTenant],
    queryFn: async () =>
      (
        await api.get<{
          documents_soft_deleted?: number;
          celery?: {
            ok?: boolean;
            workers?: string[];
            queues?: Record<string, number>;
            broker_ping?: boolean;
            error?: string;
          };
        }>("/ops/status/")
      ).data,
    enabled: Boolean(user?.is_group_level || user?.is_staff),
    refetchInterval: 60_000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cbs-connectors"] });
    qc.invalidateQueries({ queryKey: ["integration-logs"] });
  };

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post(
          "/cbs-connectors/",
          buildPayload(form, { includeAuth: true }),
        )
      ).data,
    onSuccess: () => {
      invalidate();
      setShowForm(false);
      setForm({ ...EMPTY_FORM });
      setError(null);
    },
    onError: (err) =>
      setError(
        apiErrorMessage(err, "Création impossible. Vérifiez les champs."),
      ),
  });

  const patch = useMutation({
    mutationFn: async () => {
      if (!editing) throw new Error("missing");
      const hasAuth =
        Boolean(form.auth_username.trim()) ||
        Boolean(form.auth_password) ||
        Boolean(form.auth_token.trim());
      return (
        await api.patch(
          `/cbs-connectors/${editing.id}/`,
          buildPayload(form, { includeAuth: hasAuth, existing: editing }),
        )
      ).data;
    },
    onSuccess: () => {
      invalidate();
      setEditing(null);
      setShowForm(false);
      setForm({ ...EMPTY_FORM });
      setError(null);
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Mise à jour impossible.")),
  });

  const toggleActive = useMutation({
    mutationFn: async (c: CbsConnector) =>
      (
        await api.patch(`/cbs-connectors/${c.id}/`, {
          is_active: !c.is_active,
        })
      ).data,
    onSuccess: () => invalidate(),
  });

  const testPing = useMutation({
    mutationFn: async (id: string) =>
      (
        await api.post(`/cbs-connectors/${id}/test_operation/`, {
          operation: "PING",
          payload: {},
        })
      ).data as { status?: string; error_message?: string },
    onSuccess: (log) => {
      setTestMsg(
        log.status === "SUCCESS"
          ? "Test PING réussi."
          : `Test PING : ${log.status || "échec"}${
              log.error_message ? ` — ${log.error_message}` : ""
            }`,
      );
    },
    onError: (err) =>
      setTestMsg(apiErrorMessage(err, "Échec du test PING.")),
  });

  const importPortfolio = useMutation({
    mutationFn: async (payload: { id: string; file?: File }) => {
      if (payload.file) {
        const fd = new FormData();
        fd.append("file", payload.file);
        return (
          await api.post(`/cbs-connectors/${payload.id}/import-portfolio/`, fd, {
            headers: { "Content-Type": "multipart/form-data" },
          })
        ).data as { detail?: string; status?: string };
      }
      return (
        await api.post(`/cbs-connectors/${payload.id}/import-portfolio/`)
      ).data as { detail?: string; status?: string };
    },
    onSuccess: (data) => {
      setTestMsg(
        data.detail ||
          "Import des crédits CBS lancé. Les dossiers de recouvrement seront classés par tranche.",
      );
      invalidate();
      qc.invalidateQueries({ queryKey: ["collection-cases"] });
    },
    onError: (err) =>
      setTestMsg(
        apiErrorMessage(err, "Impossible d'importer les crédits CBS."),
      ),
  });

  const formOpen = showForm || Boolean(editing);
  const pending = create.isPending || patch.isPending;

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setShowForm(true);
    setError(null);
    setTestMsg(null);
  }

  function openEdit(c: CbsConnector) {
    setShowForm(false);
    setEditing(c);
    setForm(formFromConnector(c));
    setError(null);
    setTestMsg(null);
  }

  function closeForm() {
    setShowForm(false);
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setError(null);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (editing ? canChange : canAdd) {
      if (editing) patch.mutate();
      else create.mutate();
    } else {
      setError("Vous n'avez pas le droit de modifier ce connecteur.");
    }
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Cable}
          title="Connecteurs Core Banking"
          subtitle="Par filiale"
        />
        <TenantScopeNotice />
        {opsMetrics.data?.celery && (
          <div className="card" style={{ marginTop: 16, padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Celery / files</h3>
            <p className="muted small">
              Workers :{" "}
              {opsMetrics.data.celery.ok
                ? (opsMetrics.data.celery.workers ?? []).join(", ") || "ok"
                : opsMetrics.data.celery.error || "indisponible"}
              {" · "}
              File celery : {opsMetrics.data.celery.queues?.celery ?? "—"}
              {" · "}
              GED soft-delete : {opsMetrics.data.documents_soft_deleted ?? 0}
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={Cable}
        title="Connecteurs Core Banking"
        subtitle="API Perfect : authentification, crédits existants, mise en place"
        actions={
          (formOpen ? canChange || canAdd : canAdd) ? <button
            type="button"
            className="btn btn-primary"
            onClick={() => (formOpen ? closeForm() : openCreate())}
          >
            {formOpen ? <X size={16} /> : <Plus size={16} />}
            {formOpen ? "Fermer" : "Nouveau connecteur Perfect"}
          </button>
            : undefined
        }
      />

      {testMsg && (
        <div className="form-hint" style={{ marginBottom: 12 }}>
          {testMsg}
        </div>
      )}

      {formOpen && (editing ? canChange : canAdd) && (
        <form className="tenant-compose-form" onSubmit={onSubmit}>
          <div className="form-section-head">
            <div className="form-section-icon">
              <PlugZap size={18} />
            </div>
            <div className="form-section-heading">
              <div className="form-section-title">
                {editing
                  ? "Modifier le connecteur"
                  : "Nouveau connecteur Perfect"}
              </div>
              <div className="form-section-desc">
                Prérempli avec les endpoints gateway-perfect. Renseignez l’URL
                serveur et les identifiants API pour le mode CBS. À la première
                connexion réelle, les crédits déjà ouverts dans le CBS sont
                importés et classés en recouvrement.
              </div>
            </div>
          </div>

          <div className="form-section-head" style={{ marginTop: 8 }}>
            <div className="form-section-icon">
              <Settings2 size={18} />
            </div>
            <div className="form-section-heading">
              <div className="form-section-title">Connexion</div>
            </div>
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Nom *</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>Protocole</span>
              <select
                value={form.protocol}
                onChange={(e) =>
                  setForm({ ...form, protocol: e.target.value })
                }
              >
                <option value="REST">REST (Perfect)</option>
                <option value="SOAP">SOAP</option>
                <option value="SFTP">SFTP</option>
                <option value="BATCH">BATCH</option>
              </select>
            </label>
            <label className="field full-span">
              <span>URL de base Perfect</span>
              <input
                value={form.base_url}
                onChange={(e) =>
                  setForm({ ...form, base_url: e.target.value })
                }
                placeholder="https://serveur-api"
              />
            </label>
            <label className="field">
              <span>Vérifier le certificat SSL</span>
              <select
                value={form.verify_ssl ? "1" : "0"}
                onChange={(e) =>
                  setForm({ ...form, verify_ssl: e.target.value === "1" })
                }
              >
                <option value="1">Oui (recommandé)</option>
                <option value="0">Non (staging / chaîne incomplète)</option>
              </select>
            </label>
            <label className="field">
              <span>Timeout (s)</span>
              <input
                type="number"
                min={1}
                value={form.timeout_seconds}
                onChange={(e) =>
                  setForm({
                    ...form,
                    timeout_seconds: Number(e.target.value) || 30,
                  })
                }
              />
            </label>
            <label className="field">
              <span>Tentatives max</span>
              <input
                type="number"
                min={0}
                value={form.max_retries}
                onChange={(e) =>
                  setForm({
                    ...form,
                    max_retries: Number(e.target.value) || 0,
                  })
                }
              />
            </label>
            <label className="field">
              <span>Actif</span>
              <select
                value={form.is_active ? "1" : "0"}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.value === "1" })
                }
              >
                <option value="1">Oui</option>
                <option value="0">Non</option>
              </select>
            </label>
            <label className="field">
              <span>Mode mise en place</span>
              <select
                value={form.disburse_mode}
                onChange={(e) =>
                  setForm({
                    ...form,
                    disburse_mode: e.target.value as "LOCAL" | "CBS",
                  })
                }
              >
                <option value="LOCAL">LOCAL — démo / hors CBS</option>
                <option value="CBS">CBS — POST Perfect crd/simple</option>
              </select>
            </label>
          </div>

          {form.disburse_mode === "LOCAL" && (
            <div className="form-error" style={{ marginTop: 10 }}>
              Mode LOCAL : aucun appel CBS. Mises en place et contrôles
              (soldes, situation) restent simulés — réservé à la démo / UAT
              tant que le CBS n’est pas disponible.
            </div>
          )}

          <div className="form-section-head" style={{ marginTop: 12 }}>
            <div className="form-section-icon">
              <KeyRound size={18} />
            </div>
            <div className="form-section-heading">
              <div className="form-section-title">Authentification Perfect</div>
              <div className="form-section-desc">
                POST form-urlencoded → accessToken (scope = perfect). En
                modification, laissez vide pour conserver les secrets
                existants.
              </div>
            </div>
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Utilisateur API</span>
              <input
                value={form.auth_username}
                onChange={(e) =>
                  setForm({ ...form, auth_username: e.target.value })
                }
                autoComplete="off"
                placeholder="username"
              />
            </label>
            <label className="field">
              <span>Mot de passe API</span>
              <input
                type="password"
                value={form.auth_password}
                onChange={(e) =>
                  setForm({ ...form, auth_password: e.target.value })
                }
                autoComplete="new-password"
              />
            </label>
            <label className="field">
              <span>Scope</span>
              <input
                value={form.auth_scope}
                onChange={(e) =>
                  setForm({ ...form, auth_scope: e.target.value })
                }
                placeholder="perfect"
              />
            </label>
            <label className="field">
              <span>Access token (optionnel)</span>
              <input
                type="password"
                value={form.auth_token}
                onChange={(e) =>
                  setForm({ ...form, auth_token: e.target.value })
                }
                placeholder="Sinon obtenu via /authentification"
                autoComplete="off"
              />
            </label>
          </div>

          <div className="form-section-head" style={{ marginTop: 12 }}>
            <div className="form-section-icon">
              <Radio size={18} />
            </div>
            <div className="form-section-heading">
              <div className="form-section-title">Endpoints gateway-perfect</div>
              <div className="form-section-desc">
                Chemins relatifs à l’URL de base (modifiables si besoin).
              </div>
            </div>
          </div>
          <div className="form-grid">
            <label className="field full-span">
              <span>Authentification</span>
              <input
                value={form.auth_path}
                onChange={(e) =>
                  setForm({ ...form, auth_path: e.target.value })
                }
              />
            </label>
            <label className="field full-span">
              <span>Situation adhérent</span>
              <input
                value={form.adh_situation_path}
                onChange={(e) =>
                  setForm({ ...form, adh_situation_path: e.target.value })
                }
              />
            </label>
            <label className="field full-span">
              <span>Mise en place crédit (crd/simple)</span>
              <input
                value={form.crd_simple_path}
                onChange={(e) =>
                  setForm({ ...form, crd_simple_path: e.target.value })
                }
              />
            </label>
            <label className="field full-span">
              <span>Situation crédit (crd/situation)</span>
              <input
                value={form.crd_situation_path}
                onChange={(e) =>
                  setForm({ ...form, crd_situation_path: e.target.value })
                }
              />
            </label>
            <label className="field full-span">
              <span>Liste des crédits / impayés (crd/impayes)</span>
              <input
                value={form.crd_impayes_path}
                onChange={(e) =>
                  setForm({ ...form, crd_impayes_path: e.target.value })
                }
              />
              <span className="muted small">
                S’il n’existe pas côté CBS, importez un Excel (un n° de dossier
                par ligne) : FinFlow appellera ensuite crd/situation pour
                chaque numéro.
              </span>
            </label>
          </div>

          <div className="form-section-head" style={{ marginTop: 12 }}>
            <div className="form-section-heading">
              <div className="form-section-title">
                Défauts mise en place Perfect
              </div>
              <div className="form-section-desc">
                Utilisés si agence / utilisateur / produit n’ont pas de code
                CBS.
              </div>
            </div>
          </div>
          <div className="form-grid">
            <label className="field">
              <span>idPointService</span>
              <input
                value={form.id_point_service}
                onChange={(e) =>
                  setForm({ ...form, id_point_service: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>idGestionnaire</span>
              <input
                value={form.id_gestionnaire}
                onChange={(e) =>
                  setForm({ ...form, id_gestionnaire: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>idProduitRemb historique (simulation uniquement)</span>
              <input
                value={form.id_produit_remb}
                disabled={form.disburse_mode !== "LOCAL"}
                onChange={(e) =>
                  setForm({ ...form, id_produit_remb: e.target.value })
                }
              />
              <small>En mode CBS réel, sélectionnez un produit de remboursement confirmé dans le paramétrage du produit de crédit.</small>
            </label>
          </div>

          {form.disburse_mode === "LOCAL" && (
            <>
              <div className="form-section-head" style={{ marginTop: 12 }}>
                <div className="form-section-heading">
                  <div className="form-section-title">
                    Simulation (mode LOCAL)
                  </div>
                </div>
              </div>
              <div className="form-grid">
                <label className="field">
                  <span>Prêt soldé par défaut</span>
                  <select
                    value={form.sim_loan_settled ? "1" : "0"}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        sim_loan_settled: e.target.value === "1",
                      })
                    }
                  >
                    <option value="1">Oui (main levée possible)</option>
                    <option value="0">Non (blocage main levée)</option>
                  </select>
                </label>
                <label className="field">
                  <span>Encours client défaut</span>
                  <input
                    value={form.sim_client_outstanding}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        sim_client_outstanding: e.target.value,
                      })
                    }
                  />
                </label>
              </div>
            </>
          )}

          {error && <div className="form-error">{error}</div>}

          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" disabled={pending} type="submit">
              <Save size={16} />
              {editing ? "Enregistrer" : "Créer le connecteur Perfect"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={closeForm}
              disabled={pending}
            >
              Annuler
            </button>
          </div>
        </form>
      )}

      <input
        ref={dossierFileRef}
        type="file"
        accept=".xlsx,.csv,.txt"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file || !dossierTargetId) return;
          setTestMsg(null);
          importPortfolio.mutate({ id: dossierTargetId, file });
        }}
      />

      <QueryStatus
        isLoading={connectors.isLoading}
        isError={connectors.isError}
        isEmpty={!connectors.data?.results.length}
        emptyMessage="Aucun connecteur. Créez un connecteur Perfect pour la filiale."
        onRetry={() => connectors.refetch()}
      >
        <>
          {(connectors.data?.results ?? []).some((c) => connectorMode(c) === "LOCAL") && (
            <div className="form-error" style={{ marginBottom: 12 }}>
              Au moins un connecteur est en mode LOCAL (démo / hors CBS) :
              les mises en place ne partent pas vers le core banking.
            </div>
          )}
        <table className="table card">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Provider</th>
              <th>Mode</th>
              <th>URL</th>
              <th>Endpoints</th>
              <th>Actif</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(connectors.data?.results ?? []).map((c) => {
              const endpoints = asRecord(asRecord(c.mapping_rules).endpoints);
              const authPath = str(endpoints.authentification, "—");
              const crdPath = str(endpoints.crd_simple, "—");
              const mode = connectorMode(c);
              return (
                <tr
                  key={c.id}
                  className={canChange ? "row-clickable" : undefined}
                  onClick={canChange ? () => openEdit(c) : undefined}
                >
                  <td>
                    <strong>{c.name}</strong>
                    <div className="muted small">{c.protocol}</div>
                  </td>
                  <td>
                    <Badge
                      value={
                        connectorProvider(c) === "perfect" ? "ACTIVE" : "DRAFT"
                      }
                      label={connectorProvider(c)}
                    />
                  </td>
                  <td>
                    <Badge
                      value={mode === "CBS" ? "ACTIVE" : "PENDING"}
                      label={mode === "LOCAL" ? "LOCAL (démo)" : mode}
                    />
                  </td>
                  <td className="muted small" style={{ maxWidth: 220 }}>
                    {c.base_url || <em>URL à renseigner</em>}
                  </td>
                  <td className="muted small">
                    <div title={authPath}>{authPath}</div>
                    <div title={crdPath}>{crdPath}</div>
                  </td>
                  <td>
                    <Badge
                      value={c.is_active ? "ACTIVE" : "DRAFT"}
                      label={c.is_active ? "Oui" : "Non"}
                    />
                  </td>
                  <td>
                    <div
                      style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {canChange && <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => openEdit(c)}
                      >
                        Modifier
                      </button>}
                      {canChange && <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => toggleActive.mutate(c)}
                        disabled={toggleActive.isPending}
                      >
                        {c.is_active ? "Désactiver" : "Activer"}
                      </button>}
                      {canChange && <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => {
                          setTestMsg(null);
                          testPing.mutate(c.id);
                        }}
                        disabled={testPing.isPending}
                      >
                        Test PING
                      </button>}
                      {canImportCbs && (
                        <>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => {
                              setTestMsg(null);
                              importPortfolio.mutate({ id: c.id });
                            }}
                            disabled={importPortfolio.isPending}
                          >
                            Importer les crédits
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => {
                              setDossierTargetId(c.id);
                              dossierFileRef.current?.click();
                            }}
                            disabled={importPortfolio.isPending}
                          >
                            Fichier de dossiers
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </>
      </QueryStatus>

      {canViewLogs ? (<>
      <h3 style={{ marginTop: 28, marginBottom: 8 }}>Journaux d&apos;intégration</h3>
      <p className="muted small" style={{ marginBottom: 12 }}>
        Derniers échanges CBS (mises en place, callbacks, PING…).
      </p>
      {opsMetrics.data?.celery && (
        <div className="card" style={{ marginBottom: 16, padding: 12 }}>
          <strong>Ops Celery</strong>
          <span className="muted small" style={{ marginLeft: 8 }}>
            {opsMetrics.data.celery.ok ? "workers OK" : "workers KO"}
            {" · file="}
            {opsMetrics.data.celery.queues?.celery ?? "—"}
            {" · soft-delete GED="}
            {opsMetrics.data.documents_soft_deleted ?? 0}
          </span>
        </div>
      )}
      <QueryStatus
        isLoading={logs.isLoading}
        isError={logs.isError}
        isEmpty={!logs.data?.results.length}
        emptyMessage="Aucun journal pour cette filiale."
        onRetry={() => logs.refetch()}
      >
        <table className="table card">
          <thead>
            <tr>
              <th>Date</th>
              <th>Opération</th>
              <th>Sens</th>
              <th>Statut</th>
              <th>Réf. externe</th>
              <th>Erreur</th>
            </tr>
          </thead>
          <tbody>
            {(logs.data?.results ?? []).map((log) => (
              <tr key={log.id}>
                <td className="muted small">
                  {new Date(log.created_at).toLocaleString("fr-FR")}
                </td>
                <td>
                  <code>{log.operation}</code>
                </td>
                <td>{log.direction}</td>
                <td>
                  <Badge
                    value={
                      log.status === "SUCCESS"
                        ? "ACTIVE"
                        : log.status === "FAILED"
                          ? "REJECTED"
                          : "PENDING"
                    }
                    label={log.status}
                  />
                </td>
                <td className="muted small">
                  {log.external_reference || "—"}
                </td>
                <td className="muted small" style={{ maxWidth: 240 }}>
                  {log.error_message || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </QueryStatus>
      </>) : <p className="muted small">Votre rôle ne permet pas de consulter les journaux d&apos;intégration.</p>}
    </div>
  );
}
