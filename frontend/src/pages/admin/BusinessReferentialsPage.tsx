import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Library, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type {
  AnalysisThresholdConfig,
  CreditProduct,
  DocumentCategory,
  Paginated,
  ProductChecklistItem,
  RejectReason,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import {
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  TenantScopeNotice,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

type TabKey = "rejects" | "checklists" | "thresholds" | "ged";

const TABS: { key: TabKey; label: string }[] = [
  { key: "rejects", label: "Motifs de rejet" },
  { key: "checklists", label: "Checklists produits" },
  { key: "thresholds", label: "Seuils d'analyse" },
  { key: "ged", label: "Catégories GED" },
];

const TAB_VIEW_PERMISSIONS: Record<TabKey, string> = {
  rejects: "catalog.view_rejectreason",
  checklists: "catalog.view_checklistitem",
  thresholds: "credits.view_analysisthreshold",
  ged: "documents.view_documentcategory",
};

const THRESHOLD_FIELDS: {
  key: keyof AnalysisThresholdConfig;
  label: string;
  group: string;
}[] = [
  { key: "max_debt_ratio", label: "Endettement max particulier (%)", group: "Ratios" },
  { key: "min_dscr", label: "DSCR minimum", group: "Ratios" },
  { key: "max_leverage_ratio", label: "Endettement max entreprise (%)", group: "Ratios" },
  {
    key: "min_living_wage_per_capita",
    label: "Reste à vivre min / personne",
    group: "Ratios",
  },
  {
    key: "min_interest_coverage",
    label: "Couverture charges financières (x)",
    group: "Ratios",
  },
  { key: "max_gearing", label: "Gearing max", group: "Ratios" },
  {
    key: "min_financial_autonomy",
    label: "Autonomie financière min (%)",
    group: "Ratios",
  },
  { key: "min_current_ratio", label: "Liquidité générale min", group: "Ratios" },
  {
    key: "min_guarantee_coverage",
    label: "Couverture garanties min (%)",
    group: "Collatéral",
  },
  { key: "stress_pct", label: "Baisse stress test (%)", group: "Collatéral" },
  {
    key: "transferable_quota_fraction",
    label: "Quotité cessible salaire (%)",
    group: "Revenus",
  },
  {
    key: "informal_income_weight",
    label: "Pondération revenus informels (%)",
    group: "Revenus",
  },
  { key: "haircut_mortgage", label: "Haircut hypothèque (%)", group: "Haircuts" },
  { key: "haircut_vehicle", label: "Haircut véhicule (%)", group: "Haircuts" },
  { key: "haircut_jewelry", label: "Haircut bijoux (%)", group: "Haircuts" },
  {
    key: "haircut_financial_deposit",
    label: "Haircut DAT / épargne (%)",
    group: "Haircuts",
  },
  {
    key: "haircut_financial_security",
    label: "Haircut titres (%)",
    group: "Haircuts",
  },
  { key: "haircut_other", label: "Haircut autres (%)", group: "Haircuts" },
];

const EMPTY_THRESHOLD: AnalysisThresholdConfig = {
  id: "",
  max_debt_ratio: "",
  min_dscr: "",
  max_leverage_ratio: "",
  min_living_wage_per_capita: "",
  min_interest_coverage: "",
  max_gearing: "",
  min_financial_autonomy: "",
  min_current_ratio: "",
  min_guarantee_coverage: "",
  stress_pct: "",
  transferable_quota_fraction: "",
  informal_income_weight: "",
  haircut_mortgage: "",
  haircut_vehicle: "",
  haircut_jewelry: "",
  haircut_financial_deposit: "",
  haircut_financial_security: "",
  haircut_other: "",
};

function errMsg(err: unknown, fallback: string) {
  return apiErrorMessage(err, fallback);
}

export function AdminBusinessReferentialsPage() {
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canViewRejects = hasPerm(user, "catalog.view_rejectreason");
  const canAddRejects = hasPerm(user, "catalog.add_rejectreason");
  const canChangeRejects = hasPerm(user, "catalog.change_rejectreason");
  const canDeleteRejects = hasPerm(user, "catalog.delete_rejectreason");
  const canViewChecklists = hasPerm(user, "catalog.view_checklistitem");
  const canViewProducts = hasPerm(user, "catalog.view_creditproduct");
  const canAddChecklists =
    hasPerm(user, "catalog.add_checklistitem") &&
    canViewProducts;
  const canChangeChecklists = hasPerm(user, "catalog.change_checklistitem");
  const canDeleteChecklists = hasPerm(user, "catalog.delete_checklistitem");
  const canViewThresholds = hasPerm(user, "credits.view_analysisthreshold");
  const canViewGed = hasPerm(user, "documents.view_documentcategory");
  const canAddGed = hasPerm(user, "documents.add_documentcategory");
  const canChangeGed = hasPerm(user, "documents.change_documentcategory");
  const canDeleteGed = hasPerm(user, "documents.delete_documentcategory");
  const visibleTabs = TABS.filter((item) =>
    hasPerm(user, TAB_VIEW_PERMISSIONS[item.key]),
  );
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>(
    () => visibleTabs[0]?.key ?? "rejects",
  );
  const activeTab = visibleTabs.some((item) => item.key === tab)
    ? tab
    : visibleTabs[0]?.key ?? "rejects";
  const [error, setError] = useState<string | null>(null);

  const [rejectForm, setRejectForm] = useState({
    code: "",
    label: "",
    description: "",
    is_active: true,
  });
  const [gedForm, setGedForm] = useState({
    code: "",
    label: "",
    description: "",
    tracks_expiry: false,
    is_active: true,
  });
  const [checklistForm, setChecklistForm] = useState({
    product: "",
    label: "",
    is_mandatory: true,
    order: 0,
  });
  const [productFilter, setProductFilter] = useState("");

  const rejects = useQuery({
    queryKey: ["admin-reject-reasons", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<RejectReason>>("/reject-reasons/", {
          params: { page_size: 200 },
        })
      ).data,
    enabled: !needsTenant && canViewRejects && activeTab === "rejects",
  });

  const products = useQuery({
    queryKey: ["credit-products-admin-ref", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditProduct>>("/credit-products/", {
          params: { page_size: 200, is_active: true },
        })
      ).data,
    enabled: !needsTenant && canViewChecklists && canViewProducts && activeTab === "checklists",
  });

  const checklists = useQuery({
    queryKey: ["admin-checklist-items", activeTenant, productFilter],
    queryFn: async () =>
      (
        await api.get<Paginated<ProductChecklistItem>>("/checklist-items/", {
          params: {
            page_size: 200,
            ...(productFilter ? { product: productFilter } : {}),
          },
        })
      ).data,
    enabled: !needsTenant && canViewChecklists && activeTab === "checklists",
  });

  const gedCats = useQuery({
    queryKey: ["admin-document-categories", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<DocumentCategory>>("/document-categories/", {
          params: { page_size: 200 },
        })
      ).data,
    enabled: !needsTenant && canViewGed && activeTab === "ged",
  });

  const thresholdQuery = useQuery({
    queryKey: ["analysis-thresholds-current", activeTenant],
    queryFn: async () =>
      (
        await api.get<AnalysisThresholdConfig>(
          "/analysis-thresholds/current/",
        )
      ).data,
    enabled: !needsTenant && canViewThresholds && activeTab === "thresholds",
  });

  const thresholds: AnalysisThresholdConfig = {
    ...EMPTY_THRESHOLD,
    ...thresholdQuery.data,
  };

  const createReject = useMutation({
    mutationFn: async () =>
      (
        await api.post("/reject-reasons/", {
          code: rejectForm.code.trim().toUpperCase(),
          label: rejectForm.label.trim(),
          description: rejectForm.description.trim(),
          is_active: rejectForm.is_active,
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-reject-reasons"] });
      qc.invalidateQueries({ queryKey: ["reject-reasons"] });
      setRejectForm({ code: "", label: "", description: "", is_active: true });
      setError(null);
    },
    onError: (e) => setError(errMsg(e, "Création impossible.")),
  });

  const patchReject = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<RejectReason>;
    }) => (await api.patch(`/reject-reasons/${id}/`, data)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-reject-reasons"] });
      qc.invalidateQueries({ queryKey: ["reject-reasons"] });
    },
  });

  const deleteReject = useMutation({
    mutationFn: async (id: string) => api.delete(`/reject-reasons/${id}/`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-reject-reasons"] });
      qc.invalidateQueries({ queryKey: ["reject-reasons"] });
    },
    onError: (e) =>
      setError(errMsg(e, "Suppression impossible (motif peut-être utilisé).")),
  });

  const createChecklist = useMutation({
    mutationFn: async () =>
      (
        await api.post("/checklist-items/", {
          product: checklistForm.product,
          label: checklistForm.label.trim(),
          is_mandatory: checklistForm.is_mandatory,
          order: checklistForm.order,
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-checklist-items"] });
      setChecklistForm((f) => ({ ...f, label: "", order: f.order + 1 }));
      setError(null);
    },
    onError: (e) => setError(errMsg(e, "Création impossible.")),
  });

  const patchChecklist = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<ProductChecklistItem>;
    }) => (await api.patch(`/checklist-items/${id}/`, data)).data,
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-checklist-items"] }),
  });

  const deleteChecklist = useMutation({
    mutationFn: async (id: string) => api.delete(`/checklist-items/${id}/`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-checklist-items"] }),
  });

  const createGed = useMutation({
    mutationFn: async () =>
      (
        await api.post("/document-categories/", {
          code: gedForm.code.trim().toUpperCase(),
          label: gedForm.label.trim(),
          description: gedForm.description.trim(),
          tracks_expiry: gedForm.tracks_expiry,
          is_active: gedForm.is_active,
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-document-categories"] });
      setGedForm({
        code: "",
        label: "",
        description: "",
        tracks_expiry: false,
        is_active: true,
      });
      setError(null);
    },
    onError: (e) => setError(errMsg(e, "Création impossible.")),
  });

  const patchGed = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<DocumentCategory>;
    }) => (await api.patch(`/document-categories/${id}/`, data)).data,
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-document-categories"] }),
  });

  const deleteGed = useMutation({
    mutationFn: async (id: string) =>
      api.delete(`/document-categories/${id}/`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-document-categories"] }),
    onError: (e) =>
      setError(
        errMsg(e, "Suppression impossible (catégorie peut-être utilisée)."),
      ),
  });

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Library}
          title="Référentiels métier"
          subtitle="Motifs, checklists, seuils, catégories GED"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={Library}
        title="Référentiels métier"
        subtitle="Paramétrage filiale : rejets, checklists documentaires, seuils d'analyse, catégories GED"
      />

      <div className="tabs" style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {visibleTabs.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`btn btn-sm ${activeTab === t.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => {
              setTab(t.key);
              setError(null);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="form-error">{error}</div>}
      {activeTab === "rejects" && (
        <>
          {canAddRejects && <Card title="Ajouter un motif de rejet">
            <form
              className="inline-form"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                createReject.mutate();
              }}
            >
              <div className="form-grid">
                <label className="field">
                  <span>Code *</span>
                  <input
                    value={rejectForm.code}
                    onChange={(e) =>
                      setRejectForm({ ...rejectForm, code: e.target.value })
                    }
                    placeholder="RISQUE_ELEVE"
                    required
                  />
                </label>
                <label className="field">
                  <span>Libellé *</span>
                  <input
                    value={rejectForm.label}
                    onChange={(e) =>
                      setRejectForm({ ...rejectForm, label: e.target.value })
                    }
                    required
                  />
                </label>
                <label className="field" style={{ gridColumn: "1 / -1" }}>
                  <span>Description</span>
                  <input
                    value={rejectForm.description}
                    onChange={(e) =>
                      setRejectForm({
                        ...rejectForm,
                        description: e.target.value,
                      })
                    }
                  />
                </label>
              </div>
              <button
                className="btn btn-primary btn-sm"
                disabled={createReject.isPending}
              >
                Ajouter
              </button>
            </form>
          </Card>}

          <Card title="Motifs existants">
            {rejects.isLoading ? (
              <Spinner />
            ) : (rejects.data?.results.length ?? 0) === 0 ? (
              <EmptyState message="Aucun motif de rejet." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Libellé</th>
                    <th>Actif</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rejects.data!.results.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <code>{r.code}</code>
                      </td>
                      <td>{r.label}</td>
                      <td>
                        <input
                          type="checkbox"
                          checked={r.is_active}
                          disabled={!canChangeRejects}
                          onChange={(e) =>
                            patchReject.mutate({
                              id: r.id,
                              data: { is_active: e.target.checked },
                            })
                          }
                        />
                      </td>
                      <td>
                        {canDeleteRejects && <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Supprimer le motif « ${r.label} » ?`,
                              )
                            ) {
                              deleteReject.mutate(r.id);
                            }
                          }}
                        >
                          <Trash2 size={14} />
                        </button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}

      {activeTab === "checklists" && (
        <>
          {canAddChecklists && <Card title="Ajouter une pièce de checklist">
            <form
              className="inline-form"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                if (!checklistForm.product) {
                  setError("Sélectionnez un produit.");
                  return;
                }
                createChecklist.mutate();
              }}
            >
              <div className="form-grid">
                <label className="field">
                  <span>Produit *</span>
                  <select
                    value={checklistForm.product}
                    onChange={(e) => {
                      setChecklistForm({
                        ...checklistForm,
                        product: e.target.value,
                      });
                      setProductFilter(e.target.value);
                    }}
                    required
                  >
                    <option value="">— Choisir —</option>
                    {(products.data?.results ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.code} — {p.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Libellé de la pièce *</span>
                  <input
                    value={checklistForm.label}
                    onChange={(e) =>
                      setChecklistForm({
                        ...checklistForm,
                        label: e.target.value,
                      })
                    }
                    placeholder="CNI / RCCM / Bulletins de salaire…"
                    required
                  />
                </label>
                <label className="field">
                  <span>Ordre</span>
                  <input
                    type="number"
                    min={0}
                    value={checklistForm.order}
                    onChange={(e) =>
                      setChecklistForm({
                        ...checklistForm,
                        order: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Obligatoire</span>
                  <input
                    type="checkbox"
                    checked={checklistForm.is_mandatory}
                    onChange={(e) =>
                      setChecklistForm({
                        ...checklistForm,
                        is_mandatory: e.target.checked,
                      })
                    }
                  />
                </label>
              </div>
              <button
                className="btn btn-primary btn-sm"
                disabled={createChecklist.isPending}
              >
                Ajouter
              </button>
            </form>
          </Card>}

          <Card title="Pièces par produit">
            {canViewProducts && <label className="field" style={{ marginBottom: 12, maxWidth: 360 }}>
              <span>Filtrer par produit</span>
              <select
                value={productFilter}
                onChange={(e) => setProductFilter(e.target.value)}
              >
                <option value="">Tous</option>
                {(products.data?.results ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.label}
                  </option>
                ))}
              </select>
            </label>}
            {checklists.isLoading ? (
              <Spinner />
            ) : (checklists.data?.results.length ?? 0) === 0 ? (
              <EmptyState message="Aucune pièce de checklist." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Produit</th>
                    <th>Pièce</th>
                    <th>Ordre</th>
                    <th>Obligatoire</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {checklists.data!.results.map((c) => (
                    <tr key={c.id}>
                      <td>{c.product_label || c.product.slice(0, 8)}</td>
                      <td>{c.label}</td>
                      <td>{c.order}</td>
                      <td>
                        <input
                          type="checkbox"
                          checked={c.is_mandatory}
                          disabled={!canChangeChecklists}
                          onChange={(e) =>
                            patchChecklist.mutate({
                              id: c.id,
                              data: { is_mandatory: e.target.checked },
                            })
                          }
                        />
                      </td>
                      <td>
                        {canDeleteChecklists && <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            if (window.confirm("Supprimer cette pièce ?")) {
                              deleteChecklist.mutate(c.id);
                            }
                          }}
                        >
                          <Trash2 size={14} />
                        </button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}

      {activeTab === "thresholds" && (
        <Card title="Seuils d'analyse financière (filiale)">
          <p className="muted">Les seuils se modifient dans le <Link to="/admin/configuration">Centre de configuration</Link>, avec validation par un autre utilisateur. Les valeurs ci-dessous représentent le socle applicable sans ciblage.</p>
          {thresholdQuery.isLoading ? (
            <Spinner />
          ) : (
            <fieldset disabled style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}><div>
              {(["Ratios", "Collatéral", "Revenus", "Haircuts"] as const).map(
                (group) => (
                  <div key={group} style={{ marginBottom: 18 }}>
                    <p className="section-subtitle">{group}</p>
                    <div className="form-grid two-col">
                      {THRESHOLD_FIELDS.filter((f) => f.group === group).map(
                        (f) => (
                          <label key={f.key} className="field">
                            <span>{f.label}</span>
                            <input
                              type="number"
                              step="0.01"
                              value={String(thresholds[f.key] ?? "")}
                            />
                          </label>
                        ),
                      )}
                    </div>
                  </div>
                ),
              )}
            </div></fieldset>
          )}
        </Card>
      )}

      {activeTab === "ged" && (
        <>
          {canAddGed && <Card title="Ajouter une catégorie GED">
            <form
              className="inline-form"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                createGed.mutate();
              }}
            >
              <div className="form-grid">
                <label className="field">
                  <span>Code *</span>
                  <input
                    value={gedForm.code}
                    onChange={(e) =>
                      setGedForm({ ...gedForm, code: e.target.value })
                    }
                    placeholder="CNI"
                    required
                  />
                </label>
                <label className="field">
                  <span>Libellé *</span>
                  <input
                    value={gedForm.label}
                    onChange={(e) =>
                      setGedForm({ ...gedForm, label: e.target.value })
                    }
                    required
                  />
                </label>
                <label className="field" style={{ gridColumn: "1 / -1" }}>
                  <span>Description</span>
                  <input
                    value={gedForm.description}
                    onChange={(e) =>
                      setGedForm({ ...gedForm, description: e.target.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Suivi d&apos;expiration</span>
                  <input
                    type="checkbox"
                    checked={gedForm.tracks_expiry}
                    onChange={(e) =>
                      setGedForm({
                        ...gedForm,
                        tracks_expiry: e.target.checked,
                      })
                    }
                  />
                </label>
              </div>
              <button
                className="btn btn-primary btn-sm"
                disabled={createGed.isPending}
              >
                Ajouter
              </button>
            </form>
          </Card>}

          <Card title="Catégories existantes">
            {gedCats.isLoading ? (
              <Spinner />
            ) : (gedCats.data?.results.length ?? 0) === 0 ? (
              <EmptyState message="Aucune catégorie GED." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Libellé</th>
                    <th>Expiration</th>
                    <th>Actif</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {gedCats.data!.results.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <code>{c.code}</code>
                      </td>
                      <td>{c.label}</td>
                      <td>
                        <input
                          type="checkbox"
                          checked={c.tracks_expiry}
                          disabled={!canChangeGed}
                          onChange={(e) =>
                            patchGed.mutate({
                              id: c.id,
                              data: { tracks_expiry: e.target.checked },
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={c.is_active}
                          disabled={!canChangeGed}
                          onChange={(e) =>
                            patchGed.mutate({
                              id: c.id,
                              data: { is_active: e.target.checked },
                            })
                          }
                        />
                      </td>
                      <td>
                        {canDeleteGed && <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Supprimer la catégorie « ${c.label} » ?`,
                              )
                            ) {
                              deleteGed.mutate(c.id);
                            }
                          }}
                        >
                          <Trash2 size={14} />
                        </button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
