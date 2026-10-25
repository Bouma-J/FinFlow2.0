import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Plus, Save, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { Agency, CbsCatalogItem, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  Card,
  PageHeader,
  QueryStatus,
  TenantScopeNotice,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const EMPTY = {
  code: "",
  name: "",
  region: "",
  address: "",
  is_active: true,
  manager_last_name: "",
  manager_first_name: "",
  manager_phone: "",
  cbs_point_of_service_id: "",
};

export function AdminAgenciesPage() {
  const qc = useQueryClient();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canCreateAgency = hasPerm(user, "tenants.add_agency");
  const canChangeAgency = hasPerm(user, "tenants.change_agency");

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [editing, setEditing] = useState<Agency | null>(null);
  const [error, setError] = useState<string | null>(null);

  const agencies = useQuery({
    queryKey: ["agencies", activeTenant, user?.tenant],
    queryFn: async () =>
      (await api.get<Paginated<Agency>>("/agencies/", { params: { page_size: 200 } }))
        .data,
    enabled: !needsTenant,
  });

  const servicePoints = useQuery({
    queryKey: ["service-points", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/service-points/", {
          params: { page_size: 200, is_active: true },
        })
      ).data,
    enabled: !needsTenant,
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["agencies"] });

  const createMutation = useMutation({
    mutationFn: async (payload: typeof form) =>
      (await api.post("/agencies/", payload)).data,
    onSuccess: () => {
      invalidate();
      setShowForm(false);
      setForm({ ...EMPTY });
      setError(null);
    },
    onError: (err) =>
      setError(
        apiErrorMessage(
          err,
          "Création impossible. Vérifiez le code (unique par filiale).",
        ),
      ),
  });

  const patchMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<typeof form> }) =>
      (await api.patch(`/agencies/${id}/`, data)).data,
    onSuccess: () => {
      invalidate();
      setEditing(null);
      setError(null);
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Mise à jour impossible.")),
  });

  function submitCreate(e: FormEvent) {
    e.preventDefault();
    createMutation.mutate(form);
  }

  function submitEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    patchMutation.mutate({ id: editing.id, data: form });
  }

  function startEdit(agency: Agency) {
    setEditing(agency);
    setShowForm(false);
    setForm({
      code: agency.code,
      name: agency.name,
      region: agency.region,
      address: agency.address,
      is_active: agency.is_active,
      manager_last_name: agency.manager_last_name || "",
      manager_first_name: agency.manager_first_name || "",
      manager_phone: agency.manager_phone || "",
      cbs_point_of_service_id: agency.cbs_point_of_service_id || "",
    });
  }

  if (needsTenant) {
    return (
    <div className="page-shell">
        <PageHeader
          icon={MapPin}
          title="Agences"
          subtitle="Gestion des agences par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={MapPin}
        title="Agences"
        subtitle="Création et paramétrage des agences de la filiale"
        actions={canCreateAgency ? (
          <button
            className="btn btn-primary"
            onClick={() => {
              setShowForm((s) => !s);
              setEditing(null);
              setForm({ ...EMPTY });
            }}
          >
            {showForm ? <X /> : <Plus />}
            {showForm ? "Fermer" : "Nouvelle agence"}
          </button>
        ) : undefined}
      />

      {showForm && (
        <form className="inline-form" onSubmit={submitCreate}>
          <div className="form-grid">
            <label className="field">
              <span>Code *</span>
              <input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>Nom *</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>Région</span>
              <input
                value={form.region}
                onChange={(e) => setForm({ ...form, region: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Adresse</span>
              <input
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Nom du chef d&apos;agence</span>
              <input
                value={form.manager_last_name}
                onChange={(e) =>
                  setForm({ ...form, manager_last_name: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Prénom du chef d&apos;agence</span>
              <input
                value={form.manager_first_name}
                onChange={(e) =>
                  setForm({ ...form, manager_first_name: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Téléphone du chef d&apos;agence</span>
              <input
                value={form.manager_phone}
                onChange={(e) =>
                  setForm({ ...form, manager_phone: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Point de service CBS</span>
              <select
                value={form.cbs_point_of_service_id}
                onChange={(e) =>
                  setForm({ ...form, cbs_point_of_service_id: e.target.value })
                }
              >
                <option value="">— Aucun —</option>
                {(servicePoints.data?.results ?? []).map((sp) => (
                  <option key={sp.id} value={sp.cbs_code}>
                    {sp.code} — {sp.label} ({sp.cbs_code})
                  </option>
                ))}
              </select>
              {!servicePoints.data?.results?.length && (
                <span className="field-hint">
                  Importez les référentiels CBS pour peupler la liste.
                </span>
              )}
            </label>
          </div>
          {error && <div className="form-error">{error}</div>}
          <button className="btn btn-primary" disabled={createMutation.isPending || !canCreateAgency}>
            Créer l&apos;agence
          </button>
        </form>
      )}

      {editing && (
        <Card title={`Modifier ${editing.code}`}>
          <form className="stack" onSubmit={submitEdit}>
            <div className="form-grid">
              <label className="field">
                <span>Code</span>
                <input value={form.code} readOnly />
              </label>
              <label className="field">
                <span>Nom *</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Région</span>
                <input
                  value={form.region}
                  onChange={(e) => setForm({ ...form, region: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Adresse</span>
                <input
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Nom du chef d&apos;agence</span>
                <input
                  value={form.manager_last_name}
                  onChange={(e) =>
                    setForm({ ...form, manager_last_name: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Prénom du chef d&apos;agence</span>
                <input
                  value={form.manager_first_name}
                  onChange={(e) =>
                    setForm({ ...form, manager_first_name: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Téléphone du chef d&apos;agence</span>
                <input
                  value={form.manager_phone}
                  onChange={(e) =>
                    setForm({ ...form, manager_phone: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Point de service CBS</span>
                <select
                  value={form.cbs_point_of_service_id}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      cbs_point_of_service_id: e.target.value,
                    })
                  }
                >
                  <option value="">— Aucun —</option>
                  {(servicePoints.data?.results ?? []).map((sp) => (
                    <option key={sp.id} value={sp.cbs_code}>
                      {sp.code} — {sp.label} ({sp.cbs_code})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field checkbox">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) =>
                    setForm({ ...form, is_active: e.target.checked })
                  }
                />
                <span>Agence active</span>
              </label>
            </div>
            <div className="row-actions">
              <button className="btn btn-primary btn-sm" disabled={patchMutation.isPending || !canChangeAgency}>
                <Save /> Enregistrer
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setEditing(null)}
              >
                Annuler
              </button>
            </div>
          </form>
        </Card>
      )}

      <QueryStatus
        isLoading={agencies.isLoading}
        isError={agencies.isError}
        isEmpty={!agencies.data?.results.length}
        emptyMessage="Aucune agence pour cette filiale."
        onRetry={() => agencies.refetch()}
      >
        <table className="table card">
          <thead>
            <tr>
              <th>Code</th>
              <th>Nom</th>
              <th>Région</th>
              <th>Chef d&apos;agence</th>
              <th>Statut</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(agencies.data?.results ?? []).map((a) => (
              <tr
                key={a.id}
                className={canChangeAgency ? "row-clickable" : undefined}
                onClick={canChangeAgency ? () => startEdit(a) : undefined}
              >
                <td>{a.code}</td>
                <td>{a.name}</td>
                <td>{a.region || "—"}</td>
                <td>
                  {a.manager_display_name ||
                    `${a.manager_first_name || ""} ${a.manager_last_name || ""}`.trim() ||
                    "—"}
                  {a.manager_phone ? (
                    <span className="muted small"> · {a.manager_phone}</span>
                  ) : null}
                </td>
                <td>
                  <span className={`badge badge-${a.is_active ? "success" : "muted"}`}>
                    {a.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td>
                  {canChangeAgency && (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        startEdit(a);
                      }}
                    >
                      Modifier
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </QueryStatus>
    </div>
  );
}
