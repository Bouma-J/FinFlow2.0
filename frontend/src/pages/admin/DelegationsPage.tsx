import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type {
  AdminUser,
  Delegation,
  Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  TenantScopeNotice,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function plusDaysISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function userLabel(u: AdminUser) {
  const name = `${u.first_name} ${u.last_name}`.trim();
  return name || u.username;
}

export function AdminDelegationsPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canAdd = hasPerm(user, "accounts.add_delegation");
  const canChange = hasPerm(user, "accounts.change_delegation");

  const [activeOnly, setActiveOnly] = useState(true);
  const [delegator, setDelegator] = useState("");
  const [delegate, setDelegate] = useState("");
  const [startDate, setStartDate] = useState(todayISO);
  const [endDate, setEndDate] = useState(() => plusDaysISO(7));
  const [reason, setReason] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [product, setProduct] = useState("");
  const [agency, setAgency] = useState("");
  const [stepKind, setStepKind] = useState("");
  const products = useQuery({ queryKey: ["delegation-products", activeTenant], enabled: !needsTenant, queryFn: async () => (await api.get<Paginated<{ id: string; label: string }>>("/credit-products/", { params: { page_size: 300 } })).data });
  const agencies = useQuery({ queryKey: ["delegation-agencies", activeTenant], enabled: !needsTenant, queryFn: async () => (await api.get<Paginated<{ id: string; name: string }>>("/agencies/", { params: { page_size: 300 } })).data });
  const [error, setError] = useState<string | null>(null);

  const users = useQuery({
    queryKey: ["admin-users-for-delegations", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<AdminUser>>("/users/", {
          params: { page_size: 300, is_active: true },
        })
      ).data,
    enabled: !needsTenant,
  });

  const list = useQuery({
    queryKey: ["admin-delegations", activeTenant, activeOnly],
    queryFn: async () =>
      (
        await api.get<Paginated<Delegation>>("/delegations/", {
          params: {
            ...(activeOnly ? { is_active: true } : {}),
            ordering: "-start_date",
            page_size: 100,
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<Delegation>("/delegations/", {
          delegator,
          delegate,
          start_date: startDate,
          end_date: endDate,
          reason,
          max_amount: maxAmount || null, product: product || null, agency: agency || null, step_kind: stepKind,
          is_active: true,
        })
      ).data,
    onSuccess: () => {
      setError(null);
      setReason("");
      qc.invalidateQueries({ queryKey: ["admin-delegations"] });
    },
    onError: (err: unknown) => {
      setError(apiErrorMessage(err, "Création impossible."));
    },
  });

  const revoke = useMutation({
    mutationFn: async (id: string) =>
      (await api.post<Delegation>(`/delegations/${id}/revoke/`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-delegations"] });
    },
  });
  const approve = useMutation({ mutationFn: (id: string) => api.post(`/delegations/${id}/approve/`), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-delegations"] }), onError: (cause) => setError(apiErrorMessage(cause, "Approbation impossible.")) });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!delegator || !delegate) {
      setError("Choisissez le délégant et le délégataire.");
      return;
    }
    create.mutate();
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={ArrowLeftRight}
          title="Délégations"
          subtitle="Par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  const rows = list.data?.results ?? [];

  return (
    <div className="page-shell">
      <PageHeader
        icon={ArrowLeftRight}
        title="Délégations"
        subtitle="Absences et remplacements — le délégataire voit les tâches du circuit"
      />

      {canAdd && (
        <Card title="Nouvelle délégation">
          <form className="stack" onSubmit={onCreate}>
            <div className="form-grid two-col">
              <label className="field"><span>Plafond délégué (vide : sans plafond supplémentaire)</span><input type="number" min={0} value={maxAmount} onChange={(event) => setMaxAmount(event.target.value)} /></label>
              <label className="field"><span>Produit</span><select value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Tous</option>{products.data?.results.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
              <label className="field"><span>Agence</span><select value={agency} onChange={(event) => setAgency(event.target.value)}><option value="">Toutes les agences autorisées</option>{agencies.data?.results.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
              <label className="field"><span>Nature d'acte</span><select value={stepKind} onChange={(event) => setStepKind(event.target.value)}><option value="">Toutes</option><option value="CONSULTATIVE">Avis consultatif</option><option value="DECISIONAL">Décision</option></select></label>
              <label className="field">
                <span>Délégant *</span>
                <select
                  value={delegator}
                  onChange={(e) => setDelegator(e.target.value)}
                  required
                >
                  <option value="">— choisir —</option>
                  {(users.data?.results ?? []).map((u) => (
                    <option key={u.id} value={u.id}>
                      {userLabel(u)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Délégataire *</span>
                <select
                  value={delegate}
                  onChange={(e) => setDelegate(e.target.value)}
                  required
                >
                  <option value="">— choisir —</option>
                  {(users.data?.results ?? []).map((u) => (
                    <option key={u.id} value={u.id}>
                      {userLabel(u)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Début *</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Fin *</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  required
                />
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>Motif</span>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Congé, mission…"
                />
              </label>
            </div>
            {error && <div className="form-error">{error}</div>}
            <button
              className="btn btn-primary btn-sm"
              disabled={create.isPending}
              type="submit"
            >
              <Plus size={14} />
              Créer
            </button>
          </form>
        </Card>
      )}

      <Card title="Liste">
        <label className="checkbox" style={{ marginBottom: 12 }}>
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          <span>Actives seulement</span>
        </label>
        {list.isLoading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <EmptyState message="Aucune délégation." />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Délégant</th>
                <th>Délégataire</th>
                <th>Période</th>
                <th>Motif</th>
                <th>Statut</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td>{d.delegator_display}</td>
                  <td>{d.delegate_display}</td>
                  <td className="small">
                    {d.start_date} → {d.end_date}
                  </td>
                  <td className="small">{d.reason || "—"}{d.max_amount && <div>Plafond : {d.max_amount}</div>}{d.step_kind && <div>{d.step_kind}</div>}</td>
                  <td>
                    <Badge
                      value={
                        d.is_currently_valid
                          ? "success"
                          : d.is_active
                            ? "warning"
                            : "info"
                      }
                      label={
                        d.approval_required && !d.approved_by ? "Approbation requise" : d.is_currently_valid
                          ? "En cours"
                          : d.is_active
                            ? "Planifiée / expirée"
                            : "Révoquée"
                      }
                    />
                  </td>
                  <td>
                    {canChange && d.approval_required && !d.approved_by && user?.id !== d.delegator && user?.id !== d.delegate && <button className="btn btn-ghost btn-sm" type="button" disabled={approve.isPending} onClick={() => approve.mutate(d.id)}>Approuver</button>}
                    {canChange && d.is_active && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={revoke.isPending}
                        onClick={() => {
                          if (
                            !window.confirm(
                              `Révoquer la délégation ${d.delegator_display} → ${d.delegate_display} ?`,
                            )
                          ) {
                            return;
                          }
                          revoke.mutate(d.id);
                        }}
                      >
                        Révoquer
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
