import { useQuery } from "@tanstack/react-query";
import { FileText, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditApplication, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  AgencyFilter,
  CREDIT_STATUS_OPTIONS,
  ClientFilterBanner,
  FilterField,
  FilterSelect,
  ListFilters,
  OfficerFilter,
  ProductFilter,
  SearchInput,
  countActive,
  useClientSearchParam,
} from "@/components/ListFilters";
import {
  Badge,
  DEFAULT_PAGE_SIZE,
  PageHeader,
  PaginationBar,
  QueryStatus,
  TenantScopeNotice,
  formatMoney,
} from "@/components/ui";

/** Au moins 15 dossiers par page ; le surplus se parcourt dans le tableau. */
const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

export function CreditApplicationsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const { clientFilter, clearClientFilter } = useClientSearchParam();
  const canCreate = hasPerm(user, "credits.add_creditapplication");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(() => searchParams.get("status") ?? "");
  const [product, setProduct] = useState("");
  const [agency, setAgency] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [gestionnaire, setGestionnaire] = useState("");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      "credit-applications",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      search,
      status,
      product,
      agency,
      riskLevel,
      gestionnaire,
      clientFilter,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditApplication>>("/credit-applications/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(status ? { status } : {}),
            ...(product ? { product } : {}),
            ...(agency ? { agency } : {}),
            ...(riskLevel ? { risk_level: riskLevel } : {}),
            ...(gestionnaire ? { gestionnaire } : {}),
            ...(clientFilter ? { client: clientFilter } : {}),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  return (
    <div className="page-shell page-shell--list">
      <div className="list-page-chrome">
        <PageHeader
          icon={FileText}
          title="Dossiers de crédit"
          subtitle="Instruction, approbation et mise en place"
          actions={
            canCreate ? (
              <Link className="btn btn-primary" to="/dossiers/nouveau">
                <Plus />
                Nouveau dossier
              </Link>
            ) : undefined
          }
        />
        {needsTenant && <TenantScopeNotice />}

        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={setFilter(setSearch)}
              placeholder="Réf. dossier, client…"
            />
          }
          activeCount={countActive(
            search,
            gestionnaire,
            status,
            product,
            agency,
            riskLevel,
            clientFilter,
          )}
          onReset={() => {
            setSearch("");
            setGestionnaire("");
            setStatus("");
            setProduct("");
            setAgency("");
            setRiskLevel("");
            setPage(1);
            if (clientFilter) clearClientFilter();
          }}
        >
          <OfficerFilter
            value={gestionnaire}
            onChange={setFilter(setGestionnaire)}
          />
          <FilterField label="Statut" active={!!status}>
            <FilterSelect value={status} onChange={setFilter(setStatus)}>
              {CREDIT_STATUS_OPTIONS.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <ProductFilter value={product} onChange={setFilter(setProduct)} />
          <AgencyFilter value={agency} onChange={setFilter(setAgency)} />
          <FilterField label="Risque" active={!!riskLevel}>
            <FilterSelect value={riskLevel} onChange={setFilter(setRiskLevel)}>
              <option value="">Tous risques</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={String(n)}>
                  Risque {n}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
        </ListFilters>
        <ClientFilterBanner
          clientId={clientFilter}
          onClear={() => {
            clearClientFilter();
            setPage(1);
          }}
        />
      </div>

      <div className="list-table-region">
        <QueryStatus
          isLoading={isLoading}
          isError={isError}
          isEmpty={!data?.results.length}
          emptyMessage="Aucun dossier ne correspond à ces critères."
          onRetry={() => refetch()}
        >
          <>
            <div className="table-scroll table-scroll--fill">
              <table className="table card">
                <thead>
                  <tr>
                    <th>Référence</th>
                    <th>Client</th>
                    <th>Produit</th>
                    <th>Agence</th>
                    <th>Gestionnaire</th>
                    <th className="num">Montant</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.results ?? []).map((a) => (
                    <tr
                      key={a.id}
                      className="row-clickable"
                      onClick={() => navigate(`/dossiers/${a.id}`)}
                    >
                      <td>
                        <code>{a.reference || a.id.slice(0, 8)}</code>
                      </td>
                      <td>{a.client_display}</td>
                      <td>{a.product_label}</td>
                      <td>{a.agency_display || "—"}</td>
                      <td>{a.submitted_by_display || "—"}</td>
                      <td className="num">
                        {formatMoney(a.amount_requested, a.currency)}
                      </td>
                      <td>
                        <Badge value={a.status} label={a.status_display} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationBar
              page={page}
              count={data?.count ?? 0}
              pageSize={LIST_PAGE_SIZE}
              onPageChange={setPage}
            />
          </>
        </QueryStatus>
      </div>
    </div>
  );
}
