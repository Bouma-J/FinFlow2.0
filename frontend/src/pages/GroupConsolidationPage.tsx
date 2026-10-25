import { useQuery } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import type { DashboardData } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import {
  FilterField,
  FilterSelect,
  ListFilters,
} from "@/components/ListFilters";
import {
  ErrorState,
  PageHeader,
  Spinner,
  StatCard,
  formatMoney,
} from "@/components/ui";

type BreakdownRow = Record<string, string | number | null>;

type BreakdownPayload = {
  dimension: string;
  rows: BreakdownRow[];
};

const DIMENSIONS = [
  { value: "tenant", label: "Filiale", field: "tenant_id" },
  { value: "country", label: "Pays", field: "tenant__country" },
  { value: "zone", label: "Zone", field: "tenant__zone" },
];

export function GroupConsolidationPage() {
  const { user } = useAuth();
  const [dimension, setDimension] = useState("tenant");

  const dash = useQuery({
    queryKey: ["group-consolidation"],
    queryFn: async () =>
      (await api.get<DashboardData>("/reporting/group-consolidation/")).data,
    enabled: Boolean(user?.is_group_level),
  });

  const breakdown = useQuery({
    queryKey: ["group-breakdown", dimension],
    queryFn: async () =>
      (
        await api.get<BreakdownPayload>("/reporting/group-breakdown/", {
          params: { dimension },
        })
      ).data,
    enabled: Boolean(user?.is_group_level),
  });

  if (!user?.is_group_level) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Layers}
          title="Consolidation Groupe"
          subtitle="Réservé au niveau Groupe"
        />
        <ErrorState message="Accès réservé aux utilisateurs Groupe." />
      </div>
    );
  }

  if (dash.isLoading) return <Spinner />;
  if (dash.isError || !dash.data) {
    return (
      <div className="page-shell">
        <PageHeader icon={Layers} title="Consolidation Groupe" />
        <ErrorState
          message="Impossible de charger la consolidation."
          onRetry={() => dash.refetch()}
        />
      </div>
    );
  }

  const s = dash.data.credits.summary;
  const portfolio = dash.data.portfolio;
  const dimMeta =
    DIMENSIONS.find((d) => d.value === dimension) ?? DIMENSIONS[0];

  return (
    <div className="page-shell">
      <PageHeader
        icon={Layers}
        title="Consolidation Groupe"
        subtitle="Vue multi-filiales (crédits, portefeuille, risque)"
      />

      <div className="stat-grid" style={{ marginBottom: 20 }}>
        <StatCard label="Dossiers" value={String(s.total)} />
        <StatCard
          label="Montant demandé"
          value={formatMoney(s.amount_requested)}
        />
        <StatCard
          label="Approuvé"
          value={formatMoney(s.amount_approved)}
        />
        <StatCard
          label="Mis en place"
          value={formatMoney(s.disbursed_amount)}
        />
        <StatCard
          label="Prêts actifs"
          value={String(portfolio.active_loans)}
        />
        <StatCard
          label="Échéances en retard"
          value={String(portfolio.overdue_installments)}
        />
      </div>

      <ListFilters>
        <FilterField label="Axe" active>
          <FilterSelect value={dimension} onChange={setDimension}>
            {DIMENSIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
      </ListFilters>

      {breakdown.isLoading ? (
        <Spinner />
      ) : breakdown.isError ? (
        <ErrorState
          message="Impossible de charger la décomposition."
          onRetry={() => breakdown.refetch()}
        />
      ) : (
        <table className="table card">
          <thead>
            <tr>
              <th>{dimMeta.label}</th>
              <th>Dossiers</th>
              <th>Demandé</th>
              <th>Approuvé</th>
            </tr>
          </thead>
          <tbody>
            {(breakdown.data?.rows ?? []).map((row, idx) => {
              const keyVal = row[dimMeta.field] ?? row.tenant_id ?? idx;
              return (
                <tr key={String(keyVal)}>
                  <td>
                    <strong>{String(keyVal ?? "—")}</strong>
                  </td>
                  <td className="num">{Number(row.count ?? 0)}</td>
                  <td className="num">
                    {formatMoney(
                      row.amount_requested != null
                        ? String(row.amount_requested)
                        : null,
                    )}
                  </td>
                  <td className="num">
                    {formatMoney(
                      row.amount_approved != null
                        ? String(row.amount_approved)
                        : null,
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
