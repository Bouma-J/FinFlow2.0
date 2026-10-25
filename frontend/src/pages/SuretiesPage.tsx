import { useQuery } from "@tanstack/react-query";
import { HandCoins, Plus, TriangleAlert, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { Paginated, Surety } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { SuretyForm } from "@/components/SuretyForm";
import {
  AgencyFilter,
  FilterField,
  FilterSelect,
  ListFilters,
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
  formatMoney,
} from "@/components/ui";

const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

export function SuretiesPage() {
  const navigate = useNavigate();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canCreate = hasPerm(user, "sureties.add_surety");
  const [showForm, setShowForm] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [suretyType, setSuretyType] = useState("");
  const [isActive, setIsActive] = useState("");
  const [agency, setAgency] = useState("");
  const listMode = !(showForm && !needsTenant);

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      "sureties",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      search,
      suretyType,
      isActive,
      agency,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<Surety>>("/sureties/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(suretyType ? { surety_type: suretyType } : {}),
            ...(isActive ? { is_active: isActive } : {}),
            ...(agency ? { agency } : {}),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  return (
    <div className={`page-shell${listMode ? " page-shell--list" : ""}`}>
      <div className="list-page-chrome">
        <PageHeader
          icon={HandCoins}
          title="Cautions"
          subtitle="Personnes s'engageant en garantie d'un emprunteur"
          actions={
            canCreate ? (
              <button
                className="btn btn-primary"
                onClick={() => setShowForm((s) => !s)}
              >
                {showForm ? <X /> : <Plus />}
                {showForm ? "Fermer" : "Nouvelle caution"}
              </button>
            ) : undefined
          }
        />
        {needsTenant && <TenantScopeNotice />}

        {showForm && needsTenant && (
          <div className="notice-warning">
            <TriangleAlert size={18} />
            <span>
              Vous êtes connecté au niveau Groupe. Sélectionnez d'abord une
              filiale dans la barre supérieure pour enregistrer une caution.
            </span>
          </div>
        )}
      </div>

      {showForm && !needsTenant ? (
        <SuretyForm
          onSuccess={() => setShowForm(false)}
          onCancel={() => setShowForm(false)}
        />
      ) : (
        <>
          <div className="list-page-chrome">
            <ListFilters
              search={
                <SearchInput
                  value={search}
                  onChange={setFilter(setSearch)}
                  placeholder="Nom, téléphone, pièce, IFU, RCCM…"
                />
              }
              activeCount={countActive(search, suretyType, isActive, agency)}
              onReset={() => {
                setSearch("");
                setSuretyType("");
                setIsActive("");
                setAgency("");
                setPage(1);
              }}
            >
              <FilterField label="Type" active={!!suretyType}>
                <FilterSelect
                  value={suretyType}
                  onChange={setFilter(setSuretyType)}
                >
                  <option value="">Tous types</option>
                  <option value="PHYSICAL">Personne physique</option>
                  <option value="MORAL">Personne morale</option>
                </FilterSelect>
              </FilterField>
              <FilterField label="Statut" active={!!isActive}>
                <FilterSelect
                  value={isActive}
                  onChange={setFilter(setIsActive)}
                >
                  <option value="">Actives et inactives</option>
                  <option value="true">Actives</option>
                  <option value="false">Inactives</option>
                </FilterSelect>
              </FilterField>
              <AgencyFilter value={agency} onChange={setFilter(setAgency)} />
            </ListFilters>
          </div>
          <div className="list-table-region">
            <QueryStatus
              isLoading={isLoading}
              isError={isError}
              isEmpty={!data?.results.length}
              emptyMessage="Aucune caution ne correspond à ces critères."
              onRetry={() => refetch()}
            >
              <>
                <div className="table-scroll table-scroll--fill">
                  <table className="table card">
                    <thead>
                      <tr>
                        <th>Nom & prénom</th>
                        <th>Client cautionné</th>
                        <th className="num">Montant crédit</th>
                        <th className="num">Montant cautionné</th>
                        <th>Activité</th>
                        <th>Téléphone</th>
                        <th>Statut</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data?.results ?? []).map((s) => (
                        <tr
                          key={s.id}
                          className="row-clickable"
                          onClick={() => navigate(`/cautions/${s.id}`)}
                        >
                          <td>{s.display_name}</td>
                          <td>{s.client_display || "—"}</td>
                          <td className="num">
                            {s.credit_amount
                              ? formatMoney(
                                  s.credit_amount,
                                  s.credit_currency || "XOF",
                                )
                              : "—"}
                          </td>
                          <td className="num">
                            {s.guaranteed_amount
                              ? formatMoney(
                                  s.guaranteed_amount,
                                  s.credit_currency || "XOF",
                                )
                              : "—"}
                          </td>
                          <td>{s.activity || "—"}</td>
                          <td>{s.phone || "—"}</td>
                          <td>
                            <Badge
                              value={s.is_active ? "ACTIVE" : "DRAFT"}
                              label={s.is_active ? "Active" : "Inactive"}
                            />
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
        </>
      )}
    </div>
  );
}
