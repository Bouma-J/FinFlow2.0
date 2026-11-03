import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Package, Percent, Plus, Save, X } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/api/client";
import { allCbsReferences } from "@/api/cbs";
import type { CbsProductReference, CreditProduct, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  FilterField,
  FilterSelect,
  FilterToggle,
  ListFilters,
  SearchInput,
  countActive,
} from "@/components/ListFilters";
import {
  Badge,
  PageHeader,
  QueryStatus,
  TenantScopeNotice,
  formatMoney,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const CLIENT_TYPES: { value: string; label: string }[] = [
  { value: "ALL", label: "Tous les clients" },
  { value: "INDIVIDUAL", label: "Particulier" },
  { value: "PROFESSIONAL", label: "Groupement" },
  { value: "CORPORATE", label: "Entreprise" },
];

const DEMO_CBS_PRODUCT_CODES = new Set([
  "CRED-TRESO",
  "CRED-TRESO-PRO",
  "CRED-IMMO",
  "CRED-IMMO-PROMO",
  "CRED-CONSO",
  "CRED-EQUIP",
  "CRED-AGRO",
  "COMPTE-COURANT",
]);

const EMPTY_PROD = {
  code: "",
  label: "",
  description: "",
  client_type: "ALL",
  currency: "XOF",
  amount_min: "100000",
  amount_max: "50000000",
  duration_min_months: 3,
  duration_max_months: 36,
  interest_rate: "12.5",
  processing_fee_rate: "0",
  requires_guarantee: false,
  cbs_product_code: "",
  is_active: true,
};

function FormBlock({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: typeof Package;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="tenant-form-block">
      <header className="tenant-form-block-head">
        <span className="tenant-form-block-icon">
          <Icon size={17} />
        </span>
        <div>
          <h3 className="tenant-form-block-title">{title}</h3>
          {description && (
            <p className="tenant-form-block-desc">{description}</p>
          )}
        </div>
      </header>
      <div className="tenant-form-block-body">{children}</div>
    </section>
  );
}

function clientTypeLabel(value?: string) {
  return CLIENT_TYPES.find((t) => t.value === value)?.label ?? "Tous";
}

function creditCbsCode(
  product: CreditProduct,
  references: CbsProductReference[] = [],
) {
  const code = product.cbs_product_code?.trim() || "";
  const legacyCode = references.find(
    (reference) => reference.id === product.cbs_credit_product,
  )?.cbs_code;
  if (code && !DEMO_CBS_PRODUCT_CODES.has(code.toUpperCase())) return code;
  if (legacyCode && !DEMO_CBS_PRODUCT_CODES.has(legacyCode.toUpperCase())) {
    return legacyCode;
  }
  return code;
}

export function AdminProductsPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canAddProduct = hasPerm(user, "catalog.add_creditproduct");
  const canChangeProduct = hasPerm(user, "catalog.change_creditproduct");

  const [prod, setProd] = useState({ ...EMPTY_PROD });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [clientTypeFilter, setClientTypeFilter] = useState("");
  const [showInactive, setShowInactive] = useState(false);

  const products = useQuery({
    queryKey: [
      "credit-products",
      activeTenant,
      search,
      clientTypeFilter,
      showInactive,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditProduct>>("/credit-products/", {
          params: {
            page_size: 200,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(clientTypeFilter ? { client_type: clientTypeFilter } : {}),
            ...(showInactive ? {} : { is_active: true }),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () =>
      (await api.get<Paginated<{ id: string; code: string; name: string }>>(
        "/tenants/",
      )).data,
    enabled: !!user?.is_group_level,
  });

  const cbsProducts = useQuery({
    queryKey: ["cbs-product-references", activeTenant, "credit-confirmed"],
    queryFn: () => allCbsReferences<CbsProductReference>("/cbs-product-references/", {
      kind: "CREDIT", is_active: true, verification_status: "VERIFIED", for_active_connector: true,
    }),
    enabled: !needsTenant,
    staleTime: 0,
  });

  const scopeLabel = user?.is_group_level
    ? tenants.data?.results.find((t) => t.id === activeTenant)?.name ??
      "filiale sélectionnée"
    : "votre filiale";

  const saveProd = useMutation({
    mutationFn: async () => {
      const payload = {
        ...prod,
        cbs_product_code: prod.cbs_product_code.trim(),
        duration_min_months: Number(prod.duration_min_months),
        duration_max_months: Number(prod.duration_max_months),
      };
      if (editingId) {
        return (await api.patch(`/credit-products/${editingId}/`, payload)).data;
      }
      return (await api.post("/credit-products/", payload)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credit-products"] });
      setError(null);
      setShowForm(false);
      setEditingId(null);
      setProd({ ...EMPTY_PROD });
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Enregistrement impossible. Vérifiez les champs.")),
  });

  const toggleActive = useMutation({
    mutationFn: async (p: CreditProduct) =>
      (await api.patch(`/credit-products/${p.id}/`, { is_active: !p.is_active }))
        .data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credit-products"] }),
  });

  function openCreate() {
    if (!canAddProduct) return;
    setEditingId(null);
    setProd({ ...EMPTY_PROD });
    setError(null);
    setShowForm(true);
  }

  function openEdit(p: CreditProduct) {
    if (!canChangeProduct) return;
    setEditingId(p.id);
    setProd({
      code: p.code,
      label: p.label,
      description: p.description ?? "",
      client_type: p.client_type ?? "ALL",
      currency: p.currency,
      amount_min: p.amount_min,
      amount_max: p.amount_max,
      duration_min_months: p.duration_min_months ?? 3,
      duration_max_months: p.duration_max_months ?? 36,
      interest_rate: p.interest_rate,
      processing_fee_rate: p.processing_fee_rate ?? "0",
      requires_guarantee: Boolean(p.requires_guarantee),
      cbs_product_code: creditCbsCode(p, cbsProducts.data ?? []),
      is_active: p.is_active,
    });
    setError(null);
    setShowForm(true);
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Package}
          title="Produits de crédit"
          subtitle="Catalogue par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={Package}
        title="Produits de crédit"
        subtitle={`Produits, conditions et identifiants CBS — ${scopeLabel}`}
        actions={canAddProduct ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => (showForm && !editingId ? setShowForm(false) : openCreate())}
          >
            {showForm && !editingId ? <X /> : <Plus />}
            {showForm && !editingId ? "Fermer" : "Nouveau produit"}
          </button>
        ) : undefined}
      />

      {showForm && (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (editingId ? !canChangeProduct : !canAddProduct) {
              setError("Vous n'avez pas le droit d'enregistrer ce produit.");
              return;
            }
            saveProd.mutate();
          }}
        >
          <div className="tenant-compose-head">
            <h2>{editingId ? "Modifier le produit" : "Nouveau produit"}</h2>
            <p className="muted">
              Les bornes montant / durée et le type de client sont contrôlés à
              la soumission du dossier (selon la politique filiale).
            </p>
          </div>

          <FormBlock
            icon={Package}
            title="Identité"
            description="Code unique, libellé et clientèle cible."
          >
            <div className="form-grid two-col">
              <label className="field">
                <span>Code *</span>
                <input
                  value={prod.code}
                  onChange={(e) => setProd({ ...prod, code: e.target.value })}
                  required
                  readOnly={Boolean(editingId)}
                />
              </label>
              <label className="field">
                <span>Libellé *</span>
                <input
                  value={prod.label}
                  onChange={(e) => setProd({ ...prod, label: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Type de client</span>
                <select
                  value={prod.client_type}
                  onChange={(e) =>
                    setProd({ ...prod, client_type: e.target.value })
                  }
                >
                  {CLIENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field full-span">
                <span>Description</span>
                <input
                  value={prod.description}
                  onChange={(e) =>
                    setProd({ ...prod, description: e.target.value })
                  }
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={prod.requires_guarantee}
                  onChange={(e) =>
                    setProd({ ...prod, requires_guarantee: e.target.checked })
                  }
                />
                <span>Garantie ou caution obligatoire</span>
              </label>
              {editingId && (
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={prod.is_active}
                    onChange={(e) =>
                      setProd({ ...prod, is_active: e.target.checked })
                    }
                  />
                  <span>Produit actif</span>
                </label>
              )}
            </div>
          </FormBlock>

          <FormBlock
            icon={Percent}
            title="Bornes et tarification"
            description="Montant, durée et taux proposés par défaut."
          >
            <div className="form-grid two-col">
              <label className="field">
                <span>Montant min</span>
                <input
                  type="number"
                  value={prod.amount_min}
                  onChange={(e) =>
                    setProd({ ...prod, amount_min: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Montant max</span>
                <input
                  type="number"
                  value={prod.amount_max}
                  onChange={(e) =>
                    setProd({ ...prod, amount_max: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Durée min (mois)</span>
                <input
                  type="number"
                  value={prod.duration_min_months}
                  onChange={(e) =>
                    setProd({
                      ...prod,
                      duration_min_months: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label className="field">
                <span>Durée max (mois)</span>
                <input
                  type="number"
                  value={prod.duration_max_months}
                  onChange={(e) =>
                    setProd({
                      ...prod,
                      duration_max_months: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label className="field">
                <span>Taux annuel (%)</span>
                <input
                  type="number"
                  step="0.001"
                  value={prod.interest_rate}
                  onChange={(e) =>
                    setProd({ ...prod, interest_rate: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Frais de dossier (%)</span>
                <input
                  type="number"
                  step="0.001"
                  value={prod.processing_fee_rate}
                  onChange={(e) =>
                    setProd({ ...prod, processing_fee_rate: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Devise</span>
                <input
                  value={prod.currency}
                  onChange={(e) =>
                    setProd({ ...prod, currency: e.target.value })
                  }
                />
              </label>
            </div>
          </FormBlock>

          <FormBlock
            icon={Layers}
            title="Mapping CBS"
            description="Saisissez l’identifiant fourni par le CBS ; il sera envoyé dans idProduitCrd."
          >
            <label className="field">
              <span>Identifiant produit crédit CBS (idProduitCrd)</span>
              <input
                value={prod.cbs_product_code}
                onChange={(e) =>
                  setProd({ ...prod, cbs_product_code: e.target.value })
                }
                maxLength={64}
                placeholder="Ex. 6"
                autoComplete="off"
              />
            </label>
            <p className="muted small">Aucun catalogue CBS n’est disponible pour importer ces identifiants. Renseignez ici le code exact communiqué par l’équipe CBS ; il est nécessaire pour une mise en place en mode CBS réel.</p>
            <p>Le code de remboursement provient du mécanisme configuré dans le dossier. Aucun objet de financement n’est utilisé comme produit crédit par défaut.</p>
          </FormBlock>

          {error && <div className="form-error">{error}</div>}
          <div className="tenant-compose-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setShowForm(false);
                setEditingId(null);
                setProd({ ...EMPTY_PROD });
                setError(null);
              }}
            >
              Annuler
            </button>
            <button
              className="btn btn-primary"
              disabled={saveProd.isPending || (editingId ? !canChangeProduct : !canAddProduct)}
            >
              <Save size={16} />
              {saveProd.isPending
                ? "Enregistrement…"
                : editingId
                  ? "Enregistrer"
                  : "Créer le produit"}
            </button>
          </div>
        </form>
      )}

      <ListFilters
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Code, libellé…"
          />
        }
        activeCount={countActive(
          search,
          clientTypeFilter,
          showInactive,
        )}
        onReset={() => {
          setSearch("");
          setClientTypeFilter("");
          setShowInactive(false);
        }}
        extra={
          <FilterToggle
            label="Inclure les inactifs"
            checked={showInactive}
            onChange={setShowInactive}
          />
        }
      >
        <FilterField label="Clientèle" active={!!clientTypeFilter}>
          <FilterSelect value={clientTypeFilter} onChange={setClientTypeFilter}>
            <option value="">Tous types</option>
            {CLIENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
      </ListFilters>

      <QueryStatus
        isLoading={products.isLoading}
        isError={products.isError}
        isEmpty={!products.data?.results.length}
        emptyMessage="Aucun produit pour ce filtre."
        onRetry={() => products.refetch()}
      >
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Produit</th>
                <th>Clientèle</th>
                <th className="num">Montant</th>
                <th>Durée</th>
                <th className="num">Taux</th>
                <th>CBS</th>
                <th>Statut</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(products.data?.results ?? []).map((p) => (
                <tr
                  key={p.id}
                className={canChangeProduct ? "row-clickable" : undefined}
                onClick={canChangeProduct ? () => openEdit(p) : undefined}
                >
                  <td>
                    <strong>{p.label}</strong>
                    <div className="muted small">
                      <code>{p.code}</code>
                      {p.requires_guarantee ? " · garantie exigée" : ""}
                    </div>
                  </td>
                  <td>{clientTypeLabel(p.client_type)}</td>
                  <td className="num">
                    {formatMoney(p.amount_min, p.currency)}
                    <div className="muted small">
                      → {formatMoney(p.amount_max, p.currency)}
                    </div>
                  </td>
                  <td className="muted small">
                    {p.duration_min_months ?? "—"}–{p.duration_max_months ?? "—"}{" "}
                    mois
                  </td>
                  <td className="num">{p.interest_rate} %</td>
                  <td className="muted small">
                    {creditCbsCode(p, cbsProducts.data ?? []) || "À configurer"}
                  </td>
                  <td>
                    <Badge
                      value={p.is_active ? "ACTIVE" : "DRAFT"}
                      label={p.is_active ? "Actif" : "Inactif"}
                    />
                  </td>
                  <td>
                    <div
                      className="row-actions"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {canChangeProduct && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => openEdit(p)}
                        >
                          Modifier
                        </button>
                      )}
                      {canChangeProduct && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={toggleActive.isPending}
                          onClick={() => toggleActive.mutate(p)}
                        >
                          {p.is_active ? "Désactiver" : "Activer"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryStatus>
    </div>
  );
}
