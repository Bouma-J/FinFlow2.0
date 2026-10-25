import { useQuery } from "@tanstack/react-query";
import { Boxes } from "lucide-react";

import { api } from "@/api/client";
import type { CreditProduct, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import {
  Badge,
  PageHeader,
  QueryStatus,
  TenantScopeNotice,
  formatMoney,
} from "@/components/ui";

export function ProductsPage() {
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["credit-products", activeTenant, user?.tenant],
    queryFn: async () =>
      (await api.get<Paginated<CreditProduct>>("/credit-products/")).data,
    enabled: !needsTenant,
  });

  if (needsTenant) {
    return (
    <div className="page-shell">
        <PageHeader
          icon={Boxes}
          title="Produits de crédit"
          subtitle="Catalogue par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={Boxes}
        title="Produits de crédit"
        subtitle="Catalogue de la filiale"
      />
      <QueryStatus
        isLoading={isLoading}
        isError={isError}
        isEmpty={!data?.results.length}
        emptyMessage="Aucun produit paramétré."
        onRetry={() => refetch()}
      >
        <table className="table card">
          <thead>
            <tr>
              <th>Code</th>
              <th>Libellé</th>
              <th>Famille</th>
              <th className="num">Montant min</th>
              <th className="num">Montant max</th>
              <th className="num">Taux</th>
              <th>Actif</th>
            </tr>
          </thead>
          <tbody>
            {(data?.results ?? []).map((p) => (
              <tr key={p.id}>
                <td>{p.code}</td>
                <td>{p.label}</td>
                <td>{p.category_label}</td>
                <td className="num">{formatMoney(p.amount_min, p.currency)}</td>
                <td className="num">{formatMoney(p.amount_max, p.currency)}</td>
                <td className="num">{p.interest_rate} %</td>
                <td>
                  <Badge value={p.is_active ? "ACTIVE" : "DRAFT"} label={p.is_active ? "Oui" : "Non"} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </QueryStatus>
    </div>
  );
}
