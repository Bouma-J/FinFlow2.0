import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Shield, UsersRound, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { AdminUser, Agency, CbsCatalogItem, DataScope, Paginated, RoleOption, Tenant } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { Card, PageHeader, PaginationBar, QueryStatus, TenantScopeNotice } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const DATA_SCOPE_OPTIONS: { value: DataScope; label: string }[] = [
  { value: "OWN", label: "Ses propres dossiers uniquement" },
  { value: "AGENCY", label: "Tous les dossiers de son/ses agence(s)" },
  { value: "TENANT", label: "Toute la filiale" },
];

type PasswordDelivery = "email" | "manual";

const EMPTY = {
  username: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  employee_id: "",
  cbs_id: "",
  tenant: "",
  agency: "",
  agency_ids: [] as string[],
  data_scope: "AGENCY" as DataScope,
  is_group_level: false,
  is_active: true,
  group_ids: [] as number[],
  as_filiale_admin: false,
  password_delivery: "email" as PasswordDelivery,
  password: "",
  password_confirm: "",
};

export function AdminUsersPage() {
  const qc = useQueryClient();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canProvisionFilialeAdmin = Boolean(user?.is_group_level && activeTenant);
  const canCreateUser = hasPerm(user, "accounts.add_user");
  const canChangeUser = hasPerm(user, "accounts.change_user");
  const canOpenCreateForm = canCreateUser || canProvisionFilialeAdmin;

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetDelivery, setResetDelivery] = useState<PasswordDelivery>("email");
  const [resetPassword, setResetPassword] = useState("");
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () =>
      (await api.get<Paginated<Tenant>>("/tenants/")).data,
    enabled: !!user?.is_group_level,
  });

  const users = useQuery({
    queryKey: ["admin-users", activeTenant, user?.tenant, page],
    queryFn: async () =>
      (await api.get<Paginated<AdminUser>>("/users/", { params: { page } })).data,
    enabled: !needsTenant,
  });

  const roles = useQuery({
    queryKey: ["admin-roles", activeTenant, user?.tenant],
    queryFn: async () => (await api.get<Paginated<RoleOption>>("/roles/options/")).data,
    enabled: !needsTenant,
  });

  const agencies = useQuery({
    queryKey: ["agencies", activeTenant, user?.tenant],
    queryFn: async () =>
      (await api.get<Paginated<Agency>>("/agencies/", { params: { page_size: 200 } }))
        .data,
    enabled: !needsTenant,
  });

  const cbsManagers = useQuery({
    queryKey: ["cbs-managers", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/cbs-managers/", {
          params: { page_size: 200, is_active: true },
        })
      ).data,
    enabled: !needsTenant,
  });

  useEffect(() => {
    if (user?.is_group_level && activeTenant) {
      setForm((f) => ({ ...f, tenant: activeTenant, is_group_level: false }));
    } else if (user?.tenant) {
      setForm((f) => ({ ...f, tenant: user.tenant!, is_group_level: false }));
    }
  }, [user, activeTenant]);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["admin-users"] });

  const createMutation = useMutation({
    mutationFn: async (payload: typeof form) => {
      const passwordFields = {
        password_delivery: payload.password_delivery,
        ...(payload.password_delivery === "manual"
          ? {
              password: payload.password,
              password_confirm: payload.password_confirm,
            }
          : {}),
      };
      if (payload.as_filiale_admin && user?.is_group_level) {
        return (
          await api.post("/users/provision-filiale-admin/", {
            username: payload.username,
            first_name: payload.first_name,
            last_name: payload.last_name,
            email: payload.email,
            phone: payload.phone,
            employee_id: payload.employee_id,
            cbs_id: payload.cbs_id,
            tenant: payload.tenant || activeTenant,
            ...(payload.agency ? { agency: payload.agency } : {}),
            agency_ids: payload.agency_ids,
            ...passwordFields,
          })
        ).data;
      }
      const body = {
        username: payload.username,
        first_name: payload.first_name,
        last_name: payload.last_name,
        email: payload.email,
        phone: payload.phone,
        employee_id: payload.employee_id,
        cbs_id: payload.cbs_id,
        tenant: payload.is_group_level ? null : payload.tenant || null,
        agency: payload.is_group_level ? null : payload.agency || null,
        agency_ids:
          payload.agency_ids.length > 0
            ? payload.agency_ids
            : payload.agency
              ? [payload.agency]
              : [],
        data_scope: payload.data_scope,
        is_group_level: payload.is_group_level,
        is_active: payload.is_active,
        group_ids: payload.group_ids,
        as_filiale_admin: false,
        ...passwordFields,
      };
      return (await api.post("/users/", body)).data;
    },
    onSuccess: (data: { detail?: string; email_sent?: boolean }) => {
      invalidate();
      setShowForm(false);
      setForm({
        ...EMPTY,
        tenant: activeTenant ?? user?.tenant ?? "",
        data_scope: "AGENCY",
      });
      setError(null);
      setSuccess(
        data.detail ||
          (data.email_sent
            ? "Utilisateur créé. Mot de passe temporaire envoyé par e-mail."
            : "Utilisateur créé."),
      );
    },
    onError: (err: unknown) =>
      setError(
        apiErrorMessage(
          err,
          "Création impossible (identifiant, mot de passe, e-mail ou agence ?).",
        ),
      ),
  });

  const patchMutation = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Record<string, unknown>;
    }) => (await api.patch(`/users/${id}/`, data)).data,
    onSuccess: () => {
      invalidate();
      setEditing(null);
    },
  });

  const resetPwdMutation = useMutation({
    mutationFn: async ({
      id,
      password_delivery,
      password,
      password_confirm,
    }: {
      id: string;
      password_delivery: PasswordDelivery;
      password?: string;
      password_confirm?: string;
    }) =>
      (
        await api.post(`/users/${id}/reset-password/`, {
          password_delivery,
          ...(password_delivery === "manual"
            ? { password, password_confirm }
            : {}),
        })
      ).data as {
        detail: string;
        email_sent: boolean;
      },
    onSuccess: (data) => {
      invalidate();
      setResetTarget(null);
      setResetPassword("");
      setResetPasswordConfirm("");
      setResetError(null);
      setSuccess(data.detail);
    },
    onError: (err: unknown) =>
      setResetError(
        apiErrorMessage(
          err,
          "Régénération impossible (e-mail manquant, mot de passe trop faible ?).",
        ),
      ),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setSuccess(null);
    if (!canCreateUser && !(canProvisionFilialeAdmin && form.as_filiale_admin)) {
      setError("Vous n'avez pas le droit de créer cet utilisateur.");
      return;
    }
    if (form.password_delivery === "email" && !form.email.trim()) {
      setError("L'adresse e-mail est obligatoire pour l'envoi du mot de passe.");
      return;
    }
    if (form.password_delivery === "manual") {
      if (form.password.length < 10) {
        setError("Le mot de passe doit contenir au moins 10 caractères.");
        return;
      }
      if (form.password !== form.password_confirm) {
        setError("Les mots de passe ne correspondent pas.");
        return;
      }
    }
    if (!form.is_group_level && !form.as_filiale_admin && !form.agency) {
      setError("L'agence principale est obligatoire.");
      return;
    }
    createMutation.mutate(form);
  }

  function submitReset(e: FormEvent) {
    e.preventDefault();
    if (!resetTarget) return;
    setResetError(null);
    if (resetDelivery === "email" && !resetTarget.email?.trim()) {
      setResetError(
        "Cet utilisateur n'a pas d'e-mail. Choisissez la définition manuelle.",
      );
      return;
    }
    if (resetDelivery === "manual") {
      if (resetPassword.length < 10) {
        setResetError("Le mot de passe doit contenir au moins 10 caractères.");
        return;
      }
      if (resetPassword !== resetPasswordConfirm) {
        setResetError("Les mots de passe ne correspondent pas.");
        return;
      }
    }
    resetPwdMutation.mutate({
      id: resetTarget.id,
      password_delivery: resetDelivery,
      password: resetPassword,
      password_confirm: resetPasswordConfirm,
    });
  }

  function toggleRole(list: number[], id: number): number[] {
    return list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  }

  function toggleAgency(list: string[], id: string): string[] {
    return list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  }

  function setAsFilialeAdmin(checked: boolean) {
    const adminRole = roles.data?.results.find(
      (r) => r.name === "Administrateur filiale",
    );
    setForm((f) => ({
      ...f,
      as_filiale_admin: checked,
      is_group_level: false,
      data_scope: checked ? "TENANT" : f.data_scope,
      agency: checked ? "" : f.agency,
      agency_ids: checked ? [] : f.agency_ids,
      group_ids:
        checked && adminRole
          ? Array.from(new Set([...f.group_ids, adminRole.id]))
          : f.group_ids,
    }));
  }

  const tenantName = (id: string | null) =>
    tenants.data?.results.find((t) => t.id === id)?.code ?? (id ? "—" : "Groupe");

  const agencyName = (id: string | null) =>
    agencies.data?.results.find((a) => a.id === id)?.name ?? "—";

  const scopeLabel = (scope: DataScope) =>
    DATA_SCOPE_OPTIONS.find((o) => o.value === scope)?.label ?? scope;

  const scopeLabelPage = user?.is_group_level
    ? tenants.data?.results.find((t) => t.id === activeTenant)?.name ?? "filiale sélectionnée"
    : tenantName(user?.tenant ?? null);

  if (needsTenant) {
    return (
    <div className="page-shell">
        <PageHeader
          icon={UsersRound}
          title="Utilisateurs"
          subtitle="Création des comptes par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={UsersRound}
        title="Utilisateurs"
        subtitle={`Gestion des comptes — ${scopeLabelPage}`}
        actions={canOpenCreateForm ? (
          <button
            className="btn btn-primary"
            onClick={() => {
              setShowForm((s) => !s);
              setSuccess(null);
              setError(null);
            }}
          >
            {showForm ? <X /> : <Plus />}
            {showForm ? "Fermer" : "Nouvel utilisateur"}
          </button>
        ) : undefined}
      />

      {success && <div className="form-success" style={{ marginBottom: 12 }}>{success}</div>}

      {showForm && (
        <form className="inline-form" onSubmit={submit}>
          <fieldset className="password-delivery">
            <legend>Mot de passe initial</legend>
            <label className="radio">
              <input
                type="radio"
                name="password_delivery"
                checked={form.password_delivery === "email"}
                onChange={() =>
                  setForm({
                    ...form,
                    password_delivery: "email",
                    password: "",
                    password_confirm: "",
                  })
                }
              />
              <span>Générer et envoyer par e-mail</span>
            </label>
            <label className="radio">
              <input
                type="radio"
                name="password_delivery"
                checked={form.password_delivery === "manual"}
                onChange={() =>
                  setForm({ ...form, password_delivery: "manual" })
                }
              />
              <span>Définir manuellement (si le serveur mail est indisponible)</span>
            </label>
            <p className="muted small" style={{ marginTop: 8 }}>
              Dans les deux cas, l&apos;utilisateur devra changer ce mot de passe
              à la première connexion.
            </p>
          </fieldset>
          {canProvisionFilialeAdmin && (
            <label className="checkbox" style={{ marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={form.as_filiale_admin}
                onChange={(e) => setAsFilialeAdmin(e.target.checked)}
              />
              <span>
                <Shield size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
                Administrateur filiale — menus d&apos;administration{" "}
                <em>et</em> fonctionnalités métier (clients, dossiers de crédit,
                garanties, etc.), exclusivement sur la filiale sélectionnée
              </span>
            </label>
          )}

          <div className="form-grid">
            <label className="field">
              <span>Identifiant *</span>
              <input
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>
                E-mail
                {form.password_delivery === "email"
                  ? " * (réception du mot de passe)"
                  : " (optionnel)"}
              </span>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required={form.password_delivery === "email"}
              />
            </label>
            {form.password_delivery === "manual" && (
              <>
                <label className="field">
                  <span>Mot de passe * (min. 10 car.)</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={form.password}
                    onChange={(e) =>
                      setForm({ ...form, password: e.target.value })
                    }
                    required
                    minLength={10}
                  />
                </label>
                <label className="field">
                  <span>Confirmer le mot de passe *</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={form.password_confirm}
                    onChange={(e) =>
                      setForm({ ...form, password_confirm: e.target.value })
                    }
                    required
                    minLength={10}
                  />
                </label>
              </>
            )}
            <label className="field">
              <span>Prénom</span>
              <input
                value={form.first_name}
                onChange={(e) =>
                  setForm({ ...form, first_name: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Nom</span>
              <input
                value={form.last_name}
                onChange={(e) =>
                  setForm({ ...form, last_name: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Téléphone</span>
              <input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Matricule</span>
              <input
                value={form.employee_id}
                onChange={(e) =>
                  setForm({ ...form, employee_id: e.target.value })
                }
                placeholder="Optionnel"
              />
            </label>
            <label className="field">
              <span>Gestionnaire CBS</span>
              <select
                value={form.cbs_id}
                onChange={(e) => setForm({ ...form, cbs_id: e.target.value })}
              >
                <option value="">— Aucun —</option>
                {(cbsManagers.data?.results ?? []).map((m) => (
                  <option key={m.id} value={m.cbs_code}>
                    {m.code} — {m.label} ({m.cbs_code})
                  </option>
                ))}
              </select>
              {!cbsManagers.data?.results?.length && (
                <span className="field-hint">
                  Importez les référentiels CBS pour peupler la liste.
                </span>
              )}
            </label>
            {!form.is_group_level && !form.as_filiale_admin && (
              <>
                <label className="field">
                  <span>Agence principale *</span>
                  <select
                    value={form.agency}
                    onChange={(e) => {
                      const agency = e.target.value;
                      setForm((f) => ({
                        ...f,
                        agency,
                        agency_ids: f.agency_ids.includes(agency)
                          ? f.agency_ids
                          : agency
                            ? [...f.agency_ids, agency]
                            : f.agency_ids,
                      }));
                    }}
                    required
                  >
                    <option value="">— Choisir —</option>
                    {agencies.data?.results.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Périmètre de données</span>
                  <select
                    value={form.data_scope}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        data_scope: e.target.value as DataScope,
                      })
                    }
                  >
                    {DATA_SCOPE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {form.as_filiale_admin && (
              <label className="field">
                <span>Périmètre de données</span>
                <input value="Toute la filiale (toutes agences)" readOnly />
              </label>
            )}
            {user?.is_group_level && !activeTenant && (
              <>
                <label className="field">
                  <span>Filiale</span>
                  <select
                    value={form.tenant}
                    onChange={(e) => setForm({ ...form, tenant: e.target.value })}
                    disabled={form.is_group_level}
                  >
                    <option value="">— Groupe —</option>
                    {tenants.data?.results.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} — {t.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field checkbox">
                  <input
                    type="checkbox"
                    checked={form.is_group_level}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        is_group_level: e.target.checked,
                        as_filiale_admin: false,
                        tenant: e.target.checked ? "" : form.tenant,
                      })
                    }
                  />
                  <span>Utilisateur Groupe (transverse)</span>
                </label>
              </>
            )}
            {(activeTenant || user?.tenant) && (
              <label className="field">
                <span>Filiale</span>
                <input value={scopeLabelPage} readOnly />
              </label>
            )}
          </div>

          {!form.is_group_level && !form.as_filiale_admin && (
            <div className="checkbox-group">
              <span className="field-legend">
                Agences supplémentaires (accès multi-agences)
              </span>
              <div className="checkbox-list">
                {agencies.data?.results.length === 0 && (
                  <p className="muted small">Aucune agence pour cette filiale.</p>
                )}
                {agencies.data?.results.map((a) => (
                  <label key={a.id} className="checkbox">
                    <input
                      type="checkbox"
                      checked={form.agency_ids.includes(a.id)}
                      onChange={() =>
                        setForm({
                          ...form,
                          agency_ids: toggleAgency(form.agency_ids, a.id),
                        })
                      }
                    />
                    <span>
                      {a.code} — {a.name}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {!form.as_filiale_admin && (
            <div className="checkbox-group">
              <span className="field-legend">Rôles de la filiale</span>
              <div className="checkbox-list">
                {roles.data?.results.length === 0 && (
                  <p className="muted small">Aucun rôle pour cette filiale.</p>
                )}
                {roles.data?.results.map((r) => (
                  <label key={r.id} className="checkbox">
                    <input
                      type="checkbox"
                      checked={form.group_ids.includes(r.id)}
                      onChange={() =>
                        setForm({
                          ...form,
                          group_ids: toggleRole(form.group_ids, r.id),
                        })
                      }
                    />
                    <span>{r.name}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {form.as_filiale_admin && (
            <p className="muted small" style={{ marginTop: 8 }}>
              Le rôle <strong>Administrateur filiale</strong> sera attribué
              automatiquement (paramétrage + opérations métier). Périmètre :{" "}
              <strong>toute la filiale</strong> uniquement — aucune agence à
              sélectionner, aucune donnée des autres filiales.
            </p>
          )}

          {error && <div className="form-error">{error}</div>}
          <button
            className="btn btn-primary"
            disabled={
              createMutation.isPending ||
              (!canCreateUser && !(canProvisionFilialeAdmin && form.as_filiale_admin))
            }
          >
            {form.as_filiale_admin
              ? "Créer l'administrateur filiale"
              : "Créer l'utilisateur"}
          </button>
        </form>
      )}

      {editing && (
        <Card title={`Profil de ${editing.username}`}>
          <div className="form-grid">
            <label className="field">
              <span>E-mail</span>
              <input
                type="email"
                value={editing.email ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, email: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Matricule</span>
              <input
                value={editing.employee_id ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, employee_id: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Gestionnaire CBS</span>
              <select
                value={editing.cbs_id ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, cbs_id: e.target.value })
                }
              >
                <option value="">— Aucun —</option>
                {(cbsManagers.data?.results ?? []).map((m) => (
                  <option key={m.id} value={m.cbs_code}>
                    {m.code} — {m.label} ({m.cbs_code})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Agence principale</span>
              <select
                value={editing.agency ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, agency: e.target.value || null })
                }
              >
                <option value="">—</option>
                {agencies.data?.results.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.code} — {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Périmètre de données</span>
              <select
                value={editing.data_scope}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    data_scope: e.target.value as DataScope,
                  })
                }
              >
                {DATA_SCOPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            {user?.is_group_level && !editing.is_group_level && (
              <label className="field checkbox">
                <input
                  type="checkbox"
                  checked={Boolean(editing.is_staff)}
                  onChange={(e) =>
                    setEditing({ ...editing, is_staff: e.target.checked })
                  }
                />
                <span>Administrateur (accès menus Admin)</span>
              </label>
            )}
          </div>

          <div className="checkbox-group" style={{ marginTop: 12 }}>
            <span className="field-legend">Agences accessibles</span>
            <div className="checkbox-list">
              {agencies.data?.results.map((a) => {
                const checked = editing.agencies_detail.some((x) => x.id === a.id);
                return (
                  <label key={a.id} className="checkbox">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        const next = checked
                          ? editing.agencies_detail.filter((x) => x.id !== a.id)
                          : [...editing.agencies_detail, a];
                        setEditing({ ...editing, agencies_detail: next });
                      }}
                    />
                    <span>
                      {a.code} — {a.name}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="checkbox-group" style={{ marginTop: 12 }}>
            <span className="field-legend">Rôles</span>
            <div className="checkbox-list">
              {roles.data?.results.map((r) => {
                const checked = editing.groups.some((g) => g.id === r.id);
                return (
                  <label key={r.id} className="checkbox">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        const ids = editing.groups.map((g) => g.id);
                        const next = checked
                          ? ids.filter((x) => x !== r.id)
                          : [...ids, r.id];
                        setEditing({
                          ...editing,
                          groups: roles.data!.results.filter((x) =>
                            next.includes(x.id),
                          ),
                        });
                      }}
                    />
                    <span>{r.name}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="row-actions" style={{ marginTop: 12 }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={() =>
                patchMutation.mutate({
                  id: editing.id,
                  data: {
                    email: editing.email,
                    employee_id: editing.employee_id,
                    cbs_id: editing.cbs_id,
                    agency: editing.agency,
                    data_scope: editing.data_scope,
                    agency_ids: editing.agencies_detail.map((a) => a.id),
                    group_ids: editing.groups.map((g) => g.id),
                    ...(user?.is_group_level
                      ? { is_staff: editing.is_staff }
                      : {}),
                  },
                })
              }
            >
              Enregistrer
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setEditing(null)}
            >
              Annuler
            </button>
          </div>
        </Card>
      )}

      <QueryStatus
        isLoading={users.isLoading}
        isError={users.isError}
        isEmpty={!users.data?.results.length}
        emptyMessage="Aucun utilisateur pour cette filiale."
        onRetry={() => users.refetch()}
      >
        <>
        <table className="table card">
          <thead>
            <tr>
              <th>Identifiant</th>
              <th>E-mail</th>
              <th>Agence</th>
              <th>Périmètre</th>
              <th>Rôles</th>
              <th>Admin</th>
              <th>Actif</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(users.data?.results ?? []).map((u) => (
              <tr
                key={u.id}
                className={canChangeUser ? "row-clickable" : undefined}
                onClick={canChangeUser ? () => setEditing(u) : undefined}
              >
                <td>{u.username}</td>
                <td className="small">{u.email || <span className="muted">—</span>}</td>
                <td>
                  {u.is_group_level ? (
                    <span className="muted small">Groupe</span>
                  ) : (
                    agencyName(u.agency)
                  )}
                </td>
                <td className="small">
                  {u.is_group_level ? "Groupe" : scopeLabel(u.data_scope)}
                </td>
                <td>
                  {u.groups.length === 0 ? (
                    <span className="muted small">—</span>
                  ) : (
                    u.groups.map((g) => (
                      <span key={g.id} className="badge badge-info">
                        {g.name}
                      </span>
                    ))
                  )}
                </td>
                <td>
                  {u.is_staff ? (
                    <span className="badge badge-success">Oui</span>
                  ) : (
                    <span className="muted small">—</span>
                  )}
                </td>
                <td>
                  {canChangeUser ? (
                    <button
                      className={`badge badge-${u.is_active ? "success" : "muted"} badge-btn`}
                      onClick={(e) => {
                        e.stopPropagation();
                        patchMutation.mutate({
                          id: u.id,
                          data: { is_active: !u.is_active },
                        });
                      }}
                      title="Activer / désactiver"
                    >
                      {u.is_active ? "Actif" : "Inactif"}
                    </button>
                  ) : (
                    <span className={`badge badge-${u.is_active ? "success" : "muted"}`}>
                      {u.is_active ? "Actif" : "Inactif"}
                    </span>
                  )}
                </td>
                <td>
                  <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                    {canChangeUser && (
                      <>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setEditing(u)}
                        >
                          Modifier
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          title="Régénérer le mot de passe"
                          disabled={resetPwdMutation.isPending}
                          onClick={() => {
                            setError(null);
                            setSuccess(null);
                            setResetError(null);
                            setResetDelivery(u.email ? "email" : "manual");
                            setResetPassword("");
                            setResetPasswordConfirm("");
                            setResetTarget(u);
                          }}
                        >
                          <KeyRound size={14} /> Mot de passe
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <PaginationBar
          page={page}
          count={users.data?.count ?? 0}
          onPageChange={setPage}
        />
        </>
      </QueryStatus>

      {resetTarget && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => !resetPwdMutation.isPending && setResetTarget(null)}
        >
          <form
            className="modal-card"
            onClick={(e) => e.stopPropagation()}
            onSubmit={submitReset}
          >
            <h3>Mot de passe — {resetTarget.username}</h3>
            <fieldset className="password-delivery">
              <legend>Mode</legend>
              <label className="radio">
                <input
                  type="radio"
                  name="reset_delivery"
                  checked={resetDelivery === "email"}
                  disabled={!resetTarget.email}
                  onChange={() => setResetDelivery("email")}
                />
                <span>
                  Générer et envoyer par e-mail
                  {resetTarget.email
                    ? ` (${resetTarget.email})`
                    : " — aucun e-mail renseigné"}
                </span>
              </label>
              <label className="radio">
                <input
                  type="radio"
                  name="reset_delivery"
                  checked={resetDelivery === "manual"}
                  onChange={() => setResetDelivery("manual")}
                />
                <span>Définir manuellement</span>
              </label>
            </fieldset>
            {resetDelivery === "manual" && (
              <div className="form-grid" style={{ marginTop: 12 }}>
                <label className="field">
                  <span>Nouveau mot de passe * (min. 10 car.)</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={resetPassword}
                    onChange={(e) => setResetPassword(e.target.value)}
                    required
                    minLength={10}
                    autoFocus
                  />
                </label>
                <label className="field">
                  <span>Confirmation *</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={resetPasswordConfirm}
                    onChange={(e) => setResetPasswordConfirm(e.target.value)}
                    required
                    minLength={10}
                  />
                </label>
              </div>
            )}
            <p className="muted small" style={{ marginTop: 8 }}>
              L&apos;utilisateur devra changer ce mot de passe à la prochaine
              connexion.
            </p>
            {resetError && <div className="form-error">{resetError}</div>}
            <div className="row-actions" style={{ marginTop: 12 }}>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={resetPwdMutation.isPending}
              >
                {resetPwdMutation.isPending ? "En cours…" : "Appliquer"}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={resetPwdMutation.isPending}
                onClick={() => setResetTarget(null)}
              >
                Annuler
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
