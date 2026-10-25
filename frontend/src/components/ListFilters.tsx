import { RotateCcw, Search, X } from "lucide-react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useAgencyOptions,
  useOfficerOptions,
  useProductOptions,
} from "@/hooks/useListLookups";

export function countActive(
  ...values: Array<string | boolean | null | undefined>
) {
  return values.filter((value) =>
    typeof value === "boolean" ? value : Boolean(value && String(value).trim()),
  ).length;
}

export function ListFilters({
  search,
  children,
  extra,
  onReset,
  activeCount = 0,
}: {
  search?: ReactNode;
  children?: ReactNode;
  extra?: ReactNode;
  onReset?: () => void;
  activeCount?: number;
}) {
  const showTop = Boolean(search) || (Boolean(onReset) && activeCount > 0);
  return (
    <section className="filters-panel" aria-label="Filtres de liste">
      {showTop ? (
        <div className={`filters-panel-top${search ? "" : " is-actions-only"}`}>
          {search ? (
            <div className="filters-panel-search-slot">{search}</div>
          ) : null}
          <div className="filters-panel-actions">
            {activeCount > 0 && (
              <span className="filters-panel-badge">
                {activeCount} filtre{activeCount > 1 ? "s" : ""}
              </span>
            )}
            {onReset && activeCount > 0 && (
              <button type="button" className="filters-reset" onClick={onReset}>
                <RotateCcw size={14} />
                Réinitialiser
              </button>
            )}
          </div>
        </div>
      ) : null}
      {children ? <div className="filters-panel-grid">{children}</div> : null}
      {extra ? <div className="filters-panel-extra">{extra}</div> : null}
    </section>
  );
}

export function FilterField({
  label,
  children,
  active = false,
}: {
  label: string;
  children: ReactNode;
  active?: boolean;
}) {
  return (
    <label className={`filter-field${active ? " is-active" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="filters-search">
      <Search size={16} />
      <input
        type="search"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value ? (
        <button
          type="button"
          className="filters-search-clear"
          aria-label="Effacer la recherche"
          onClick={() => onChange("")}
        >
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}

export function FilterSelect({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {children}
    </select>
  );
}

export function FilterToggle({
  label,
  checked,
  onChange,
  title,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      className={`filter-toggle${checked ? " is-on" : ""}`}
      title={title}
      onClick={() => onChange(!checked)}
    >
      {label}
    </button>
  );
}

export function OfficerFilter({
  value,
  onChange,
  label = "Gestionnaire",
  emptyLabel = "Tous les gestionnaires",
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  emptyLabel?: string;
}) {
  const officers = useOfficerOptions();
  return (
    <FilterField label={label} active={!!value}>
      <FilterSelect value={value} onChange={onChange}>
        <option value="">{emptyLabel}</option>
        {(officers.data ?? []).map((o) => (
          <option key={o.id} value={o.id}>
            {o.display_name}
          </option>
        ))}
      </FilterSelect>
    </FilterField>
  );
}

export function ProductFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const products = useProductOptions();
  return (
    <FilterField label="Produit" active={!!value}>
      <FilterSelect value={value} onChange={onChange}>
        <option value="">Tous les produits</option>
        {(products.data ?? []).map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </FilterSelect>
    </FilterField>
  );
}

export function AgencyFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const agencies = useAgencyOptions();
  return (
    <FilterField label="Agence" active={!!value}>
      <FilterSelect value={value} onChange={onChange}>
        <option value="">Toutes les agences</option>
        {(agencies.data ?? []).map((a) => (
          <option key={a.id} value={a.id}>
            {a.code ? `${a.code} — ${a.name}` : a.name}
          </option>
        ))}
      </FilterSelect>
    </FilterField>
  );
}

export const CREDIT_STATUS_OPTIONS = [
  ["", "Tous statuts"],
  ["DRAFT", "Brouillon"],
  ["SUBMITTED", "Soumis"],
  ["IN_APPROVAL", "En cours d'approbation"],
  ["APPROVED", "Approuvé"],
  ["REJECTED", "Rejeté"],
  ["RETURNED", "Retourné pour correction"],
  ["CONTRACT_GENERATED", "Contrat généré"],
  ["DISBURSEMENT_PENDING", "Mise en place en attente"],
  ["DISBURSED", "Mis en place"],
  ["CLOSED", "Clôturé"],
  ["CANCELLED", "Annulé"],
] as const;

export function useClientSearchParam() {
  const [searchParams, setSearchParams] = useSearchParams();
  const clientFilter = searchParams.get("client") || "";

  function clearClientFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete("client");
    setSearchParams(next, { replace: true });
  }

  return { clientFilter, clearClientFilter };
}

export function ClientFilterBanner({
  clientId,
  onClear,
}: {
  clientId: string;
  onClear: () => void;
}) {
  if (!clientId) return null;
  return (
    <p className="muted small" style={{ marginTop: 8 }}>
      Filtré sur ce client{" "}
      <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
        <X size={14} />
        Retirer
      </button>
    </p>
  );
}

export const PROCESS_STATUS_OPTIONS = [
  ["", "Tous statuts"],
  ["DRAFT", "Brouillon"],
  ["IN_PROGRESS", "En cours"],
  ["IN_APPROVAL", "En validation"],
  ["APPROVED", "Approuvée"],
  ["REJECTED", "Rejetée"],
  ["RETURNED", "Retournée"],
  ["COMPLETED", "Clôturée"],
  ["CANCELLED", "Annulée"],
  ["BLOCKED", "Bloquée (CBS)"],
] as const;
