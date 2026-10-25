import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Save, Timer, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { CollectionEscalationRule, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { isFinflowAdmin } from "@/auth/routePerms";
import { EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const STAGES = [
  { value: "AMICABLE", label: "Amiable" },
  { value: "PRECONTENTIOUS", label: "Précontentieux" },
  { value: "LITIGATION", label: "Contentieux" },
] as const;

type DraftRule = {
  id?: string;
  key: string;
  min_days_overdue: string;
  target_stage: (typeof STAGES)[number]["value"];
  label: string;
  is_active: boolean;
};

function toDraft(rows: CollectionEscalationRule[]): DraftRule[] {
  return rows.map((row) => ({
    id: row.id,
    key: row.id,
    min_days_overdue: String(row.min_days_overdue),
    target_stage: row.target_stage,
    label: row.label,
    is_active: row.is_active,
  }));
}

export function AdminCollectionEscalationRulesPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canAdmin = isFinflowAdmin(user);
  const canAdd = hasPerm(user, "collections.add_collectionescalationrule");
  const canChange = hasPerm(user, "collections.change_collectionescalationrule");
  const canDelete = hasPerm(user, "collections.delete_collectionescalationrule");
  const hasWritePermission = canAdd || canChange || canDelete;
  const [rows, setRows] = useState<DraftRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const query = useQuery({
    queryKey: ["collection-escalation-rules", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CollectionEscalationRule>>(
          "/collection-escalation-rules/",
          { params: { page_size: 50, ordering: "min_days_overdue" } },
        )
      ).data,
    enabled: canAdmin && !needsTenant,
  });

  useEffect(() => {
    if (query.data?.results) setRows(toDraft(query.data.results));
  }, [query.data]);

  const existingRows = query.data?.results ?? [];
  const existingById = new Map(existingRows.map((row) => [row.id, row]));
  const hasNewRows = rows.some((row) => !row.id);
  const hasDeletedRows = existingRows.some(
    (old) => !rows.some((row) => row.id === old.id),
  );
  const hasEditedRows = rows.some((row) => {
    if (!row.id) return false;
    const old = existingById.get(row.id);
    return Boolean(old && (
      Number(row.min_days_overdue) !== old.min_days_overdue ||
      row.target_stage !== old.target_stage ||
      row.label.trim() !== old.label ||
      row.is_active !== old.is_active
    ));
  });
  const canSave = canAdmin && (
    (hasNewRows && canAdd) ||
    (hasEditedRows && canChange) ||
    (hasDeletedRows && canDelete)
  ) && (!hasNewRows || canAdd) && (!hasEditedRows || canChange) && (!hasDeletedRows || canDelete);

  const save = useMutation({
    mutationFn: async () => {
      const existing = query.data?.results ?? [];
      const keepIds = new Set(rows.map((row) => row.id).filter(Boolean));
      for (const old of existing) {
        if (!keepIds.has(old.id)) {
          if (!canDelete) throw new Error("Droit de suppression requis.");
          await api.delete(`/collection-escalation-rules/${old.id}/`);
        }
      }
      const savedRows: CollectionEscalationRule[] = [];
      for (const row of rows) {
        const payload = {
          min_days_overdue: Number(row.min_days_overdue),
          target_stage: row.target_stage,
          label: row.label.trim(),
          is_active: row.is_active,
        };
        if (!row.id) {
          if (!canAdd) throw new Error("Droit de création requis.");
          const res = await api.post<CollectionEscalationRule>(
            "/collection-escalation-rules/", payload,
          );
          savedRows.push(res.data);
          continue;
        }
        const old = existingById.get(row.id);
        if (!old) throw new Error("Règle introuvable.");
        const changed =
          Number(row.min_days_overdue) !== old.min_days_overdue ||
          row.target_stage !== old.target_stage ||
          row.label.trim() !== old.label ||
          row.is_active !== old.is_active;
        if (changed) {
          if (!canChange) throw new Error("Droit de modification requis.");
          const res = await api.patch<CollectionEscalationRule>(
            `/collection-escalation-rules/${row.id}/`, payload,
          );
          savedRows.push(res.data);
        } else {
          savedRows.push(old);
        }
      }
      return savedRows;
    },
    onSuccess: (data) => {
      setSaved(true);
      setError(null);
      setRows(toDraft(data));
      qc.invalidateQueries({ queryKey: ["collection-escalation-rules"] });
      qc.invalidateQueries({ queryKey: ["collection-cases"] });
    },
    onError: (err: unknown) => {
      setSaved(false);
      setError(
        apiErrorMessage(
          err,
          "Enregistrement impossible. Vérifiez les seuils et vos droits.",
        ),
      );
    },
  });

  function updateRow(key: string, patch: Partial<DraftRule>) {
    setSaved(false);
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  function addRow() {
    setSaved(false);
    setRows((current) => {
      const last = current[current.length - 1];
      const nextMin = last ? Number(last.min_days_overdue) + 30 : 31;
      return [
        ...current,
        {
          key: `new-${crypto.randomUUID()}`,
          min_days_overdue: String(Number.isFinite(nextMin) ? nextMin : 31),
          target_stage: "PRECONTENTIOUS",
          label: "",
          is_active: true,
        },
      ];
    });
  }

  function removeRow(key: string) {
    setSaved(false);
    setRows((current) => current.filter((row) => row.key !== key));
  }

  if (!canAdmin) {
    return (
      <EmptyState message="Paramétrage réservé aux administrateurs filiale et groupe." />
    );
  }
  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Timer}
          title="Règles d'escalade"
          subtitle="Sélectionnez une filiale"
        />
        <p className="muted">
          Choisissez une filiale dans la barre supérieure pour paramétrer les
          délais de stade (précontentieux / contentieux).
        </p>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={Timer}
        title="Règles d'escalade"
        subtitle="Délais de passage en précontentieux et contentieux"
      />

      {query.isLoading ? (
        <Spinner />
      ) : query.isError ? (
        <ErrorState
          message="Impossible de charger les règles."
          onRetry={() => query.refetch()}
        />
      ) : (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (canSave) save.mutate();
          }}
        >
          <p className="muted" style={{ marginBottom: 16 }}>
            Dès que le retard atteint un seuil, le dossier passe au stade cible
            (jamais en descente). Les tranches gèrent l&apos;affectation ; ces
            règles pilotent le stade amiable / précontentieux / contentieux.
          </p>

          {error && (
            <div className="notice-error" role="alert" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}
          {saved && !error && (
            <div className="form-success" style={{ marginBottom: 16 }}>
              Règles enregistrées. Le prochain recalcul des retards les
              appliquera.
            </div>
          )}
          {!hasWritePermission && <p className="muted" role="status">Consultation seule : aucun droit de création, modification ou suppression n&apos;est attribué.</p>}

          <div className="card" style={{ padding: 0, overflow: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Seuil (j)</th>
                  <th>Stade cible</th>
                  <th>Libellé</th>
                  <th>Active</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <input
                        type="number"
                        disabled={row.id ? !canChange : !canAdd}
                        min={1}
                        value={row.min_days_overdue}
                        onChange={(e) =>
                          updateRow(row.key, {
                            min_days_overdue: e.target.value,
                          })
                        }
                        required
                      />
                    </td>
                    <td>
                      <select
                        value={row.target_stage}
                        disabled={row.id ? !canChange : !canAdd}
                        onChange={(e) =>
                          updateRow(row.key, {
                            target_stage: e.target
                              .value as DraftRule["target_stage"],
                          })
                        }
                      >
                        {STAGES.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        value={row.label}
                        disabled={row.id ? !canChange : !canAdd}
                        onChange={(e) =>
                          updateRow(row.key, { label: e.target.value })
                        }
                        placeholder="Précontentieux dès 31 j"
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.is_active}
                        disabled={row.id ? !canChange : !canAdd}
                        onChange={(e) =>
                          updateRow(row.key, { is_active: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      {(row.id ? canDelete : canAdd) && <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => removeRow(row.key)}
                        aria-label="Supprimer la règle"
                      >
                        <Trash2 size={14} />
                      </button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="credit-form-actions" style={{ marginTop: 16 }}>
            {canAdd && <button type="button" className="btn btn-ghost" onClick={addRow}>
              <Plus size={16} /> Ajouter une règle
            </button>}
            {hasWritePermission && <button
              type="submit"
              className="btn btn-primary"
              disabled={save.isPending || !canSave}
            >
              <Save size={16} />
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>}
          </div>
        </form>
      )}
    </div>
  );
}
