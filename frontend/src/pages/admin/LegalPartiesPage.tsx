import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, MapPin, Scale, Save, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/api/client";
import type { LegalParty, LegalPartyType, Paginated, Tenant } from "@/api/types";
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
} from "@/components/ui";

const TYPES: { value: LegalPartyType; label: string }[] = [
  { value: "LAW_FIRM", label: "Cabinet d'avocats" },
  { value: "LAWYER", label: "Avocat" },
  { value: "BAILIFF", label: "Huissier" },
  { value: "NOTARY", label: "Notaire" },
  { value: "EXPERT", label: "Expert" },
  { value: "OTHER", label: "Autre" },
];

type FormState = {
  party_type: LegalPartyType;
  name: string;
  phone: string;
  email: string;
  contact_name: string;
  registration_no: string;
  address: string;
  notes: string;
  is_active: boolean;
};

const EMPTY_FORM: FormState = {
  party_type: "LAW_FIRM",
  name: "",
  phone: "",
  email: "",
  contact_name: "",
  registration_no: "",
  address: "",
  notes: "",
  is_active: true,
};

function FormBlock({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: typeof Scale;
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

export function LegalPartiesPage() {
  const { user, activeTenant, setActiveTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canAdd = hasPerm(user, "collections.add_legalparty");
  const canChange = hasPerm(user, "collections.change_legalparty");
  const qc = useQueryClient();

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () => (await api.get<Paginated<Tenant>>("/tenants/")).data,
    enabled: Boolean(user?.is_group_level),
  });

  const list = useQuery({
    queryKey: ["legal-parties", activeTenant, search, typeFilter, showInactive],
    queryFn: async () =>
      (
        await api.get<Paginated<LegalParty>>("/legal-parties/", {
          params: {
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(typeFilter ? { party_type: typeFilter } : {}),
            ...(showInactive ? {} : { is_active: true }),
            ordering: "name",
            page_size: 200,
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  useEffect(() => {
    if (!showForm) setEditingId(null);
  }, [showForm]);

  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        party_type: form.party_type,
        name: form.name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        contact_name: form.contact_name.trim(),
        registration_no: form.registration_no.trim(),
        address: form.address.trim(),
        notes: form.notes.trim(),
        is_active: form.is_active,
      };
      if (editingId) {
        return (
          await api.patch<LegalParty>(`/legal-parties/${editingId}/`, payload)
        ).data;
      }
      return (await api.post<LegalParty>("/legal-parties/", payload)).data;
    },
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setEditingId(null);
      setShowForm(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["legal-parties"] });
    },
    onError: () =>
      setError(
        editingId
          ? "Impossible de mettre à jour l'intervenant."
          : "Impossible d'enregistrer l'intervenant.",
      ),
  });

  const deactivate = useMutation({
    mutationFn: async (id: string) =>
      (await api.patch<LegalParty>(`/legal-parties/${id}/`, { is_active: false }))
        .data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["legal-parties"] }),
  });

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setError(null);
    setShowForm(true);
  }

  function openEdit(p: LegalParty) {
    setEditingId(p.id);
    setForm({
      party_type: p.party_type,
      name: p.name,
      phone: p.phone || "",
      email: p.email || "",
      contact_name: p.contact_name || "",
      registration_no: p.registration_no || "",
      address: p.address || "",
      notes: p.notes || "",
      is_active: p.is_active,
    });
    setError(null);
    setShowForm(true);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Le nom est obligatoire.");
      return;
    }
    save.mutate();
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Scale}
          title="Intervenants juridiques"
          subtitle="Cabinets, avocats, huissiers et autres conseils"
        />
        <TenantScopeNotice />
        <div className="tenant-compose-form" style={{ marginTop: 16 }}>
          <div className="tenant-compose-head">
            <h2>
              <Building2 size={18} style={{ verticalAlign: -3, marginRight: 8 }} />
              Choisir la filiale
            </h2>
            <p>Les intervenants sont propres à chaque filiale.</p>
          </div>
          <label className="field">
            <span>Filiale</span>
            <select
              value={activeTenant ?? ""}
              onChange={(e) => setActiveTenant(e.target.value || null)}
            >
              <option value="">— Sélectionner —</option>
              {tenants.data?.results.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.code} — {t.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={Scale}
        title="Intervenants juridiques"
        subtitle="Référentiel filiale — cabinets, avocats, huissiers, notaires"
        actions={
          canAdd ? (
            <button type="button" className="btn btn-primary" onClick={openCreate}>
              Nouvel intervenant
            </button>
          ) : undefined
        }
      />

      {showForm && (canAdd || (editingId && canChange)) && (
        <form className="tenant-compose-form" onSubmit={submit}>
          <div className="tenant-compose-head">
            <h2>{editingId ? "Modifier l'intervenant" : "Nouvel intervenant"}</h2>
            <p>Coordonnées utilisées dans le contentieux et les saisies.</p>
          </div>
          <FormBlock
            icon={Scale}
            title="Identité"
            description="Type d’intervenant et identification professionnelle."
          >
            <div className="form-grid two-col">
              <label className="field">
                <span>Type</span>
                <select
                  value={form.party_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      party_type: e.target.value as LegalPartyType,
                    })
                  }
                >
                  {TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Nom / raison sociale *</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>N° barreau / agrément</span>
                <input
                  value={form.registration_no}
                  onChange={(e) =>
                    setForm({ ...form, registration_no: e.target.value })
                  }
                />
              </label>
              {editingId && (
                <label className="checkbox tenant-active-field">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) =>
                      setForm({ ...form, is_active: e.target.checked })
                    }
                  />
                  <span>Actif</span>
                </label>
              )}
            </div>
          </FormBlock>
          <FormBlock
            icon={UserRound}
            title="Coordonnées"
            description="Contact utilisé dans le contentieux et les saisies."
          >
            <div className="form-grid two-col">
              <label className="field">
                <span>Contact</span>
                <input
                  value={form.contact_name}
                  onChange={(e) =>
                    setForm({ ...form, contact_name: e.target.value })
                  }
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
                <span>E-mail</span>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </label>
              <label className="field full-span">
                <span>
                  <MapPin size={13} style={{ verticalAlign: "-2px" }} /> Adresse
                </span>
                <input
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                />
              </label>
              <label className="field full-span">
                <span>Notes</span>
                <textarea
                  rows={2}
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </label>
            </div>
          </FormBlock>
          {error && <div className="form-error">{error}</div>}
          <div className="tenant-compose-actions">
            <button
              className="btn btn-primary"
              disabled={save.isPending}
              type="submit"
            >
              <Save size={16} />
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setShowForm(false);
                setEditingId(null);
                setForm(EMPTY_FORM);
                setError(null);
              }}
            >
              Annuler
            </button>
          </div>
        </form>
      )}

      <ListFilters
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Nom, contact, barreau, téléphone…"
          />
        }
        activeCount={countActive(search, typeFilter, showInactive)}
        onReset={() => {
          setSearch("");
          setTypeFilter("");
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
        <FilterField label="Type" active={!!typeFilter}>
          <FilterSelect value={typeFilter} onChange={setTypeFilter}>
            <option value="">Tous les types</option>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </FilterSelect>
        </FilterField>
      </ListFilters>

      <QueryStatus
        isLoading={list.isLoading}
        isError={list.isError}
        isEmpty={!list.data?.results.length}
        emptyMessage="Aucun intervenant pour ce filtre."
        onRetry={() => list.refetch()}
      >
        <table className="table">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Type</th>
              <th>Contact</th>
              <th>Téléphone</th>
              <th>E-mail</th>
              <th>Statut</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(list.data?.results ?? []).map((p) => (
              <tr
                key={p.id}
                className={canChange ? "row-clickable" : undefined}
                onClick={canChange ? () => openEdit(p) : undefined}
              >
                <td>
                  <strong>{p.name}</strong>
                  {p.registration_no && (
                    <div className="muted small">{p.registration_no}</div>
                  )}
                </td>
                <td>
                  <Badge value={p.party_type} label={p.party_type_display} />
                </td>
                <td>{p.contact_name || "—"}</td>
                <td>{p.phone || "—"}</td>
                <td>{p.email || "—"}</td>
                <td>
                  <Badge
                    value={p.is_active ? "ACTIVE" : "DRAFT"}
                    label={p.is_active ? "Actif" : "Inactif"}
                  />
                </td>
                <td>
                  <div
                    style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {canChange && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => openEdit(p)}
                      >
                        Modifier
                      </button>
                    )}
                    {canChange && p.is_active && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={deactivate.isPending}
                        onClick={() => deactivate.mutate(p.id)}
                      >
                        Désactiver
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </QueryStatus>
    </div>
  );
}
