import { useQuery } from "@tanstack/react-query";
import { FolderOpen } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { DocumentCategory, GedDocument, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { DocumentVerification } from "@/components/DocumentVerification";
import {
  PERM_ADMIN_REFERENTIALS,
  PERM_CLIENTS,
  PERM_COLLECTIONS,
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_FORMALIZATIONS,
  PERM_GUARANTEES,
  PERM_LITIGATION,
  PERM_RELEASES,
  PERM_SURETIES,
} from "@/auth/routePerms";
import {
  ClientFilterBanner,
  FilterField,
  FilterSelect,
  ListFilters,
  OfficerFilter,
  SearchInput,
  countActive,
  useClientSearchParam,
} from "@/components/ListFilters";
import { PermLink } from "@/components/PermLink";
import {
  DEFAULT_PAGE_SIZE,
  PageHeader,
  PaginationBar,
  QueryStatus,
  TenantScopeNotice,
  formatDate,
} from "@/components/ui";

const LIST_PAGE_SIZE = Math.max(15, DEFAULT_PAGE_SIZE);

const RELATED_KIND_OPTIONS = [
  ["", "Tous les modules"],
  ["CREDIT", "Dossier"],
  ["CLIENT", "Client"],
  ["GUARANTEE", "Garantie"],
  ["SURETY", "Caution"],
  ["DATION", "Dation"],
  ["FORMALIZATION", "Formalisation"],
  ["RELEASE", "Main levée"],
  ["COLLECTION", "Recouvrement"],
  ["LITIGATION", "Contentieux"],
  ["LOAN", "Prêt"],
  ["OTHER", "Autre"],
] as const;

const RELATED_KIND_LABELS: Record<string, string> = Object.fromEntries(
  RELATED_KIND_OPTIONS.filter(([value]) => value).map(([value, label]) => [
    value,
    label,
  ]),
);

const EXPIRY_OPTIONS = [
  ["", "Toutes les échéances"],
  ["expired", "Expirés"],
  ["expiring", "Expirant ≤ 30 j"],
  ["dated", "Avec date d'expiration"],
  ["none", "Sans date d'expiration"],
] as const;

function formatBytes(n: number) {
  if (!n || n < 0) return "—";
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
}

function relatedHref(doc: GedDocument): string | null {
  if (doc.related_path) return doc.related_path;
  const t = doc.related_type || "";
  if (!doc.object_id) return null;
  if (t.includes("creditapplication")) return `/dossiers/${doc.object_id}`;
  if (t.includes("guaranteereleaserequest"))
    return `/mains-levees/${doc.object_id}`;
  if (t.includes("dationrequest")) return `/dations/${doc.object_id}`;
  if (t.includes("guaranteeformalizationrequest"))
    return `/formalisations/${doc.object_id}`;
  if (t.includes("collectioncase")) return `/recouvrement/${doc.object_id}`;
  if (t.includes("litigationfile")) return `/recouvrement`;
  if (t === "clients.client" || t.endsWith(".client"))
    return `/clients/${doc.object_id}`;
  if (t.includes("surety") && !t.includes("engagement"))
    return `/cautions/${doc.object_id}`;
  if (t.includes("guarantee") && !t.includes("request"))
    return `/garanties/${doc.object_id}`;
  if (t.includes("loan")) return "/prets";
  return null;
}

function relatedPerms(href: string): readonly string[] | null {
  if (href.startsWith("/dossiers")) return PERM_CREDITS;
  if (href.startsWith("/mains-levees")) return PERM_RELEASES;
  if (href.startsWith("/dations")) return PERM_DATIONS;
  if (href.startsWith("/formalisations")) return PERM_FORMALIZATIONS;
  if (href.includes("/contentieux/")) return PERM_LITIGATION;
  if (href.startsWith("/recouvrement")) return PERM_COLLECTIONS;
  if (href.startsWith("/garanties")) return PERM_GUARANTEES;
  if (href.startsWith("/clients")) return PERM_CLIENTS;
  if (href.startsWith("/cautions")) return PERM_SURETIES;
  if (href.startsWith("/prets")) return PERM_CREDITS;
  return null;
}

function relatedKindLabel(doc: GedDocument) {
  if (doc.related_kind && RELATED_KIND_LABELS[doc.related_kind]) {
    return RELATED_KIND_LABELS[doc.related_kind];
  }
  return doc.related_type || "—";
}

export function DocumentsPage() {
  const { user, activeTenant } = useAuth();
  const { clientFilter, clearClientFilter } = useClientSearchParam();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [relatedKind, setRelatedKind] = useState("");
  const [expiry, setExpiry] = useState("");
  const [uploadedBy, setUploadedBy] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");

  const categories = useQuery({
    queryKey: ["document-categories", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<DocumentCategory>>("/document-categories/", {
          params: { page_size: 200, is_active: true },
        })
      ).data,
    enabled: !needsTenant,
  });

  const docs = useQuery({
    queryKey: [
      "ged-documents",
      activeTenant,
      page,
      LIST_PAGE_SIZE,
      search,
      category,
      relatedKind,
      expiry,
      uploadedBy,
      createdAfter,
      createdBefore,
      clientFilter,
    ],
    queryFn: async () =>
      (
        await api.get<Paginated<GedDocument>>("/documents/", {
          params: {
            page,
            page_size: LIST_PAGE_SIZE,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(category ? { category } : {}),
            ...(relatedKind ? { related_kind: relatedKind } : {}),
            ...(expiry ? { expiry } : {}),
            ...(uploadedBy ? { uploaded_by: uploadedBy } : {}),
            ...(createdAfter ? { created_after: createdAfter } : {}),
            ...(createdBefore ? { created_before: createdBefore } : {}),
            ...(clientFilter ? { client: clientFilter } : {}),
          },
        })
      ).data,
    enabled: !needsTenant,
  });

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={FolderOpen}
          title="GED — Documents"
          subtitle="Consultation unifiée de tous les modules"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  const results = docs.data?.results ?? [];
  const count = docs.data?.count ?? 0;

  return (
    <div className="page-shell page-shell--list">
      <div className="list-page-chrome">
        <PageHeader
          icon={FolderOpen}
          title="GED — Documents"
          subtitle="Consultation unifiée (clients, dossiers, garanties, cautions, formalisations, mains levées, dations, recouvrement, contentieux)"
        />

        <ListFilters
          search={
            <SearchInput
              value={search}
              onChange={setFilter(setSearch)}
              placeholder="Nom de fichier, catégorie, déposant…"
            />
          }
          activeCount={countActive(
            search,
            category,
            relatedKind,
            expiry,
            uploadedBy,
            createdAfter,
            createdBefore,
            clientFilter,
          )}
          onReset={() => {
            setSearch("");
            setCategory("");
            setRelatedKind("");
            setExpiry("");
            setUploadedBy("");
            setCreatedAfter("");
            setCreatedBefore("");
            setPage(1);
            if (clientFilter) clearClientFilter();
          }}
        >
          <FilterField label="Module" active={!!relatedKind}>
            <FilterSelect
              value={relatedKind}
              onChange={setFilter(setRelatedKind)}
            >
              {RELATED_KIND_OPTIONS.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Catégorie" active={!!category}>
            <FilterSelect value={category} onChange={setFilter(setCategory)}>
              <option value="">Toutes les catégories</option>
              {(categories.data?.results ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Expiration" active={!!expiry}>
            <FilterSelect value={expiry} onChange={setFilter(setExpiry)}>
              {EXPIRY_OPTIONS.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <OfficerFilter
            value={uploadedBy}
            onChange={setFilter(setUploadedBy)}
            label="Déposé par"
            emptyLabel="Tous les déposants"
          />
          <FilterField label="Déposé du" active={!!createdAfter}>
            <input
              type="date"
              value={createdAfter}
              onChange={(e) => setFilter(setCreatedAfter)(e.target.value)}
            />
          </FilterField>
          <FilterField label="jusqu'au" active={!!createdBefore}>
            <input
              type="date"
              value={createdBefore}
              onChange={(e) => setFilter(setCreatedBefore)(e.target.value)}
            />
          </FilterField>
        </ListFilters>
        <ClientFilterBanner
          clientId={clientFilter}
          onClear={() => {
            clearClientFilter();
            setPage(1);
          }}
        />
        <p className="muted small" style={{ marginTop: 8, marginBottom: 12 }}>
          Les catégories se paramètrent dans{" "}
          <PermLink
            user={user}
            anyOf={PERM_ADMIN_REFERENTIALS}
            to="/admin/referentiels-metier"
          >
            Référentiels métier
          </PermLink>
          . Les pièces dossier sont aussi indexées ici à l&apos;upload.
        </p>
      </div>

      <div className="list-table-region">
        <QueryStatus
          isLoading={docs.isLoading}
          isError={docs.isError}
          isEmpty={results.length === 0}
          emptyMessage="Aucun document dans la GED pour ces filtres."
          onRetry={() => docs.refetch()}
        >
          <>
            <div className="table-scroll table-scroll--fill">
              <table className="table card">
                <thead>
                  <tr>
                    <th>Nom</th>
                    <th>Catégorie</th>
                    <th>Module</th>
                    <th>Rattaché à</th>
                    <th>Taille</th>
                    <th>Créé le</th>
                    <th>Expire</th>
                    <th>Contrôle documentaire</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((d) => {
                    const href = relatedHref(d);
                    const hrefPerms = href ? relatedPerms(href) : null;
                    const url = d.file_url || d.file;
                    return (
                      <tr
                        key={d.id}
                        className={url ? "row-clickable" : undefined}
                        onClick={
                          url
                            ? () =>
                                window.open(url, "_blank", "noopener,noreferrer")
                            : undefined
                        }
                      >
                        <td>
                          <strong>{d.name}</strong>
                          {d.uploaded_by_name ? (
                            <div className="muted small">
                              {d.uploaded_by_name}
                            </div>
                          ) : null}
                        </td>
                        <td>
                          <code>{d.category_code || "—"}</code>
                          <div className="muted small">{d.category_label}</div>
                        </td>
                        <td>{relatedKindLabel(d)}</td>
                        <td>
                          {href && d.related_label ? (
                            hrefPerms ? (
                              <PermLink
                                user={user}
                                anyOf={hrefPerms}
                                to={href}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {d.related_label}
                              </PermLink>
                            ) : (
                              <Link
                                to={href}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {d.related_label}
                              </Link>
                            )
                          ) : (
                            d.related_label || <span className="muted">—</span>
                          )}
                        </td>
                        <td>{formatBytes(d.size_bytes)}</td>
                        <td>{formatDate(d.created_at)}</td>
                        <td>
                          {d.expiry_date ? formatDate(d.expiry_date) : "—"}
                        </td>
                        <td onClick={(event) => event.stopPropagation()}><DocumentVerification document={d} canVerify={hasPerm(user, "documents.change_document")} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <PaginationBar
              page={page}
              count={count}
              pageSize={LIST_PAGE_SIZE}
              onPageChange={setPage}
            />
          </>
        </QueryStatus>
      </div>
    </div>
  );
}
