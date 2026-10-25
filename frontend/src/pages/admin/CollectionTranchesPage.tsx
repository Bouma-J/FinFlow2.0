import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDollarSign, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type {
  CollectionTranche,
  CollectionTrancheOwner,
  Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { isFinflowAdmin } from "@/auth/routePerms";
import { EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const OWNER_OPTIONS: { value: CollectionTrancheOwner; label: string }[] = [
  { value: "GESTIONNAIRE", label: "Gestionnaire" },
  { value: "COLLECTION", label: "Service recouvrement" },
  { value: "LEGAL", label: "Juridique" },
];

type DraftTranche = {
  key: string;
  name: string;
  min_days_overdue: string;
  max_days_overdue: string;
  owner_kind: CollectionTrancheOwner;
};

function toDraft(rows: CollectionTranche[]): DraftTranche[] {
  return rows.map((row) => ({
    key: row.id,
    name: row.name,
    min_days_overdue: String(row.min_days_overdue),
    max_days_overdue:
      row.max_days_overdue == null ? "" : String(row.max_days_overdue),
    owner_kind: row.owner_kind,
  }));
}

function emptyRow(afterMin = 1): DraftTranche {
  return {
    key: `new-${crypto.randomUUID()}`,
    name: "",
    min_days_overdue: String(afterMin),
    max_days_overdue: "",
    owner_kind: "GESTIONNAIRE",
  };
}

export function AdminCollectionTranchesPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canAdmin = isFinflowAdmin(user);
  const canManage = canAdmin && hasPerm(user, "collections.change_collectiontranche");
  const [rows, setRows] = useState<DraftTranche[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const query = useQuery({
    queryKey: ["collection-tranches", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CollectionTranche>>("/collection-tranches/", {
          params: { page_size: 50, ordering: "position" },
        })
      ).data,
    enabled: canAdmin && !needsTenant,
  });

  useEffect(() => {
    if (query.data?.results) setRows(toDraft(query.data.results));
  }, [query.data]);

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<CollectionTranche[]>("/collection-tranches/replace/", {
          tranches: rows.map((row) => ({
            name: row.name.trim(),
            min_days_overdue: Number(row.min_days_overdue),
            max_days_overdue: row.max_days_overdue.trim()
              ? Number(row.max_days_overdue)
              : null,
            owner_kind: row.owner_kind,
            is_active: true,
          })),
        })
      ).data,
    onSuccess: (data) => {
      setSaved(true);
      setError(null);
      setRows(toDraft(data));
      qc.invalidateQueries({ queryKey: ["collection-tranches"] });
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

  function updateRow(key: string, patch: Partial<DraftTranche>) {
    setSaved(false);
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  function addRow() {
    setSaved(false);
    setRows((current) => {
      const last = current[current.length - 1];
      const lastMax = last?.max_days_overdue
        ? Number(last.max_days_overdue)
        : last?.min_days_overdue
          ? Number(last.min_days_overdue)
          : 0;
      const next = emptyRow(Number.isFinite(lastMax) ? lastMax + 1 : 1);
      if (last && !last.max_days_overdue) {
        return [
          ...current.slice(0, -1),
          { ...last, max_days_overdue: String(Math.max(lastMax, 1)) },
          next,
        ];
      }
      return [...current, next];
    });
  }

  function removeRow(key: string) {
    setSaved(false);
    setRows((current) => (current.length <= 1 ? current : current.filter((r) => r.key !== key)));
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
          icon={CircleDollarSign}
          title="Tranches de recouvrement"
          subtitle="Sélectionnez une filiale"
        />
        <p className="muted">
          Choisissez une filiale dans la barre supérieure pour paramétrer les
          tranches de retard.
        </p>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={CircleDollarSign}
        title="Tranches de recouvrement"
        subtitle="Nombre de niveaux et jours de retard — transfert automatique"
      />

      {query.isLoading ? (
        <Spinner />
      ) : query.isError ? (
        <ErrorState
          message="Impossible de charger les tranches."
          onRetry={() => query.refetch()}
        />
      ) : (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (canManage) save.mutate();
          }}
        >
          <p className="muted" style={{ marginBottom: 16 }}>
            Dès qu&apos;un dossier atteint le seuil d&apos;une tranche, il est
            transféré automatiquement (jamais en sens inverse). Le gestionnaire
            garde la première tranche ; le service recouvrement et le juridique
            reçoivent ensuite les files non affectées.
          </p>

          {error && (
            <div className="notice-error" role="alert" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}
          {saved && !error && (
            <div className="form-success" style={{ marginBottom: 16 }}>
              Tranches enregistrées. Le prochain recalcul des retards appliquera
              les transferts.
            </div>
          )}

          <div className="card" style={{ padding: 0, overflow: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Libellé</th>
                  <th>De (j)</th>
                  <th>À (j)</th>
                  <th>Responsable</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={row.key}>
                    <td>{index + 1}</td>
                    <td>
                      <input
                        value={row.name}
                        disabled={!canManage}
                        onChange={(e) =>
                          updateRow(row.key, { name: e.target.value })
                        }
                        placeholder={
                          index === 0
                            ? "Gestionnaire"
                            : index === rows.length - 1
                              ? "Juridique"
                              : "Service recouvrement"
                        }
                        required
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        disabled={!canManage}
                        min={1}
                        value={row.min_days_overdue}
                        onChange={(e) =>
                          updateRow(row.key, { min_days_overdue: e.target.value })
                        }
                        required
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        disabled={!canManage}
                        min={1}
                        value={row.max_days_overdue}
                        onChange={(e) =>
                          updateRow(row.key, { max_days_overdue: e.target.value })
                        }
                        placeholder={
                          index === rows.length - 1 ? "sans plafond" : ""
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={row.owner_kind}
                        disabled={!canManage}
                        onChange={(e) =>
                          updateRow(row.key, {
                            owner_kind: e.target.value as CollectionTrancheOwner,
                          })
                        }
                      >
                        {OWNER_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {canManage && <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => removeRow(row.key)}
                        disabled={rows.length <= 1}
                        aria-label="Supprimer la tranche"
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
            {canManage && <button type="button" className="btn btn-ghost" onClick={addRow}>
              <Plus size={16} /> Ajouter une tranche
            </button>}
            {canManage && <button
              type="submit"
              className="btn btn-primary"
              disabled={save.isPending || rows.length === 0}
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
