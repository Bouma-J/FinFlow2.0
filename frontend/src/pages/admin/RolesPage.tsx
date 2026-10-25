import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/api/client";
import type { BusinessCapability, Paginated, Permission, Role, RoleOption } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { isFinflowAdmin } from "@/auth/routePerms";
import { Card, ErrorState, PageHeader, QueryStatus, Spinner, TenantScopeNotice } from "@/components/ui";

export function AdminRolesPage() {
  const qc = useQueryClient();
  const { user, activeTenant, refreshUser } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canCreate = Boolean(isFinflowAdmin(user) && user?.permissions.includes("accounts.add_tenantrole"));
  const canChange = Boolean(isFinflowAdmin(user) && user?.permissions.includes("accounts.change_tenantrole"));

  const [newRole, setNewRole] = useState("");
  const [selected, setSelected] = useState<RoleOption | null>(null);
  const [draftPerms, setDraftPerms] = useState<number[]>([]);
  const [filter, setFilter] = useState("");
  const [draftCapabilities, setDraftCapabilities] = useState<string[]>([]);
  const [draftName, setDraftName] = useState("");

  useEffect(() => {
    setSelected(null);
    setDraftPerms([]);
    setDraftCapabilities([]);
  }, [activeTenant, user?.tenant]);

  const roles = useQuery({
    queryKey: ["admin-roles", activeTenant, user?.tenant],
    queryFn: async () => (await api.get<Paginated<RoleOption>>("/roles/options/")).data,
    enabled: !needsTenant,
  });
  const selectedRole = useQuery({
    queryKey: ["admin-role-detail", activeTenant, user?.tenant, selected?.id],
    queryFn: async () => (await api.get<Role>(`/roles/${selected!.id}/`)).data,
    enabled: Boolean(selected) && !needsTenant,
  });
  const perms = useQuery({
    queryKey: ["permissions", activeTenant, user?.tenant],
    queryFn: async () => (await api.get<Permission[]>("/permissions/")).data,
    enabled: Boolean(selectedRole.data),
  });
  const capabilities = useQuery({
    queryKey: ["business-capabilities", activeTenant, user?.tenant],
    queryFn: async () => (await api.get<BusinessCapability[]>("/roles/capabilities/")).data,
    enabled: Boolean(selected),
  });

  useEffect(() => {
    if (!selectedRole.data || selectedRole.data.id !== selected?.id) return;
    setDraftPerms(selectedRole.data.permissions);
    setDraftCapabilities(selectedRole.data.capabilities ?? []);
    setDraftName(selectedRole.data.name);
  }, [selected?.id, selectedRole.data]);

  const grouped = useMemo(() => {
    const map = new Map<string, Permission[]>();
    (perms.data ?? [])
      .filter(
        (p) =>
          !p.codename.startsWith("business_") && (
          !filter ||
          p.label.toLowerCase().includes(filter.toLowerCase()) ||
          p.name.toLowerCase().includes(filter.toLowerCase())),
      )
      .forEach((p) => {
        const arr = map.get(p.app_label) ?? [];
        arr.push(p);
        map.set(p.app_label, arr);
      });
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [perms.data, filter]);

  const createRole = useMutation({
    mutationFn: async (name: string) =>
      (await api.post("/roles/", { name })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] });
      setNewRole("");
    },
  });

  const savePerms = useMutation({
    mutationFn: async ({ id, permissions, name, capabilities }: { id: number; permissions: number[]; name: string; capabilities: string[] }) =>
      (await api.patch(`/roles/${id}/`, { permissions, name, capabilities })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] });
      setSelected(null);
      void refreshUser();
    },
  });

  function openRole(role: RoleOption) {
    setSelected(role);
    setDraftPerms([]);
    setDraftCapabilities([]);
    setDraftName("");
    setFilter("");
  }

  function toggle(id: number) {
    setDraftPerms((d) =>
      d.includes(id) ? d.filter((x) => x !== id) : [...d, id],
    );
  }

  if (needsTenant) {
    return (
    <div className="page-shell">
        <PageHeader
          icon={KeyRound}
          title="Rôles & droits"
          subtitle="Définition des rôles par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={KeyRound}
        title="Rôles & droits"
        subtitle="Rôles et permissions de la filiale active"
      />

      <form
        className="inline-form row"
        onSubmit={(e) => {
          e.preventDefault();
          if (canCreate && newRole.trim()) createRole.mutate(newRole.trim());
        }}
      >
        <input
          placeholder="Nom du nouveau rôle (ex. Directeur des risques)"
          value={newRole}
          disabled={!canCreate}
          onChange={(e) => setNewRole(e.target.value)}
        />
        <button className="btn btn-primary" disabled={createRole.isPending || !canCreate || !newRole.trim()}>
          <Plus />
          Créer le rôle
        </button>
      </form>
      {(createRole.isError || savePerms.isError) && <p className="alert alert-danger">{JSON.stringify((savePerms.error as { response?: { data?: unknown } })?.response?.data ?? (createRole.error as { response?: { data?: unknown } })?.response?.data ?? "L'enregistrement a échoué.")}</p>}

      <div className="detail-grid stacked">
        <Card title="Rôles de la filiale">
          <QueryStatus
            isLoading={roles.isLoading}
            isError={roles.isError}
            isEmpty={!roles.data?.results.length}
            emptyMessage="Aucun rôle pour cette filiale."
            errorMessage="Impossible de charger les rôles de cette filiale."
            onRetry={() => roles.refetch()}
          >
            <table className="table">
              <thead>
                <tr>
                  <th>Rôle</th>
                  <th className="num">Droits</th>
                  <th className="num">Utilisateurs</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(roles.data?.results ?? []).map((r) => (
                  <tr
                    key={r.id}
                    className="row-clickable"
                    onClick={() => openRole(r)}
                  >
                    <td>{r.name}</td>
                    <td className="num">{r.permission_count ?? 0}</td>
                    <td className="num">{r.user_count}</td>
                    <td>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          openRole(r);
                        }}
                      >
                        Droits
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </QueryStatus>
        </Card>

        <Card
          title={
            selected ? `Droits — ${selected.name}` : "Sélectionnez un rôle"
          }
        >
          {!selected ? (
            <p className="muted">
              Choisissez un rôle pour gérer ses permissions.
            </p>
          ) : selectedRole.isLoading ? (
            <Spinner />
          ) : selectedRole.isError ? (
            <ErrorState message="Impossible de charger ce rôle." onRetry={() => selectedRole.refetch()} />
          ) : !selectedRole.data ? (
            <p className="muted">Le rôle sélectionné est indisponible.</p>
          ) : perms.isLoading || capabilities.isLoading ? (
            <Spinner />
          ) : perms.isError ? (
            <ErrorState message="Impossible de charger le catalogue des permissions." onRetry={() => perms.refetch()} />
          ) : capabilities.isError ? (
            <ErrorState message="Impossible de charger les fonctions métier." onRetry={() => capabilities.refetch()} />
          ) : (
            <>
              <label className="field"><span>Nom du rôle</span><input value={draftName} maxLength={150} disabled={!canChange} onChange={(event) => setDraftName(event.target.value)} /></label>
              <p className="muted">Le nom est libre. Les fonctions métier ci-dessous déterminent le rôle dans les processus, en complément des permissions et du périmètre de données.</p>
              <div className="perm-group">
                <div className="perm-group-title">Fonctions métier</div>
                {capabilities.isError && <p className="muted">Chargement des fonctions impossible.</p>}
                {(capabilities.data ?? []).map((capability) => <label key={capability.code} className="checkbox"><input type="checkbox" disabled={!canChange} checked={draftCapabilities.includes(capability.code)} onChange={() => setDraftCapabilities((current) => current.includes(capability.code) ? current.filter((code) => code !== capability.code) : [...current, capability.code])} /><span>{capability.label}</span></label>)}
              </div>
              <input
                className="perm-filter"
                placeholder="Filtrer les permissions…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <div className="perm-scroll">
                {grouped.map(([app, list]) => (
                  <div key={app} className="perm-group">
                    <div className="perm-group-title">{app}</div>
                    {list.map((p) => (
                      <label key={p.id} className="checkbox">
                        <input
                          type="checkbox"
                          checked={draftPerms.includes(p.id)}
                          disabled={!canChange}
                          onChange={() => toggle(p.id)}
                        />
                        <span>{p.name}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
              <div className="row-actions" style={{ marginTop: 12 }}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() =>
                    savePerms.mutate({
                      id: selected.id,
                      permissions: draftPerms,
                      capabilities: draftCapabilities,
                      name: draftName.trim(),
                    })
                  }
                  disabled={savePerms.isPending || !canChange || !draftName.trim() || !capabilities.data}
                >
                  Enregistrer ({draftPerms.length})
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelected(null)}
                >
                  Fermer
                </button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
