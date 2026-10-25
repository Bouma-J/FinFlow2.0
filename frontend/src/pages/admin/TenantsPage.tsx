import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Image,
  MapPin,
  Palette,
  Plus,
  Save,
  Trash2,
  Users,
  X,
} from "lucide-react";
import {
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";

import { api } from "@/api/client";
import type { Agency, Paginated, Tenant, TenantOfficer } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  FilterField,
  FilterSelect,
  ListFilters,
  SearchInput,
  countActive,
} from "@/components/ListFilters";
import {
  Badge,
  Card,
  PageHeader,
  QueryStatus,
  Spinner,
} from "@/components/ui";

type OfficerDraft = {
  title: string;
  last_name: string;
  first_name: string;
  phone: string;
};

const EMPTY_OFFICER: OfficerDraft = {
  title: "",
  last_name: "",
  first_name: "",
  phone: "",
};

const EMPTY_TENANT = {
  code: "",
  name: "",
  country: "",
  zone: "",
  currency: "XOF",
  timezone: "UTC",
  address: "",
  phone: "",
  email: "",
  is_active: true,
  brand_primary: "#0f9488",
  brand_accent: "#d4a017",
  brand_sidebar: "#084f4a",
  brand_sidebar_text: "#ffffff",
};

const EMPTY_AGENCY = {
  code: "",
  name: "",
  region: "",
  address: "",
  manager_last_name: "",
  manager_first_name: "",
  manager_phone: "",
};

function fromOfficers(items?: TenantOfficer[]): OfficerDraft[] {
  if (!items?.length) return [];
  return items.map((o) => ({
    title: o.title ?? "",
    last_name: o.last_name ?? "",
    first_name: o.first_name ?? "",
    phone: o.phone ?? "",
  }));
}

function cleanOfficers(items: OfficerDraft[]) {
  return items
    .map((o) => ({
      title: o.title.trim(),
      last_name: o.last_name.trim(),
      first_name: o.first_name.trim(),
      phone: o.phone.trim(),
    }))
    .filter((o) => o.title || o.last_name || o.first_name || o.phone);
}

function FormBlock({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: typeof Building2;
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

export function AdminTenantsPage() {
  const qc = useQueryClient();
  const { user, setActiveTenant } = useAuth();
  const canManageTenants = Boolean(
    user?.is_superuser || (user?.is_group_level && user?.is_staff),
  );
  const canViewAgencies = hasPerm(user, "tenants.view_agency");
  const canCreateAgencies = hasPerm(user, "tenants.add_agency");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_TENANT });
  const [officers, setOfficers] = useState<OfficerDraft[]>([]);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [agencyForm, setAgencyForm] = useState({ ...EMPTY_AGENCY });
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () =>
      (await api.get<Paginated<Tenant>>("/tenants/", { params: { page_size: 200 } }))
        .data,
    enabled: !!user?.is_group_level,
  });

  const allTenants = tenants.data?.results ?? [];
  const countries = [...new Set(allTenants.map((t) => t.country).filter(Boolean))].sort();
  const filteredTenants = allTenants.filter((t) => {
    const q = search.trim().toLowerCase();
    if (
      q &&
      !`${t.code} ${t.name} ${t.country} ${t.zone}`.toLowerCase().includes(q)
    ) {
      return false;
    }
    if (countryFilter && t.country !== countryFilter) return false;
    if (statusFilter === "active" && !t.is_active) return false;
    if (statusFilter === "inactive" && t.is_active) return false;
    return true;
  });

  const selected = allTenants.find((t) => t.id === selectedId);

  const agencies = useQuery({
    queryKey: ["agencies", selectedId],
    queryFn: async () =>
      (
        await api.get<Paginated<Agency>>("/agencies/", {
          params: { tenant: selectedId },
          headers: { "X-Tenant-Id": selectedId! },
        })
      ).data,
    enabled: !!selectedId && canViewAgencies,
  });

  const createTenant = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      Object.entries(form).forEach(([k, v]) => {
        if (typeof v === "boolean") fd.append(k, v ? "true" : "false");
        else if (v !== "") fd.append(k, String(v));
      });
      if (logoFile) fd.append("logo", logoFile);
      fd.append("officers", JSON.stringify(cleanOfficers(officers)));
      return (await api.post("/tenants/", fd)).data;
    },
    onSuccess: (created: Tenant) => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      setShowForm(false);
      setForm({ ...EMPTY_TENANT });
      setOfficers([]);
      setLogoFile(null);
      setError(null);
      setSelectedId(created.id);
      setActiveTenant(created.id);
    },
    onError: () =>
      setError(
        "Création impossible. Vérifiez le code (unique) et les champs requis.",
      ),
  });

  const updateTenant = useMutation({
    mutationFn: async ({
      id,
      data,
      logo,
      officerList,
    }: {
      id: string;
      data: typeof form;
      logo: File | null;
      officerList: OfficerDraft[];
    }) => {
      const fd = new FormData();
      Object.entries(data).forEach(([k, v]) => {
        if (typeof v === "boolean") fd.append(k, v ? "true" : "false");
        else if (v !== "") fd.append(k, String(v));
      });
      if (logo) fd.append("logo", logo);
      fd.append("officers", JSON.stringify(cleanOfficers(officerList)));
      return (await api.patch(`/tenants/${id}/`, fd)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      qc.invalidateQueries({ queryKey: ["tenant-branding"] });
      qc.invalidateQueries({ queryKey: ["public-tenant-branding"] });
      setError(null);
    },
    onError: () => setError("Mise à jour impossible."),
  });

  const createAgency = useMutation({
    mutationFn: async () =>
      (
        await api.post(
          "/agencies/",
          { ...agencyForm, tenant: selectedId },
          { headers: { "X-Tenant-Id": selectedId! } },
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agencies", selectedId] });
      setAgencyForm({ ...EMPTY_AGENCY });
    },
  });

  if (!user?.is_group_level) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Building2}
          title="Filiales"
          subtitle="Réservé aux administrateurs Groupe"
        />
        <p className="muted">
          Vous n&apos;avez pas accès à la gestion des filiales.
        </p>
      </div>
    );
  }

  function openEdit(t: Tenant) {
    setSelectedId(t.id);
    setForm({
      code: t.code,
      name: t.name,
      country: t.country,
      zone: t.zone,
      currency: t.currency,
      timezone: t.timezone,
      address: t.address ?? "",
      phone: t.phone ?? "",
      email: t.email ?? "",
      is_active: t.is_active,
      brand_primary: t.brand_primary,
      brand_accent: t.brand_accent,
      brand_sidebar: t.brand_sidebar,
      brand_sidebar_text: t.brand_sidebar_text,
    });
    setOfficers(fromOfficers(t.officers));
    setLogoFile(null);
    setShowForm(false);
    setError(null);
  }

  function resetCreateForm() {
    setForm({ ...EMPTY_TENANT });
    setOfficers([]);
    setLogoFile(null);
    setError(null);
  }

  return (
    <div className="page-shell tenants-admin-page">
      <PageHeader
        icon={Building2}
        title="Filiales"
        subtitle="Création, configuration, logo, couleurs, responsables et agences"
        actions={canManageTenants ? (
          <button
            className="btn btn-primary"
            type="button"
            onClick={() => {
              setShowForm((s) => !s);
              if (!showForm) resetCreateForm();
            }}
          >
            {showForm ? <X /> : <Plus />}
            {showForm ? "Fermer" : "Nouvelle filiale"}
          </button>
        ) : undefined}
      />

      {showForm && canManageTenants && (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            createTenant.mutate();
          }}
        >
          <div className="tenant-compose-head">
            <h2>Nouvelle filiale</h2>
            <p className="muted">
              Renseignez l&apos;identité, la charte graphique et les
              responsables avant de créer la filiale.
            </p>
          </div>
          <TenantFields
            form={form}
            setForm={setForm}
            logoFile={logoFile}
            setLogoFile={setLogoFile}
          />
          <OfficersEditor officers={officers} setOfficers={setOfficers} />
          {error && <div className="form-error">{error}</div>}
          <div className="tenant-compose-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setShowForm(false);
                resetCreateForm();
              }}
            >
              Annuler
            </button>
            <button
              className="btn btn-primary"
              disabled={createTenant.isPending}
            >
              <Plus size={16} />
              {createTenant.isPending ? "Création…" : "Créer la filiale"}
            </button>
          </div>
        </form>
      )}

      <ListFilters
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Code, raison sociale, pays…"
          />
        }
        activeCount={countActive(search, countryFilter, statusFilter)}
        onReset={() => {
          setSearch("");
          setCountryFilter("");
          setStatusFilter("");
        }}
      >
        <FilterField label="Pays" active={!!countryFilter}>
          <FilterSelect value={countryFilter} onChange={setCountryFilter}>
            <option value="">Tous</option>
            {countries.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
        <FilterField label="Statut" active={!!statusFilter}>
          <FilterSelect value={statusFilter} onChange={setStatusFilter}>
            <option value="">Tous</option>
            <option value="active">Actives</option>
            <option value="inactive">Inactives</option>
          </FilterSelect>
        </FilterField>
      </ListFilters>

      <div className="tenants-admin-layout">
        <Card title="Filiales">
          <QueryStatus
            isLoading={tenants.isLoading}
            isError={tenants.isError}
            isEmpty={!filteredTenants.length}
            emptyMessage="Aucune filiale pour ce filtre."
            onRetry={() => tenants.refetch()}
          >
            <ul className="tenant-pick-list">
              {filteredTenants.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    className={`tenant-pick${selectedId === t.id ? " is-selected" : ""}`}
                    onClick={() => openEdit(t)}
                  >
                    <span
                      className="tenant-pick-swatches"
                      aria-hidden
                    >
                      <i style={{ background: t.brand_primary }} />
                      <i style={{ background: t.brand_accent }} />
                      <i style={{ background: t.brand_sidebar }} />
                      <i style={{ background: t.brand_sidebar_text }} />
                    </span>
                    <span className="tenant-pick-body">
                      <strong>
                        {t.code} — {t.name}
                      </strong>
                      <span className="muted small">
                        {t.country}
                        {t.zone ? ` · ${t.zone}` : ""} · {t.currency}
                      </span>
                    </span>
                    <Badge
                      value={t.is_active ? "ACTIVE" : "DRAFT"}
                      label={t.is_active ? "Active" : "Inactive"}
                    />
                  </button>
                </li>
              ))}
            </ul>
          </QueryStatus>
        </Card>

        <Card
          title={
            selected ? `Configuration — ${selected.code}` : "Configuration"
          }
        >
          {!selected ? (
            <p className="muted">Sélectionnez une filiale à configurer.</p>
          ) : (
            <div className="tenant-config-stack">
              {selected.logo_url && (
                <div className="tenant-logo-preview">
                  <img src={selected.logo_url} alt="Logo filiale" />
                </div>
              )}
              {canManageTenants ? (
                <form
                  className="tenant-compose-form embedded"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    updateTenant.mutate({
                      id: selected.id,
                      data: form,
                      logo: logoFile,
                      officerList: officers,
                    });
                  }}
                >
                  <TenantFields
                    form={form}
                    setForm={setForm}
                    logoFile={logoFile}
                    setLogoFile={setLogoFile}
                    codeReadOnly
                  />
                  <OfficersEditor officers={officers} setOfficers={setOfficers} />
                  {error && <div className="form-error">{error}</div>}
                  <div className="tenant-compose-actions">
                    <button
                      className="btn btn-primary"
                      disabled={updateTenant.isPending}
                    >
                      <Save size={16} />
                      {updateTenant.isPending
                        ? "Enregistrement…"
                        : "Enregistrer la filiale"}
                    </button>
                  </div>
                </form>
              ) : (
                <p className="muted">
                  La modification des filiales est réservée aux administrateurs Groupe.
                </p>
              )}

              <section className="tenant-form-block">
                <header className="tenant-form-block-head">
                  <span className="tenant-form-block-icon">
                    <MapPin size={17} />
                  </span>
                  <div>
                    <h3 className="tenant-form-block-title">Agences</h3>
                    <p className="tenant-form-block-desc">
                      Points de vente rattachés à cette filiale.
                    </p>
                  </div>
                </header>
                <div className="tenant-form-block-body">
                  {canViewAgencies && agencies.isLoading ? (
                    <Spinner />
                  ) : canViewAgencies ? (
                    <ul className="tenant-agency-list">
                      {(agencies.data?.results ?? []).map((a) => (
                        <li key={a.id}>
                          <strong>
                            {a.code} — {a.name}
                          </strong>
                          {a.region && (
                            <span className="muted small"> ({a.region})</span>
                          )}
                          {(a.manager_last_name || a.manager_first_name) && (
                            <div className="muted small">
                              Chef :{" "}
                              {`${a.manager_first_name} ${a.manager_last_name}`.trim()}
                              {a.manager_phone ? ` · ${a.manager_phone}` : ""}
                            </div>
                          )}
                        </li>
                      ))}
                      {(agencies.data?.results.length ?? 0) === 0 && (
                        <li className="muted">Aucune agence.</li>
                      )}
                    </ul>
                  ) : (
                    <p className="muted">La consultation des agences n’est pas autorisée.</p>
                  )}

                  {canCreateAgencies && <form
                    className="tenant-agency-form"
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      createAgency.mutate();
                    }}
                  >
                    <p className="tenant-form-subtitle">Ajouter une agence</p>
                    <div className="form-grid two-col">
                      <label className="field">
                        <span>Code agence *</span>
                        <input
                          value={agencyForm.code}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              code: e.target.value,
                            })
                          }
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Nom agence *</span>
                        <input
                          value={agencyForm.name}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              name: e.target.value,
                            })
                          }
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Région</span>
                        <input
                          value={agencyForm.region}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              region: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Adresse</span>
                        <input
                          value={agencyForm.address}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              address: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Nom du chef d&apos;agence</span>
                        <input
                          value={agencyForm.manager_last_name}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              manager_last_name: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Prénom du chef d&apos;agence</span>
                        <input
                          value={agencyForm.manager_first_name}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              manager_first_name: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Téléphone du chef d&apos;agence</span>
                        <input
                          value={agencyForm.manager_phone}
                          onChange={(e) =>
                            setAgencyForm({
                              ...agencyForm,
                              manager_phone: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={createAgency.isPending}
                    >
                      <Plus size={15} />
                      Ajouter l&apos;agence
                    </button>
                  </form>}
                </div>
              </section>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function OfficersEditor({
  officers,
  setOfficers,
}: {
  officers: OfficerDraft[];
  setOfficers: (
    items: OfficerDraft[] | ((prev: OfficerDraft[]) => OfficerDraft[]),
  ) => void;
}) {
  const update = (idx: number, patch: Partial<OfficerDraft>) =>
    setOfficers((arr) =>
      arr.map((item, i) => (i === idx ? { ...item, ...patch } : item)),
    );

  return (
    <FormBlock
      icon={Users}
      title="Responsables"
      description="DG, directeur d'exploitation, ou autres postes clés (optionnel)."
    >
      {officers.length === 0 && (
        <p className="muted small" style={{ marginTop: 0 }}>
          Aucun responsable saisi pour le moment.
        </p>
      )}
      <div className="officer-list">
        {officers.map((o, idx) => (
          <div key={idx} className="officer-row">
            <input
              placeholder="Intitulé du poste *"
              value={o.title}
              onChange={(e) => update(idx, { title: e.target.value })}
              aria-label="Intitulé du poste"
            />
            <input
              placeholder="Nom *"
              value={o.last_name}
              onChange={(e) => update(idx, { last_name: e.target.value })}
              aria-label="Nom"
            />
            <input
              placeholder="Prénom"
              value={o.first_name}
              onChange={(e) => update(idx, { first_name: e.target.value })}
              aria-label="Prénom"
            />
            <input
              placeholder="Téléphone"
              value={o.phone}
              onChange={(e) => update(idx, { phone: e.target.value })}
              aria-label="Téléphone"
            />
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() =>
                setOfficers((arr) => arr.filter((_, i) => i !== idx))
              }
              title="Retirer"
              aria-label="Retirer"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => setOfficers((arr) => [...arr, { ...EMPTY_OFFICER }])}
      >
        <Plus size={14} />
        Ajouter un responsable
      </button>
    </FormBlock>
  );
}

function TenantFields({
  form,
  setForm,
  logoFile,
  setLogoFile,
  codeReadOnly,
}: {
  form: typeof EMPTY_TENANT;
  setForm: (f: typeof EMPTY_TENANT) => void;
  logoFile: File | null;
  setLogoFile: (f: File | null) => void;
  codeReadOnly?: boolean;
}) {
  return (
    <div className="tenant-fields">
      <FormBlock
        icon={Building2}
        title="Identité"
        description="Code unique, raison sociale et localisation."
      >
        <div className="form-grid two-col">
          <label className="field">
            <span>Code filiale *</span>
            <input
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              required
              readOnly={codeReadOnly}
            />
          </label>
          <label className="field">
            <span>Raison sociale *</span>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <label className="field">
            <span>Pays *</span>
            <input
              value={form.country}
              onChange={(e) => setForm({ ...form, country: e.target.value })}
              required
            />
          </label>
          <label className="field">
            <span>Zone / région</span>
            <input
              value={form.zone}
              onChange={(e) => setForm({ ...form, zone: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Devise</span>
            <input
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Fuseau horaire</span>
            <input
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value })}
            />
          </label>
          <label className="field checkbox tenant-active-field">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) =>
                setForm({ ...form, is_active: e.target.checked })
              }
            />
            <span>Filiale active</span>
          </label>
        </div>
      </FormBlock>

      <FormBlock
        icon={MapPin}
        title="Coordonnées"
        description="Adresse et contacts de la filiale."
      >
        <div className="form-grid two-col">
          <label className="field full-span">
            <span>Adresse</span>
            <input
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Téléphone</span>
            <input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </label>
        </div>
      </FormBlock>

      <FormBlock
        icon={Palette}
        title="Charte graphique"
        description="Logo et couleurs appliquées à toute l'interface de la filiale."
      >
        <div className="tenant-brand-layout">
          <div className="form-grid two-col tenant-brand-fields">
            <label className="field full-span">
              <span>
                <Image size={14} style={{ verticalAlign: "-2px" }} /> Logo
              </span>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
              />
              {logoFile && (
                <span className="muted small">{logoFile.name}</span>
              )}
            </label>
            {([
              ["brand_primary", "Couleur principale"],
              ["brand_accent", "Couleur accent"],
              ["brand_sidebar", "Couleur barre latérale"],
              ["brand_sidebar_text", "Couleur texte de la barre"],
            ] as const).map(([key, label]) => <label className="field color-field" key={key}>
              <span>{label}</span>
              <input type="color" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
              <input value={form[key]} readOnly className="color-hex" aria-label={`${label} — code hexadécimal`} />
            </label>)}
          </div>
          <aside
            className="tenant-brand-preview"
            style={
              {
                "--preview-primary": form.brand_primary,
                "--preview-accent": form.brand_accent,
                "--preview-sidebar": form.brand_sidebar,
                "--preview-sidebar-text": form.brand_sidebar_text,
              } as CSSProperties
            }
          >
            <div className="tenant-brand-preview-bar" />
            <div className="tenant-brand-preview-body">
              <strong>{form.name || "Aperçu filiale"}</strong>
              <span className="muted small">
                {form.code || "CODE"} · {form.country || "Pays"}
              </span>
              <div className="tenant-brand-preview-menu">
                <span>Menu latéral</span>
                <span>Tableau de bord</span>
                <span className="tenant-brand-preview-active">Dossiers de crédit</span>
              </div>
              <div className="tenant-brand-preview-swatches">
                <span style={{ background: form.brand_primary }} title="Principale" />
                <span style={{ background: form.brand_accent }} title="Accent" />
                <span style={{ background: form.brand_sidebar }} title="Barre latérale" />
                <span style={{ background: form.brand_sidebar_text }} title="Texte de la barre" />
              </div>
            </div>
          </aside>
        </div>
      </FormBlock>
    </div>
  );
}
