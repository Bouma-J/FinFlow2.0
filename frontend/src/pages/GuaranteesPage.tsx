import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Guarantee, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { PERM_COLLECTIONS, PERM_CREDITS } from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import {
  AgencyFilter,
  ClientFilterBanner,
  FilterField,
  FilterSelect,
  ListFilters,
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

const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

export function GuaranteesPage() {
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { clientFilter, clearClientFilter } = useClientSearchParam();
  const applicationFilter = searchParams.get("application") || "";
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [guaranteeType, setGuaranteeType] = useState("");
  const [agency, setAgency] = useState("");
  const [formalized, setFormalized] = useState("");

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  function clearApplicationFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete("application");
    setSearchParams(next, { replace: true });
    setPage(1);
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      "guarantees",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      search,
      status,
      guaranteeType,
      agency,
      formalized,
      applicationFilter,
      clientFilter,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<Guarantee>>("/guarantees/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(status ? { status } : {}),
            ...(guaranteeType ? { guarantee_type: guaranteeType } : {}),
            ...(agency ? { agency } : {}),
            ...(formalized ? { formalized } : {}),
            ...(applicationFilter ? { application: applicationFilter } : {}),
            ...(clientFilter ? { client: clientFilter } : {}),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  const dossierLabel =
    data?.results.find((g) => g.application === applicationFilter)
      ?.application_reference ||
    (applicationFilter ? applicationFilter.slice(0, 8) : "");

  return (
    <div className="page-shell page-shell--list">
      <div className="list-page-chrome">
        <PageHeader
          icon={ShieldCheck}
          title="Garanties"
          subtitle="Sûretés adossées aux crédits"
        />
        {needsTenant && <TenantScopeNotice />}
        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={setFilter(setSearch)}
              placeholder="Référence, client, propriétaire…"
            />
          }
          activeCount={countActive(
            search,
            status,
            guaranteeType,
            agency,
            formalized,
            applicationFilter,
            clientFilter,
          )}
          onReset={() => {
            setSearch("");
            setStatus("");
            setGuaranteeType("");
            setAgency("");
            setFormalized("");
            setPage(1);
            if (applicationFilter) clearApplicationFilter();
            if (clientFilter) clearClientFilter();
          }}
        >
          <FilterField label="Statut" active={!!status}>
            <FilterSelect value={status} onChange={setFilter(setStatus)}>
              <option value="">Tous statuts</option>
              <option value="ACTIVE">Active</option>
              <option value="RELEASED">Mainlevée</option>
              <option value="REALIZED">Réalisée</option>
              <option value="TRANSFERRED">Transférée</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Type" active={!!guaranteeType}>
            <FilterSelect
              value={guaranteeType}
              onChange={setFilter(setGuaranteeType)}
            >
              <option value="">Tous types</option>
              <option value="MORTGAGE">Hypothèque</option>
              <option value="PLEDGE">Gage</option>
              <option value="FINANCIAL">Garantie financière</option>
              <option value="LIEN">Nantissement</option>
              <option value="DEPOSIT">Dépôt de garantie</option>
              <option value="BANK_GUARANTEE">Garantie bancaire</option>
              <option value="DATION">Dation en paiement</option>
              <option value="JOINT">Garantie solidaire</option>
              <option value="OTHER">Autre</option>
            </FilterSelect>
          </FilterField>
          <AgencyFilter value={agency} onChange={setFilter(setAgency)} />
          <FilterField label="Formalisation" active={!!formalized}>
            <FilterSelect
              value={formalized}
              onChange={setFilter(setFormalized)}
            >
              <option value="">Toutes</option>
              <option value="1">Formalisée</option>
              <option value="0">À formaliser</option>
            </FilterSelect>
          </FilterField>
        </ListFilters>
        {applicationFilter && (
          <p className="muted small" style={{ marginTop: 8 }}>
            Filtré sur le dossier {dossierLabel}{" "}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={clearApplicationFilter}
            >
              <X size={14} />
              Retirer
            </button>
          </p>
        )}
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
          emptyMessage="Aucune garantie ne correspond à ces critères."
          onRetry={() => refetch()}
        >
          <>
            <div className="table-scroll table-scroll--fill">
              <table className="table card">
                <thead>
                  <tr>
                    <th>Référence</th>
                    <th>Client</th>
                    <th>Dossier</th>
                    <th>Type</th>
                    <th className="num">Valeur actualisée</th>
                    <th>Statut</th>
                    <th>Recouvrement</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.results ?? []).map((g) => (
                    <tr
                      key={g.id}
                      className="row-clickable"
                      onClick={() => navigate(`/garanties/${g.id}`)}
                    >
                      <td>{g.reference || g.id.slice(0, 8)}</td>
                      <td>{g.client_display || "—"}</td>
                      <td>
                        {g.application ? (
                          <PermLink
                            user={user}
                            anyOf={PERM_CREDITS}
                            to={`/dossiers/${g.application}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {g.application_reference ||
                              g.application.slice(0, 8)}
                          </PermLink>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>{g.type_display}</td>
                      <td className="num">{formatMoney(g.current_value)}</td>
                      <td>
                        <Badge value={g.status} />
                        {g.formalized_at ? (
                          <Badge value="OK" label="Formalisée" />
                        ) : null}
                        {g.process_busy ? (
                          <Badge
                            value="IN_PROGRESS"
                            label={g.process_busy.label}
                          />
                        ) : null}
                      </td>
                      <td>
                        {g.collection_case_id ? (
                          <PermLink
                            user={user}
                            anyOf={PERM_COLLECTIONS}
                            to={`/recouvrement/${g.collection_case_id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {g.collection_stage_display || "Dossier"}
                          </PermLink>
                        ) : (
                          <span className="muted">—</span>
                        )}
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
