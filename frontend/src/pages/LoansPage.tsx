import { useQuery } from "@tanstack/react-query";
import { Banknote } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { PERM_COLLECTIONS, PERM_CREDITS } from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import {
  AgencyFilter,
  FilterField,
  FilterSelect,
  ListFilters,
  OfficerFilter,
  ProductFilter,
  SearchInput,
  countActive,
} from "@/components/ListFilters";
import {
  Badge,
  DEFAULT_PAGE_SIZE,
  PageHeader,
  PaginationBar,
  QueryStatus,
  TenantScopeNotice,
  formatDate,
  formatMoney,
} from "@/components/ui";

type LoanRow = {
  id: string;
  application: string;
  application_reference: string;
  client_display: string;
  currency: string;
  principal: string;
  interest_rate: string;
  duration_months: number;
  disbursed_at: string;
  first_due_date: string;
  status: string;
  core_banking_reference: string;
  cbs_contract_number: string;
  cbs_disbursement_status: string;
  collection_case_id?: string | null;
  collection_stage_display?: string;
};

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "En cours",
  CLOSED: "Soldé",
  DEFAULTED: "Défaut",
};

/** Au moins 15 prêts par page ; le surplus se parcourt dans le tableau. */
const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

export function LoansPage() {
  const navigate = useNavigate();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [product, setProduct] = useState("");
  const [agency, setAgency] = useState("");
  const [gestionnaire, setGestionnaire] = useState("");
  const [disbursedAfter, setDisbursedAfter] = useState("");
  const [disbursedBefore, setDisbursedBefore] = useState("");

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  const list = useQuery({
    queryKey: [
      "loans",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      status,
      search,
      product,
      agency,
      gestionnaire,
      disbursedAfter,
      disbursedBefore,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<LoanRow>>("/loans/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(status ? { status } : {}),
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(product ? { product } : {}),
            ...(agency ? { agency } : {}),
            ...(gestionnaire ? { gestionnaire } : {}),
            ...(disbursedAfter ? { disbursed_after: disbursedAfter } : {}),
            ...(disbursedBefore ? { disbursed_before: disbursedBefore } : {}),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  return (
    <div className="page-shell page-shell--list">
      <div className="list-page-chrome">
        <PageHeader
          icon={Banknote}
          title="Prêts"
          subtitle="Prêts mis en place et références CBS"
        />
        {needsTenant && <TenantScopeNotice />}

        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={setFilter(setSearch)}
              placeholder="Réf. dossier, client, CBS…"
            />
          }
          activeCount={countActive(
            search,
            gestionnaire,
            status,
            product,
            agency,
            disbursedAfter,
            disbursedBefore,
          )}
          onReset={() => {
            setSearch("");
            setGestionnaire("");
            setStatus("");
            setProduct("");
            setAgency("");
            setDisbursedAfter("");
            setDisbursedBefore("");
            setPage(1);
          }}
        >
          <OfficerFilter
            value={gestionnaire}
            onChange={setFilter(setGestionnaire)}
          />
          <FilterField label="Statut" active={!!status}>
            <FilterSelect value={status} onChange={setFilter(setStatus)}>
              <option value="">Tous statuts</option>
              <option value="ACTIVE">En cours</option>
              <option value="CLOSED">Soldé</option>
              <option value="DEFAULTED">Défaut</option>
            </FilterSelect>
          </FilterField>
          <ProductFilter value={product} onChange={setFilter(setProduct)} />
          <AgencyFilter value={agency} onChange={setFilter(setAgency)} />
          <FilterField label="Mis en place du" active={!!disbursedAfter}>
            <input
              type="date"
              value={disbursedAfter}
              onChange={(e) => setFilter(setDisbursedAfter)(e.target.value)}
            />
          </FilterField>
          <FilterField label="jusqu'au" active={!!disbursedBefore}>
            <input
              type="date"
              value={disbursedBefore}
              onChange={(e) => setFilter(setDisbursedBefore)(e.target.value)}
            />
          </FilterField>
        </ListFilters>
      </div>

      <div className="list-table-region">
        <QueryStatus
          isLoading={list.isLoading}
          isError={list.isError}
          isEmpty={!list.data?.results.length}
          emptyMessage="Aucun prêt pour cette filiale."
          onRetry={() => list.refetch()}
        >
          <>
            <div className="table-scroll table-scroll--fill">
              <table className="table card">
                <thead>
                  <tr>
                    <th>Dossier</th>
                    <th>Client</th>
                    <th className="num">Capital</th>
                    <th>Durée</th>
                    <th>Mis en place</th>
                    <th>Statut</th>
                    <th>CBS</th>
                    <th>Recouvrement</th>
                  </tr>
                </thead>
                <tbody>
                  {(list.data?.results ?? []).map((loan) => (
                    <tr
                      key={loan.id}
                      className="row-clickable"
                      onClick={() => navigate(`/dossiers/${loan.application}`)}
                    >
                      <td>
                        <PermLink
                          user={user}
                          anyOf={PERM_CREDITS}
                          to={`/dossiers/${loan.application}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {loan.application_reference ||
                            loan.application.slice(0, 8)}
                        </PermLink>
                      </td>
                      <td>{loan.client_display || "—"}</td>
                      <td className="num">
                        {formatMoney(loan.principal, loan.currency)}
                      </td>
                      <td>{loan.duration_months} mois</td>
                      <td>{formatDate(loan.disbursed_at)}</td>
                      <td>
                        <Badge
                          value={loan.status}
                          label={STATUS_LABELS[loan.status] ?? loan.status}
                        />
                      </td>
                      <td className="muted small">
                        {loan.cbs_contract_number ||
                          loan.core_banking_reference ||
                          loan.cbs_disbursement_status ||
                          "—"}
                      </td>
                      <td>
                        {loan.collection_case_id ? (
                          <PermLink
                            user={user}
                            anyOf={PERM_COLLECTIONS}
                            to={`/recouvrement/${loan.collection_case_id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {loan.collection_stage_display || "Dossier"}
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
              count={list.data?.count ?? 0}
              pageSize={LIST_PAGE_SIZE}
              onPageChange={setPage}
            />
          </>
        </QueryStatus>
      </div>
    </div>
  );
}
