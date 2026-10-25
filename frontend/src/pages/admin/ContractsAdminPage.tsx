import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  FileSignature,
  Plus,
  Power,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/api/client";
import type {
  ContractExtraField,
  ContractTemplate,
  CreditProduct,
  Paginated,
  VariableCatalog,
} from "@/api/types";
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
  Card,
  PageHeader,
  QueryStatus,
  TenantScopeNotice,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const CATEGORIES: [string, string][] = [
  ["NOTIFICATION", "Notification de crédit"],
  ["LOAN", "Contrat de prêt"],
  ["SURETY", "Cautionnement"],
  ["PLEDGE_VEHICLE", "Gage véhicule"],
  ["PLEDGE_JEWELRY", "Gage bijoux"],
  ["PLEDGE_SHARES", "Nantissement d'actions"],
  ["SALARY_ASSIGNMENT", "Cession sur salaire"],
  ["PROMISSORY_NOTE", "Billet à ordre"],
  ["FIDUCIARY_TRANSFER", "Transfert fiduciaire"],
  ["OTHER", "Autre"],
];

const APPLIES_TO: [string, string][] = [
  ["ANY", "Tous les clients"],
  ["INDIVIDUAL", "Particuliers uniquement"],
  ["CORPORATE", "Entreprises et groupements"],
];

const emptyForm = {
  name: "",
  category: "OTHER",
  applies_to: "ANY",
  product: "",
  amount_min: "",
  amount_max: "",
  is_required: false,
  description: "",
};

function FormBlock({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: typeof FileSignature;
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

export function AdminContractsPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canAdd = hasPerm(user, "contracts.add_contracttemplate");
  const canChange = hasPerm(user, "contracts.change_contracttemplate");
  const canDelete = hasPerm(user, "contracts.delete_contracttemplate");

  const [form, setForm] = useState({ ...emptyForm });
  const [file, setFile] = useState<File | null>(null);
  const [extras, setExtras] = useState<ContractExtraField[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showVars, setShowVars] = useState(false);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [appliesFilter, setAppliesFilter] = useState("");
  const [requiredOnly, setRequiredOnly] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  const templates = useQuery({
    queryKey: [
      "contract-templates",
      activeTenant,
      search,
      categoryFilter,
      appliesFilter,
      requiredOnly,
      showInactive,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<ContractTemplate>>("/contract-templates/", {
          params: {
            page_size: 200,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(categoryFilter ? { category: categoryFilter } : {}),
            ...(appliesFilter ? { applies_to: appliesFilter } : {}),
            ...(requiredOnly ? { is_required: true } : {}),
            ...(showInactive ? {} : { is_active: true }),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  const products = useQuery({
    queryKey: ["credit-products", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditProduct>>("/credit-products/", {
          params: { page_size: 200, is_active: true },
        })
      ).data,
    enabled: !needsTenant && canAdd,
  });

  const variables = useQuery({
    queryKey: ["contract-variables"],
    queryFn: async () =>
      (await api.get<VariableCatalog>("/contract-templates/variables/")).data,
    enabled: !needsTenant,
  });

  const create = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("name", form.name);
      fd.append("category", form.category);
      fd.append("applies_to", form.applies_to);
      if (form.product) fd.append("product", form.product);
      if (form.amount_min) fd.append("amount_min", form.amount_min);
      if (form.amount_max) fd.append("amount_max", form.amount_max);
      fd.append("is_required", String(form.is_required));
      fd.append("description", form.description);
      fd.append("extra_fields", JSON.stringify(extras));
      if (file) fd.append("file", file);
      return (
        await api.post("/contract-templates/", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      ).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract-templates"] });
      setForm({ ...emptyForm });
      setFile(null);
      setExtras([]);
      setError(null);
      setShowForm(false);
    },
    onError: (e) =>
      setError(
        apiErrorMessage(
          e,
          "Création impossible. Vérifiez les champs et le fichier (.docx/.xlsx).",
        ),
      ),
  });

  const toggleActive = useMutation({
    mutationFn: async (t: ContractTemplate) =>
      (
        await api.patch(`/contract-templates/${t.id}/`, {
          is_active: !t.is_active,
        })
      ).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contract-templates"] }),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/contract-templates/${id}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contract-templates"] }),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!canAdd) return;
    if (!file) {
      setError("Veuillez joindre le modèle (.docx ou .xlsx).");
      return;
    }
    if (!form.name.trim()) {
      setError("L'intitulé du contrat est obligatoire.");
      return;
    }
    create.mutate();
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={FileSignature}
          title="Modèles de contrats"
          subtitle="Catalogue par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={FileSignature}
        title="Modèles de contrats"
        subtitle="Chaque filiale gère ses actes, variables et obligations avant mise en place."
        actions={
          canAdd ? <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setShowForm((s) => !s);
              setError(null);
            }}
          >
            {showForm ? <X /> : <Plus />}
            {showForm ? "Fermer" : "Nouveau modèle"}
          </button>
            : undefined
        }
      />

      {showForm && canAdd && (
        <form className="tenant-compose-form" onSubmit={submit}>
          <div className="tenant-compose-head">
            <h2>Nouveau modèle</h2>
            <p className="muted">
              Joignez un fichier Word ou Excel avec des balises{" "}
              <code>{"{{ variable }}"}</code>.
            </p>
          </div>

          <FormBlock
            icon={FileSignature}
            title="Identité"
            description="Intitulé, catégorie et clientèle visée."
          >
            <div className="form-grid two-col">
              <label className="field full-span">
                <span>Intitulé *</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex. Contrat de cautionnement solidaire"
                  required
                />
              </label>
              <label className="field">
                <span>Catégorie</span>
                <select
                  value={form.category}
                  onChange={(e) =>
                    setForm({ ...form, category: e.target.value })
                  }
                >
                  {CATEGORIES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>S&apos;applique à</span>
                <select
                  value={form.applies_to}
                  onChange={(e) =>
                    setForm({ ...form, applies_to: e.target.value })
                  }
                >
                  {APPLIES_TO.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Produit (optionnel)</span>
                <select
                  value={form.product}
                  onChange={(e) =>
                    setForm({ ...form, product: e.target.value })
                  }
                >
                  <option value="">— tous les produits —</option>
                  {products.data?.results.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Fichier modèle *</span>
                <input
                  type="file"
                  accept=".docx,.xlsx"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                {file && <span className="muted small">{file.name}</span>}
              </label>
              <label className="field full-span">
                <span>Description</span>
                <input
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </label>
            </div>
          </FormBlock>

          <FormBlock
            icon={SlidersHorizontal}
            title="Règles d’application"
            description="Bornes de montant et obligation avant mise en place."
          >
            <div className="form-grid two-col">
              <label className="field">
                <span>Montant min</span>
                <input
                  type="number"
                  value={form.amount_min}
                  onChange={(e) =>
                    setForm({ ...form, amount_min: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Montant max</span>
                <input
                  type="number"
                  value={form.amount_max}
                  onChange={(e) =>
                    setForm({ ...form, amount_max: e.target.value })
                  }
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.is_required}
                  onChange={(e) =>
                    setForm({ ...form, is_required: e.target.checked })
                  }
                />
                <span>Obligatoire avant mise en place</span>
              </label>
            </div>
          </FormBlock>

          <FormBlock
            icon={Plus}
            title="Variables manuelles"
            description="Champs saisis à la génération, en plus du catalogue."
          >
            {extras.map((f, idx) => (
              <div key={idx} className="extra-field-row">
                <input
                  placeholder="clé (ex. temoin_nom)"
                  value={f.key}
                  onChange={(e) =>
                    setExtras((arr) =>
                      arr.map((x, i) =>
                        i === idx ? { ...x, key: e.target.value } : x,
                      ),
                    )
                  }
                />
                <input
                  placeholder="libellé"
                  value={f.label}
                  onChange={(e) =>
                    setExtras((arr) =>
                      arr.map((x, i) =>
                        i === idx ? { ...x, label: e.target.value } : x,
                      ),
                    )
                  }
                />
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() =>
                    setExtras((arr) => arr.filter((_, i) => i !== idx))
                  }
                >
                  <X size={14} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() =>
                setExtras((arr) => [
                  ...arr,
                  { key: "", label: "", type: "text" },
                ])
              }
            >
              <Plus size={14} />
              Ajouter une variable
            </button>
          </FormBlock>

          {error && <div className="form-error">{error}</div>}
          <div className="tenant-compose-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setShowForm(false);
                setError(null);
              }}
            >
              Annuler
            </button>
            <button className="btn btn-primary" disabled={create.isPending}>
              <Plus size={15} />
              {create.isPending ? "Ajout…" : "Ajouter le modèle"}
            </button>
          </div>
        </form>
      )}

      <Card title="Catalogue des variables">
        <p className="muted small" style={{ marginTop: 0 }}>
          Insérez ces balises dans vos modèles Word/Excel (ex.{" "}
          <code>{"{{ montant_accorde }}"}</code>).
        </p>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setShowVars((v) => !v)}
        >
          <BookOpen size={14} />
          {showVars ? "Masquer les variables" : "Afficher les variables"}
        </button>
        {variables.data?.loop_help && showVars && (
          <div className="callout callout-info" style={{ marginTop: 12 }}>
            <strong>Tableaux & listes : </strong>
            {variables.data.loop_help}
          </div>
        )}
        {showVars &&
          variables.data?.groups.map((grp) => (
            <div key={grp.group} style={{ marginTop: 12 }}>
              <strong className="small">{grp.group}</strong>
              <div className="var-catalog">
                {grp.items.map(([key, label]) => (
                  <span key={key} className="chip chip-muted" title={label}>
                    <code>{`{{ ${key} }}`}</code>
                  </span>
                ))}
              </div>
            </div>
          ))}
      </Card>

      <ListFilters
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Intitulé, code, description…"
          />
        }
        activeCount={countActive(
          search,
          categoryFilter,
          appliesFilter,
          requiredOnly,
          showInactive,
        )}
        onReset={() => {
          setSearch("");
          setCategoryFilter("");
          setAppliesFilter("");
          setRequiredOnly(false);
          setShowInactive(false);
        }}
        extra={
          <>
            <FilterToggle
              label="Obligatoires seulement"
              checked={requiredOnly}
              onChange={setRequiredOnly}
            />
            <FilterToggle
              label="Inclure les inactifs"
              checked={showInactive}
              onChange={setShowInactive}
            />
          </>
        }
      >
        <FilterField label="Catégorie" active={!!categoryFilter}>
          <FilterSelect value={categoryFilter} onChange={setCategoryFilter}>
            <option value="">Toutes</option>
            {CATEGORIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
        <FilterField label="Cible" active={!!appliesFilter}>
          <FilterSelect value={appliesFilter} onChange={setAppliesFilter}>
            <option value="">Toutes</option>
            {APPLIES_TO.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
      </ListFilters>

      <QueryStatus
        isLoading={templates.isLoading}
        isError={templates.isError}
        isEmpty={!templates.data?.results.length}
        emptyMessage="Aucun modèle pour ce filtre."
        onRetry={() => templates.refetch()}
      >
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Intitulé</th>
                <th>Catégorie</th>
                <th>Cible</th>
                <th>Produit</th>
                <th>Obligatoire</th>
                <th>Statut</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(templates.data?.results ?? []).map((t) => (
                <tr
                  key={t.id}
                  className={t.file ? "row-clickable" : undefined}
                  onClick={
                    t.file
                      ? () =>
                          window.open(t.file!, "_blank", "noopener,noreferrer")
                      : undefined
                  }
                >
                  <td>
                    <strong>{t.name}</strong>
                    {t.engine && (
                      <div className="muted small">{t.engine}</div>
                    )}
                  </td>
                  <td>{t.category_display}</td>
                  <td>{t.applies_to_display}</td>
                  <td>{t.product_label || "Tous"}</td>
                  <td>
                    {t.is_required ? (
                      <Badge value="WARN" label="Oui" />
                    ) : (
                      <span className="muted small">Non</span>
                    )}
                  </td>
                  <td>
                    <Badge
                      value={t.is_active ? "ACTIVE" : "DRAFT"}
                      label={t.is_active ? "Actif" : "Inactif"}
                    />
                  </td>
                  <td>
                    <div
                      className="row-actions"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t.file && (
                        <a
                          className="btn btn-ghost btn-sm"
                          href={t.file}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Modèle
                        </a>
                      )}
                      {canChange && <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => toggleActive.mutate(t)}
                        disabled={toggleActive.isPending}
                      >
                        <Power size={14} />
                        {t.is_active ? "Désactiver" : "Activer"}
                      </button>}
                      {canDelete && <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Supprimer le modèle « ${t.name} » ? Les contrats déjà générés sont conservés.`,
                            )
                          )
                            remove.mutate(t.id);
                        }}
                        disabled={remove.isPending}
                      >
                        <Trash2 size={14} />
                      </button>}
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
