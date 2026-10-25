import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookMarked, Download } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type {
  CbsCatalogItem,
  CbsConnector,
  CbsRefSyncReport,
  Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { CbsProductsCatalog } from "./CbsProductsCatalog";
import {
  Card,
  DEFAULT_PAGE_SIZE,
  PageHeader,
  PaginationBar,
  QueryStatus,
  TenantScopeNotice,
} from "@/components/ui";

/** Plus de 20 lignes par page → scroll interne ; les 20 premières restent visibles. */
const LIST_PAGE_SIZE = Math.max(50, DEFAULT_PAGE_SIZE);

type TabKey =
  | "periodicities"
  | "currencies"
  | "financing_objects"
  | "service_points"
  | "managers"
  | "financing_sources"
  | "decision_motifs"
  | "professions"
  | "repayment_methods"
  | "products";

const CBS_READONLY_TABS: TabKey[] = [
  "periodicities",
  "currencies",
  "financing_objects",
  "service_points",
  "managers",
  "financing_sources",
  "decision_motifs",
  "professions",
];

const TABS: { key: TabKey; label: string; endpoint: string; cbsOnly: boolean }[] =
  [
    {
      key: "periodicities",
      label: "Périodicités",
      endpoint: "/loan-periodicities/",
      cbsOnly: true,
    },
    {
      key: "currencies",
      label: "Devises",
      endpoint: "/currencies/",
      cbsOnly: true,
    },
    {
      key: "financing_objects",
      label: "Objets de financement",
      endpoint: "/financing-objects/",
      cbsOnly: true,
    },
    {
      key: "financing_sources",
      label: "Sources de financement",
      endpoint: "/financing-sources/",
      cbsOnly: true,
    },
    {
      key: "decision_motifs",
      label: "Motifs de décision",
      endpoint: "/decision-motifs/",
      cbsOnly: true,
    },
    {
      key: "professions",
      label: "Professions",
      endpoint: "/cbs-professions/",
      cbsOnly: true,
    },
    {
      key: "service_points",
      label: "Points de service",
      endpoint: "/service-points/",
      cbsOnly: true,
    },
    {
      key: "managers",
      label: "Gestionnaires",
      endpoint: "/cbs-managers/",
      cbsOnly: true,
    },
    {
      key: "repayment_methods",
      label: "Mécanismes d’amortissement",
      endpoint: "/repayment-methods/",
      cbsOnly: false,
    },
    { key: "products", label: "Produits crédit", endpoint: "/cbs-product-references/", cbsOnly: false },
  ];

const EMPTY = {
  code: "",
  label: "",
  cbs_code: "",
  sort_order: 0,
  is_active: true,
};

function summarizeSync(report: CbsRefSyncReport): string {
  const lines: string[] = [];
  for (const [scope, bucket] of Object.entries(report.results || {})) {
    if (!bucket) continue;
    if (bucket.error) {
      lines.push(`${scope}: erreur — ${bucket.error}`);
      continue;
    }
    const unmatched = bucket.unmatched?.length ?? 0;
    lines.push(
      `${scope}: ${bucket.fetched} lus · ${bucket.created} créés · ${bucket.updated} maj · ${bucket.linked} liés` +
        (unmatched ? ` · ${unmatched} non rattachés` : ""),
    );
  }
  return lines.join("\n") || "Aucune donnée synchronisée.";
}

export function AdminCbsReferentialsPage() {
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>("periodicities");
  const [page, setPage] = useState(1);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const current = TABS.find((t) => t.key === tab)!;
  const isCbsOnly = CBS_READONLY_TABS.includes(tab);

  const connectors = useQuery({
    queryKey: ["cbs-connectors", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsConnector>>("/cbs-connectors/", {
          params: { is_active: true, page_size: 20 },
        })
      ).data,
    enabled: !needsTenant,
  });

  const activeConnector =
    connectors.data?.results?.find((c) => c.is_active) ??
    connectors.data?.results?.[0] ??
    null;

  const items = useQuery({
    queryKey: ["cbs-catalog", tab, activeTenant, page, LIST_PAGE_SIZE],
    queryFn: async () => {
      const endpoint = TABS.find((t) => t.key === tab)!.endpoint;
      const cbsOnly = CBS_READONLY_TABS.includes(tab);
      return (
        await api.get<Paginated<CbsCatalogItem>>(endpoint, {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(cbsOnly ? { is_active: true } : {}),
          },
        })
      ).data;
    },
    enabled: !needsTenant && tab !== "products",
    staleTime: 0,
  });

  const create = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        code: form.code.trim().toUpperCase(),
        label: form.label.trim(),
        cbs_code: form.cbs_code.trim(),
        sort_order: form.sort_order,
        is_active: form.is_active,
      };
      return (await api.post(current.endpoint, payload)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cbs-catalog", tab] });
      setForm({ ...EMPTY });
      setError(null);
    },
    onError: () =>
      setError("Création impossible. Vérifiez le code (unique) et les champs."),
  });

  const patch = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: Partial<CbsCatalogItem>;
    }) => (await api.patch(`${current.endpoint}${id}/`, data)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cbs-catalog", tab] }),
  });

  const syncFromCbs = useMutation({
    mutationFn: async () => {
      if (!activeConnector) {
        throw new Error("Aucun connecteur CBS actif.");
      }
      return (
        await api.post<CbsRefSyncReport>(
          `/cbs-connectors/${activeConnector.id}/sync-referentials/`,
          {},
        )
      ).data;
    },
    onSuccess: async (report) => {
      setSyncMsg(summarizeSync(report));
      setError(null);
      setPage(1);
      // Force le rechargement des tableaux (staleTime global 30s sinon)
      await qc.invalidateQueries({ queryKey: ["cbs-catalog"] });
      await qc.refetchQueries({ queryKey: ["cbs-catalog"], type: "active" });
      await qc.invalidateQueries({ queryKey: ["service-points"] });
      await qc.invalidateQueries({ queryKey: ["cbs-managers"] });
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ||
        (err as Error)?.message ||
        "Import CBS impossible.";
      setError(String(detail));
      setSyncMsg(null);
    },
  });

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={BookMarked}
          title="Référentiels CBS"
          subtitle="Données Perfect synchronisées dans FinFlow"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={BookMarked}
        title="Référentiels CBS"
        subtitle="Référentiels importés et correspondances des produits CBS"
        actions={
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!activeConnector || syncFromCbs.isPending}
            onClick={() => syncFromCbs.mutate()}
            title={
              activeConnector
                ? `Importer depuis ${activeConnector.name}`
                : "Aucun connecteur CBS actif"
            }
          >
            <Download size={16} />
            {syncFromCbs.isPending
              ? "Import en cours…"
              : "Mettre à jour depuis le CBS"}
          </button>
        }
      />

      {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}

      {patch.isError && <p className="form-error">Modification du mécanisme impossible.</p>}

      {syncMsg && (
        <div style={{ marginBottom: 16 }}>
          <Card title="Résultat de l'import CBS">
            <pre
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                fontFamily: "inherit",
                fontSize: 13,
              }}
            >
              {syncMsg}
            </pre>
          </Card>
        </div>
      )}

      <div
        className="tabs"
        style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`btn btn-sm ${tab === t.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => {
              setTab(t.key);
              setPage(1);
              setForm({ ...EMPTY });
              setError(null);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "products" && <CbsProductsCatalog creditOnly />}
      {tab !== "products" && !isCbsOnly && (
        <Card title={`Ajouter — ${current.label}`}>
          <form
            className="inline-form"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Code FIN_FLOW *</span>
                <input
                  value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
                  placeholder="DEGRESSIVE"
                  required
                />
              </label>
              <label className="field">
                <span>Libellé *</span>
                <input
                  value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Identifiant CBS de remboursement *</span>
                <input value={form.cbs_code} onChange={(e) => setForm({ ...form, cbs_code: e.target.value })} required />
              </label>
              <label className="field">
                <span>Ordre</span>
                <input
                  type="number"
                  value={form.sort_order}
                  onChange={(e) =>
                    setForm({ ...form, sort_order: Number(e.target.value) })
                  }
                />
              </label>
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={create.isPending}
            >
              Enregistrer
            </button>
          </form>
        </Card>
      )}

      {tab !== "products" && <QueryStatus
        isLoading={items.isLoading || (syncFromCbs.isPending && !items.data)}
        isError={items.isError}
        isEmpty={!items.data?.results.length}
        emptyMessage={
          isCbsOnly
            ? "Aucune donnée. Lancez « Mettre à jour depuis le CBS »."
            : "Aucun élément. Créez-en manuellement."
        }
        onRetry={() => items.refetch()}
      >
        <>
          {items.isFetching && (
            <p className="page-subtitle" style={{ marginBottom: 8 }}>
              Actualisation…
            </p>
          )}
          <div key={tab} className="cbs-ref-table">
            <div className="cbs-ref-table__head">
              <table className="table">
                <colgroup>
                  <col className="cbs-ref-col-code" />
                  <col className="cbs-ref-col-label" />
                  <col className="cbs-ref-col-cbs" />
                  {tab === "periodicities" && (
                    <col className="cbs-ref-col-extra" />
                  )}
                  {tab === "financing_objects" && (
                    <col className="cbs-ref-col-extra" />
                  )}
                  <col className="cbs-ref-col-active" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Libellé</th>
                    <th>{tab === "repayment_methods" ? "ID CBS remboursement" : "ID CBS"}</th>
                    {tab === "periodicities" && <th className="num">/ an</th>}
                    {tab === "financing_objects" && <th>PurposeType</th>}
                    <th>Actif</th>
                  </tr>
                </thead>
              </table>
            </div>
            <div className="cbs-ref-table__body">
              <table className="table">
                <colgroup>
                  <col className="cbs-ref-col-code" />
                  <col className="cbs-ref-col-label" />
                  <col className="cbs-ref-col-cbs" />
                  {tab === "periodicities" && (
                    <col className="cbs-ref-col-extra" />
                  )}
                  {tab === "financing_objects" && (
                    <col className="cbs-ref-col-extra" />
                  )}
                  <col className="cbs-ref-col-active" />
                </colgroup>
                <tbody>
                  {(items.data?.results ?? [])
                    .filter((row) => !isCbsOnly || row.is_active)
                    .map((row) => (
                      <tr key={row.id}>
                        <td>{row.code}</td>
                        <td>{row.label}</td>
                        <td>
                          {tab === "repayment_methods" ? (
                            <input aria-label={`Identifiant CBS du mécanisme ${row.label}`} key={`${row.id}:${row.cbs_code}`} defaultValue={row.cbs_code || ""}
                              onBlur={(e) => { const value = e.target.value.trim(); if (value !== (row.cbs_code || "")) patch.mutate({id: row.id, data: {cbs_code: value}}); }} />
                          ) : row.cbs_code || "—"}
                        </td>
                        {tab === "periodicities" && (
                          <td className="num">
                            {row.periods_per_year ?? "—"}
                          </td>
                        )}
                        {tab === "financing_objects" && (
                          <td>{row.purpose_type || "—"}</td>
                        )}
                        <td>
                          {!isCbsOnly ? (
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={row.is_active}
                                onChange={(e) =>
                                  patch.mutate({
                                    id: row.id,
                                    data: { is_active: e.target.checked },
                                  })
                                }
                              />
                            </label>
                          ) : row.is_active ? (
                            "Oui"
                          ) : (
                            "Non"
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
          <PaginationBar
            page={page}
            count={items.data?.count ?? 0}
            pageSize={LIST_PAGE_SIZE}
            onPageChange={setPage}
          />
        </>
      </QueryStatus>}
    </div>
  );
}
