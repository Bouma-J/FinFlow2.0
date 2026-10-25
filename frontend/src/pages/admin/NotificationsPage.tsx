import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  Bell,
  Building2,
  CheckCircle2,
  CircleAlert,
  Mail,
  MessageSquare,
  Save,
  Send,
  Server,
  Settings2,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/api/client";
import type {
  NotificationLog,
  NotificationSettings,
  Paginated,
  Tenant,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm } from "@/auth/permissions";
import { isFinflowAdmin } from "@/auth/routePerms";
import { isSmsEnabled } from "@/auth/features";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  TenantScopeNotice,
  formatDate,
} from "@/components/ui";

const EMPTY: NotificationSettings = {
  id: "",
  enabled: true,
  notify_on_step: true,
  notify_on_completion: true,
  notify_on_rejection: true,
  notify_on_return: true,
  notify_collection_email: false,
  notify_collection_sms: false,
  notify_collection_transfer: true,
  notify_collection_dialogue: true,
  from_email: "",
  reply_to: "",
  cc_tenant_email: false,
  smtp_host: "",
  smtp_port: 587,
  smtp_use_tls: true,
  smtp_use_ssl: false,
  smtp_username: "",
  smtp_password: "",
  smtp_password_configured: false,
  smtp_configured: false,
  effective_from_email: "",
  updated_at: "",
};

type PrefKey =
  | "notify_on_step"
  | "notify_on_completion"
  | "notify_on_rejection"
  | "notify_on_return"
  | "notify_collection_email"
  | "notify_collection_sms"
  | "notify_collection_transfer"
  | "notify_collection_dialogue"
  | "cc_tenant_email";

const CIRCUIT_PREFS: {
  key: PrefKey;
  title: string;
  hint: string;
}[] = [
  {
    key: "notify_on_step",
    title: "Étape suivante",
    hint: "Alerte les utilisateurs du rôle habilité quand une tâche s’ouvre.",
  },
  {
    key: "notify_on_completion",
    title: "Dossier validé",
    hint: "Informe l’initiateur et les intervenants — rappel de générer les contrats.",
  },
  {
    key: "notify_on_rejection",
    title: "Rejet",
    hint: "Informe l’initiateur et les intervenants en cas de rejet.",
  },
  {
    key: "notify_on_return",
    title: "Renvoi pour correction",
    hint: "Informe l’initiateur quand le dossier revient en instruction.",
  },
];

const COLLECTION_PREFS: {
  key: PrefKey;
  title: string;
  hint: string;
  requiresSms?: boolean;
}[] = [
  {
    key: "notify_collection_transfer",
    title: "Transfert de tranche",
    hint: "Alerte les responsables de la tranche d’arrivée (recouvrement, juridique…).",
  },
  {
    key: "notify_collection_dialogue",
    title: "Commentaire / recommandation",
    hint: "Alerte l’agent affecté ou l’équipe de la tranche quand un message est déposé.",
  },
  {
    key: "notify_collection_email",
    title: "Relances e-mail",
    hint: "Envois automatiques liés aux actions de recouvrement dues.",
  },
  {
    key: "notify_collection_sms",
    title: "Relances SMS",
    hint: "Nécessite FEATURE_SMS=1 et un provider (désactivé par défaut).",
    requiresSms: true,
  },
  {
    key: "cc_tenant_email",
    title: "Copie filiale",
    hint: "Met l’e-mail de la filiale en CC sur les alertes.",
  },
];

function FormBlock({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="tenant-form-block">
      <header className="tenant-form-block-head">
        <span className="tenant-form-block-icon">{icon}</span>
        <div>
          <h3 className="tenant-form-block-title">{title}</h3>
          <p className="tenant-form-block-desc">{description}</p>
        </div>
      </header>
      <div className="tenant-form-block-body">{children}</div>
    </section>
  );
}

export function AdminNotificationsPage() {
  const { user, activeTenant, setActiveTenant } = useAuth();
  const qc = useQueryClient();
  const smsEnabled = isSmsEnabled(user);
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canManage = Boolean(
    isFinflowAdmin(user) ||
    user?.permissions.includes("notifications.change_tenantnotificationsettings") ||
    user?.permissions.includes("tenants.change_tenant"),
  );
  const canViewLogs = Boolean(
    canManage || hasAnyPerm(user, ["notifications.view_notificationlog"]),
  );
  const [form, setForm] = useState<NotificationSettings>(EMPTY);
  const [smtpPassword, setSmtpPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testTo, setTestTo] = useState(user?.email ?? "");
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [logFilter, setLogFilter] = useState<"ALL" | "SENT" | "FAILED" | "SKIPPED">(
    "ALL",
  );

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () => (await api.get<Paginated<Tenant>>("/tenants/")).data,
    enabled: Boolean(user?.is_group_level),
  });

  const activeTenantLabel = (() => {
    if (!user?.is_group_level) {
      return user?.tenant_branding?.name || "Filiale connectée";
    }
    const match = tenants.data?.results.find((t) => t.id === activeTenant);
    return match ? `${match.code} — ${match.name}` : null;
  })();

  const settings = useQuery({
    queryKey: ["notification-settings", activeTenant],
    queryFn: async () =>
      (await api.get<NotificationSettings>("/notification-settings/current/"))
        .data,
    enabled: !needsTenant,
  });

  const logs = useQuery({
    queryKey: ["notification-logs", activeTenant],
    queryFn: async () =>
      (await api.get<Paginated<NotificationLog>>("/notification-logs/", {
        params: { page_size: 50 },
      })).data,
    enabled: !needsTenant && canViewLogs,
  });

  useEffect(() => {
    if (settings.data) {
      setForm(settings.data);
      setSmtpPassword("");
      if (!testTo && (user?.email || settings.data.from_email)) {
        setTestTo(user?.email || settings.data.from_email);
      }
    }
  }, [settings.data, user?.email, testTo]);

  const filteredLogs = useMemo(() => {
    const rows = logs.data?.results ?? [];
    if (logFilter === "ALL") return rows;
    return rows.filter((l) => l.status === logFilter);
  }, [logs.data, logFilter]);

  const logStats = useMemo(() => {
    const rows = logs.data?.results ?? [];
    return {
      total: rows.length,
      sent: rows.filter((l) => l.status === "SENT").length,
      failed: rows.filter((l) => l.status === "FAILED").length,
      skipped: rows.filter((l) => l.status === "SKIPPED").length,
    };
  }, [logs.data]);

  const save = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        enabled: form.enabled,
        notify_on_step: form.notify_on_step,
        notify_on_completion: form.notify_on_completion,
        notify_on_rejection: form.notify_on_rejection,
        notify_on_return: form.notify_on_return,
        notify_collection_email: form.notify_collection_email,
        notify_collection_sms: smsEnabled ? form.notify_collection_sms : false,
        notify_collection_transfer: form.notify_collection_transfer,
        notify_collection_dialogue: form.notify_collection_dialogue,
        from_email: form.from_email,
        reply_to: form.reply_to,
        cc_tenant_email: form.cc_tenant_email,
        smtp_host: form.smtp_host,
        smtp_port: form.smtp_port,
        smtp_use_tls: form.smtp_use_tls,
        smtp_use_ssl: form.smtp_use_ssl,
        smtp_username: form.smtp_username,
      };
      if (smtpPassword.trim()) {
        payload.smtp_password = smtpPassword.trim();
      }
      return (
        await api.patch<NotificationSettings>(
          "/notification-settings/current/",
          payload,
        )
      ).data;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["notification-settings"] });
      setForm(data);
      setSmtpPassword("");
      setError(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const data =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: Record<string, unknown> } }).response
              ?.data
          : undefined;
      const parts: string[] = [];
      if (data) {
        for (const [key, val] of Object.entries(data)) {
          if (key === "detail") {
            parts.push(String(val));
            continue;
          }
          if (Array.isArray(val)) parts.push(`${key}: ${val.join(" ")}`);
          else if (typeof val === "string") parts.push(`${key}: ${val}`);
        }
      }
      setError(
        parts.length
          ? parts.join(" — ")
          : "Enregistrement impossible. Vérifiez les champs et vos droits.",
      );
    },
  });

  const testMail = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ detail: string; from_email?: string }>(
          "/notification-settings/current/test/",
          { to: testTo },
          { timeout: 45000 },
        )
      ).data,
    onSuccess: (data) => {
      setTestMsg(data.detail);
      setError(null);
      qc.invalidateQueries({ queryKey: ["notification-logs"] });
    },
    onError: (err: unknown) => {
      setTestMsg(null);
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as
          | { detail?: string; error?: string; hint?: string }
          | string
          | undefined;
        if (data && typeof data === "object") {
          const msg = [data.detail, data.error, data.hint]
            .filter(Boolean)
            .join(" — ");
          if (msg) {
            setError(msg);
            return;
          }
        }
        if (err.code === "ECONNABORTED") {
          setError(
            "Délai dépassé : le serveur SMTP ne répond pas. " +
              "Désactivez Avast/Norton Mail Shield, puis réessayez.",
          );
          return;
        }
        if (err.response?.status === 502 || err.response?.status === 504) {
          setError(
            "Passerelle saturée (timeout). Le SMTP est probablement bloqué " +
              "par l'antivirus ou le pare-feu Windows.",
          );
          return;
        }
        setError(
          err.message ||
            `Échec de l'e-mail de test (HTTP ${err.response?.status ?? "?"}).`,
        );
        return;
      }
      setError("Échec de l'e-mail de test.");
    },
  });

  function setPref(key: PrefKey, value: boolean) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Bell}
          title="Alertes e-mail"
          subtitle="Paramétrage SMTP et notifications par filiale"
        />
        <TenantScopeNotice />
        <div className="tenant-compose-form" style={{ marginTop: 16 }}>
          <div className="tenant-compose-head">
            <h2>
              <Building2 size={18} style={{ verticalAlign: -3, marginRight: 8 }} />
              Choisir la filiale
            </h2>
            <p>
              Les alertes et le SMTP sont propres à chaque filiale. Sélectionnez
              celle à paramétrer.
            </p>
          </div>
          <label className="field">
            <span>Filiale</span>
            <select
              value={activeTenant ?? ""}
              onChange={(e) => setActiveTenant(e.target.value || null)}
            >
              <option value="">— Sélectionner —</option>
              {tenants.data?.results.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.code} — {t.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={Bell}
        title="Alertes e-mail"
        subtitle={
          activeTenantLabel
            ? `SMTP et notifications — ${activeTenantLabel}`
            : "SMTP et notifications de circuit pour la filiale active"
        }
      />

      {settings.isLoading ? (
        <Spinner />
      ) : settings.isError ? (
        <ErrorState
          message="Impossible de charger les paramètres d'alertes."
          onRetry={() => settings.refetch()}
        />
      ) : !settings.data ? (
        <EmptyState message="Aucun paramètre d'alertes." />
      ) : (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="tenant-compose-head">
            <h2>Paramétrage messagerie</h2>
            <p>
              Compte d’envoi de la filiale, préférences d’alertes circuit /
              recouvrement, et contrôle d’envoi.
            </p>
          </div>

          {!canManage && (
            <p className="muted" role="status">
              Consultation seule : la modification des paramètres et le test d’envoi sont réservés aux gestionnaires.
            </p>
          )}

          <fieldset disabled={!canManage} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>

          <div
            className={`alerts-status-strip ${
              form.smtp_configured ? "is-ready" : "is-fallback"
            }`}
          >
            <div className="alerts-status-main">
              {form.smtp_configured ? (
                <CheckCircle2 size={18} />
              ) : (
                <CircleAlert size={18} />
              )}
              <div>
                <strong>
                  {form.smtp_configured
                    ? "SMTP filiale actif"
                    : "Repli sur la configuration globale"}
                </strong>
                <p className="muted small" style={{ margin: "2px 0 0" }}>
                  Expéditeur effectif :{" "}
                  <code>
                    {form.effective_from_email ||
                      "NOREPLY Nom filiale <adresse>"}
                  </code>
                </p>
              </div>
            </div>
            <label className="alerts-master-toggle">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) =>
                  setForm({ ...form, enabled: e.target.checked })
                }
              />
              <span>
                {form.enabled
                  ? "Notifications activées"
                  : "Notifications désactivées"}
              </span>
            </label>
          </div>

          <FormBlock
            icon={<Server size={16} />}
            title="Serveur SMTP"
            description="Compte utilisé pour les identifiants utilisateurs et les alertes de cette filiale. Vide = config globale serveur."
          >
            <div className="form-grid two-col">
              <label className="field">
                <span>Serveur SMTP</span>
                <input
                  value={form.smtp_host}
                  onChange={(e) =>
                    setForm({ ...form, smtp_host: e.target.value })
                  }
                  placeholder="smtp.gmail.com"
                />
              </label>
              <label className="field">
                <span>Port</span>
                <input
                  type="number"
                  value={form.smtp_port}
                  onChange={(e) => {
                    const port = Number(e.target.value) || 587;
                    setForm({
                      ...form,
                      smtp_port: port,
                      smtp_use_tls: port !== 465,
                      smtp_use_ssl: port === 465,
                    });
                  }}
                />
              </label>
              <label className="field">
                <span>Identifiant SMTP</span>
                <input
                  value={form.smtp_username}
                  onChange={(e) =>
                    setForm({ ...form, smtp_username: e.target.value })
                  }
                  placeholder="noreply@filiale.com"
                  autoComplete="off"
                />
              </label>
              <label className="field">
                <span>
                  Mot de passe SMTP
                  {form.smtp_password_configured
                    ? " (vide = conserver)"
                    : ""}
                </span>
                <input
                  type="password"
                  value={smtpPassword}
                  onChange={(e) => setSmtpPassword(e.target.value)}
                  placeholder={
                    form.smtp_password_configured
                      ? "•••••••• (déjà enregistré)"
                      : "App Password / mot de passe"
                  }
                  autoComplete="new-password"
                />
              </label>
              <label className="field">
                <span>Adresse expéditeur (optionnel)</span>
                <input
                  value={form.from_email}
                  onChange={(e) =>
                    setForm({ ...form, from_email: e.target.value })
                  }
                  placeholder="laisser vide = identifiant SMTP"
                />
              </label>
              <label className="field">
                <span>Répondre à (optionnel)</span>
                <input
                  type="email"
                  value={form.reply_to}
                  onChange={(e) =>
                    setForm({ ...form, reply_to: e.target.value })
                  }
                />
              </label>
            </div>
            <div className="alerts-security-row">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.smtp_use_tls}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      smtp_use_tls: e.target.checked,
                      smtp_use_ssl: false,
                      smtp_port: e.target.checked ? 587 : form.smtp_port,
                    })
                  }
                />
                <span>TLS / STARTTLS (port 587)</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.smtp_use_ssl}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      smtp_use_ssl: e.target.checked,
                      smtp_use_tls: false,
                      smtp_port: e.target.checked ? 465 : form.smtp_port,
                    })
                  }
                />
                <span>SSL (port 465)</span>
              </label>
            </div>
          </FormBlock>

          <FormBlock
            icon={<Settings2 size={16} />}
            title="Alertes de circuit"
            description="Qui est notifié pendant et à la fin du circuit d’approbation."
          >
            <div className="alerts-pref-grid">
              {CIRCUIT_PREFS.map((p) => (
                <label
                  key={p.key}
                  className={`alerts-pref ${!form.enabled ? "is-disabled" : ""}`}
                >
                  <input
                    type="checkbox"
                    checked={form[p.key]}
                    disabled={!form.enabled}
                    onChange={(e) => setPref(p.key, e.target.checked)}
                  />
                  <span>
                    <strong>{p.title}</strong>
                    <em>{p.hint}</em>
                  </span>
                </label>
              ))}
            </div>
          </FormBlock>

          <FormBlock
            icon={<MessageSquare size={16} />}
            title="Recouvrement & copies"
            description="Relances après-vente et options transverses."
          >
            <div className="alerts-pref-grid">
              {COLLECTION_PREFS.map((p) => {
                const smsLocked = Boolean(p.requiresSms && !smsEnabled);
                const disabled = !form.enabled || smsLocked;
                return (
                  <label
                    key={p.key}
                    className={`alerts-pref ${disabled ? "is-disabled" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={smsLocked ? false : form[p.key]}
                      disabled={disabled}
                      onChange={(e) => setPref(p.key, e.target.checked)}
                    />
                    <span>
                      <strong>{p.title}</strong>
                      <em>
                        {smsLocked
                          ? "Canal SMS désactivé sur le serveur (FEATURE_SMS=0)."
                          : p.hint}
                      </em>
                    </span>
                  </label>
                );
              })}
            </div>
          </FormBlock>

          <FormBlock
            icon={<Send size={16} />}
            title="Tester l’envoi"
            description="Vérifie immédiatement la connexion SMTP avec un message de contrôle."
          >
            <div className="alerts-test-row">
              <label className="field" style={{ flex: 1, minWidth: 220 }}>
                <span>Destinataire</span>
                <input
                  type="email"
                  value={testTo}
                  onChange={(e) => setTestTo(e.target.value)}
                  placeholder="vous@exemple.com"
                />
              </label>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={testMail.isPending || !testTo.trim()}
                onClick={() => {
                  setError(null);
                  setTestMsg(null);
                  testMail.mutate();
                }}
              >
                <Mail size={15} />
                {testMail.isPending ? "Envoi…" : "Envoyer un test"}
              </button>
            </div>
            {testMsg && <div className="form-success">{testMsg}</div>}
          </FormBlock>

          {error && <div className="form-error">{error}</div>}
          {saved && (
            <p className="muted small" style={{ color: "var(--brand)" }}>
              Paramètres enregistrés.
            </p>
          )}

          <div className="tenant-compose-actions">
            <button
              className="btn btn-primary"
              disabled={save.isPending}
              type="submit"
            >
              <Save size={16} />
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
          </fieldset>
        </form>
      )}

      <section className="tenant-form-block" style={{ marginTop: 8 }}>
        <header className="tenant-form-block-head">
          <span className="tenant-form-block-icon">
            <Bell size={16} />
          </span>
          <div>
            <h3 className="tenant-form-block-title">Journal des envois</h3>
            <p className="tenant-form-block-desc">
              Derniers e-mails journalisés pour cette filiale.
            </p>
          </div>
        </header>
        <div className="tenant-form-block-body">
          <div className="alerts-log-toolbar">
            <div className="mini-kpis alerts-log-kpis">
              <button
                type="button"
                className={`mini-kpi ${logFilter === "ALL" ? "is-active" : ""}`}
                onClick={() => setLogFilter("ALL")}
              >
                <span className="mk-value">{logStats.total}</span>
                <span className="mk-label">Tous</span>
              </button>
              <button
                type="button"
                className={`mini-kpi ${logFilter === "SENT" ? "is-active" : ""}`}
                onClick={() => setLogFilter("SENT")}
              >
                <span className="mk-value">{logStats.sent}</span>
                <span className="mk-label">Envoyés</span>
              </button>
              <button
                type="button"
                className={`mini-kpi ${logFilter === "FAILED" ? "is-active" : ""}`}
                onClick={() => setLogFilter("FAILED")}
              >
                <span className="mk-value">{logStats.failed}</span>
                <span className="mk-label">Échecs</span>
              </button>
              <button
                type="button"
                className={`mini-kpi ${logFilter === "SKIPPED" ? "is-active" : ""}`}
                onClick={() => setLogFilter("SKIPPED")}
              >
                <span className="mk-value">{logStats.skipped}</span>
                <span className="mk-label">Ignorés</span>
              </button>
            </div>
          </div>

          {!canViewLogs ? (
            <EmptyState message="Votre rôle ne permet pas de consulter le journal des envois." />
          ) : logs.isLoading ? (
            <Spinner />
          ) : logs.isError ? (
            <ErrorState
              message="Impossible de charger le journal."
              onRetry={() => logs.refetch()}
            />
          ) : filteredLogs.length === 0 ? (
            <EmptyState message="Aucun e-mail journalisé pour ce filtre." />
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Sujet</th>
                  <th>Destinataires</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((l) => (
                  <tr key={l.id}>
                    <td className="muted small">{formatDate(l.created_at)}</td>
                    <td>{l.kind_display || l.kind}</td>
                    <td>{l.subject}</td>
                    <td className="muted small">
                      {(l.recipients || []).join(", ") || "—"}
                    </td>
                    <td>
                      <Badge
                        value={l.status}
                        label={l.status_display || l.status}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
