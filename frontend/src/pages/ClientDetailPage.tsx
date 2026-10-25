import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Briefcase,
  Building2,
  CircleDollarSign,
  Contact,
  FileSignature,
  FileText,
  FilePlus2,
  FilePenLine,
  FolderOpen,
  Trash2,
  GitBranch,
  Cable,
  HandCoins,
  Heart,
  History,
  IdCard,
  ImageOff,
  Landmark,
  Pencil,
  Phone,
  Plus,
  Scale,
  ShieldCheck,
  TriangleAlert,
  Unlock,
  User,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import {
  CLIENT_LABELS,
  type AuditLog,
  type Client,
  type CollectionCase,
  type CreditApplication,
  type DationRequest,
  type GedDocument,
  type Guarantee,
  type GuaranteeFormalizationRequest,
  type GuaranteeReleaseRequest,
  type Paginated,
  type SuretyEngagement,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import {
  PERM_COLLECTIONS,
  PERM_CREDIT_CREATE,
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_DOCUMENTS,
  PERM_FORMALIZATIONS,
  PERM_GUARANTEES,
  PERM_RELEASES,
  PERM_SURETIES,
} from "@/auth/routePerms";
import { Badge, Card, ErrorState, Spinner, formatDate, formatMoney } from "@/components/ui";

function label(map: Record<string, string>, key: string) {
  return map[key] || key || "—";
}

/** Ligne d'une liste de définitions ; les valeurs vides restent visibles (« — »). */
function Row({ term, value }: { term: string; value?: ReactNode }) {
  const empty =
    value === null ||
    value === undefined ||
    value === "" ||
    (typeof value === "string" && value.trim() === "");
  return (
    <div>
      <dt>{term}</dt>
      <dd>{empty ? "—" : value}</dd>
    </div>
  );
}

function DocLink({ label: text, url }: { label: string; url: string | null }) {
  if (!url) return null;
  return (
    <a
      className="doc-chip"
      href={url}
      target="_blank"
      rel="noreferrer"
      title={`Ouvrir : ${text}`}
    >
      <FileText size={15} />
      {text}
    </a>
  );
}

function SubSection({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="subsection">
      <div className="subsection-title">
        <Icon size={15} />
        {title}
      </div>
      {children}
    </div>
  );
}

/** Tous les champs situation CBS mappés sur le client (import Perfect). */
function CbsFieldsBlock({ client: c }: { client: Client }) {
  const estValide =
    c.cbs_est_valide === null || c.cbs_est_valide === undefined
      ? undefined
      : c.cbs_est_valide
        ? "Oui"
        : "Non";

  return (
    <SubSection icon={Landmark} title="Core Banking">
      <dl className="def-list two">
        <Row term="Matricule Core Banking" value={c.cbs_client_id} />
        <Row term="N° de compte (n° manuel)" value={c.cbs_account_number} />
        <Row term="Nom adhérent CBS" value={c.cbs_full_name} />
        <Row term="N° d'ordre CBS" value={c.cbs_order_number} />
        <Row term="Code point de service" value={c.cbs_point_of_service_id} />
        <Row term="Libellé point de service" value={c.cbs_point_of_service_name} />
        <Row
          term="Date d'inscription CBS"
          value={
            c.cbs_registration_date
              ? formatDate(c.cbs_registration_date)
              : undefined
          }
        />
        <Row
          term="Date de création CBS"
          value={
            c.cbs_creation_date ? formatDate(c.cbs_creation_date) : undefined
          }
        />
        <Row
          term="Limite de crédit CBS"
          value={
            c.cbs_credit_limit != null && c.cbs_credit_limit !== ""
              ? formatMoney(c.cbs_credit_limit)
              : undefined
          }
        />
        <Row term="Adhérent valide CBS" value={estValide} />
        <Row term="Identifiant externe CBS" value={c.cbs_external_id} />
        <Row term="Id profession CBS" value={c.cbs_profession_id} />
        <Row term="Id nationalité CBS" value={c.cbs_nationality_id} />
        <Row term="Id secteur d'activité CBS" value={c.cbs_sector_id} />
        <Row term="Id type client CBS" value={c.cbs_client_type_id} />
        <Row term="Id zone CBS" value={c.cbs_zone_id} />
        <Row term="Id produit épargne CBS" value={c.cbs_savings_product_id} />
        <Row
          term="Nombre de signatures CBS"
          value={
            c.cbs_signature_count != null
              ? String(c.cbs_signature_count)
              : undefined
          }
        />
        <Row
          term="Distance CBS"
          value={
            c.cbs_distance != null && c.cbs_distance !== ""
              ? String(c.cbs_distance)
              : undefined
          }
        />
        <Row term="Contexte réponse CBS" value={c.cbs_context} />
        <Row term="Message réponse CBS" value={c.cbs_message} />
        <Row
          term="Dernière synchronisation CBS"
          value={c.cbs_synced_at ? formatDate(c.cbs_synced_at) : undefined}
        />
      </dl>
    </SubSection>
  );
}

const ACTION_META: Record<
  string,
  { label: string; icon: LucideIcon; tone: string }
> = {
  CREATE: { label: "Création", icon: FilePlus2, tone: "success" },
  UPDATE: { label: "Modification", icon: FilePenLine, tone: "info" },
  DELETE: { label: "Suppression", icon: Trash2, tone: "danger" },
  WORKFLOW: { label: "Action workflow", icon: GitBranch, tone: "info" },
  INTEGRATION: { label: "Échange Core Banking", icon: Cable, tone: "muted" },
};

function InterventionHistory({ clientId }: { clientId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["client-audit", clientId],
    queryFn: async () =>
      (
        await api.get<Paginated<AuditLog>>("/audit-logs/", {
          params: { object_id: clientId, ordering: "-timestamp" },
        })
      ).data,
    enabled: !!clientId,
  });

  if (isLoading) return <Spinner />;
  const logs = data?.results ?? [];
  if (logs.length === 0)
    return <p className="muted small">Aucune intervention enregistrée.</p>;

  return (
    <ol className="timeline">
      {logs.map((log) => {
        const meta =
          ACTION_META[log.action] ?? {
            label: log.action,
            icon: History,
            tone: "muted",
          };
        const Icon = meta.icon;
        const changed =
          log.action === "UPDATE" && log.changes
            ? Object.keys(log.changes)
            : [];
        return (
          <li key={log.id} className="timeline-item">
            <span className={`timeline-dot tone-${meta.tone}`}>
              <Icon size={14} />
            </span>
            <div className="timeline-body">
              <div className="timeline-head">
                <strong>{meta.label}</strong>
                <span className="timeline-date">{formatDate(log.timestamp)}</span>
              </div>
              <div className="timeline-sub">
                par {log.user_display || "système"}
                {changed.length > 0 && (
                  <span className="muted">
                    {" "}
                    · {changed.length} champ(s) modifié(s)
                  </span>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ClientPortfolio({ client }: { client: Client }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const canViewCredits = hasAnyPerm(user, PERM_CREDITS);
  const canCreateCredit = hasAnyPerm(user, PERM_CREDIT_CREATE);
  const canViewGuarantees = hasAnyPerm(user, PERM_GUARANTEES);
  const canViewSureties =
    hasPerm(user, "sureties.view_suretyengagement") ||
    hasAnyPerm(user, PERM_SURETIES);
  const canViewDations = hasAnyPerm(user, PERM_DATIONS);
  const canInitiateDation = hasPerm(user, "guarantees.initiate_dationrequest");
  const canViewFormalizations = hasAnyPerm(user, PERM_FORMALIZATIONS);
  const canInitiateFormalization = hasPerm(
    user,
    "guarantees.initiate_guaranteeformalizationrequest",
  );
  const canViewReleases = hasAnyPerm(user, PERM_RELEASES);
  const canInitiateRelease = hasPerm(
    user,
    "guarantees.initiate_guaranteereleaserequest",
  );
  const canViewCollections = hasAnyPerm(user, PERM_COLLECTIONS);
  const canViewDocuments = hasAnyPerm(user, PERM_DOCUMENTS);

  const show =
    canViewCredits ||
    canViewGuarantees ||
    canViewSureties ||
    canViewDations ||
    canViewFormalizations ||
    canViewReleases ||
    canViewCollections ||
    canViewDocuments;

  const credits = useQuery({
    queryKey: ["credit-applications", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditApplication>>("/credit-applications/", {
          params: { client: client.id, page_size: 20 },
        })
      ).data,
    enabled: canViewCredits,
  });
  const guarantees = useQuery({
    queryKey: ["guarantees", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<Guarantee>>("/guarantees/", {
          params: { client: client.id, page_size: 20 },
        })
      ).data,
    enabled: canViewGuarantees,
  });
  const engagements = useQuery({
    queryKey: ["surety-engagements", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<SuretyEngagement>>("/surety-engagements/", {
          params: { client: client.id, page_size: 20 },
        })
      ).data,
    enabled: canViewSureties,
  });
  const dations = useQuery({
    queryKey: ["dation-requests", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<DationRequest>>("/dation-requests/", {
          params: { client: client.id, page_size: 20 },
        })
      ).data,
    enabled: canViewDations,
  });
  const formalizations = useQuery({
    queryKey: ["guarantee-formalizations", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<GuaranteeFormalizationRequest>>(
          "/guarantee-formalizations/",
          { params: { client: client.id, page_size: 20 } },
        )
      ).data,
    enabled: canViewFormalizations,
  });
  const releases = useQuery({
    queryKey: ["guarantee-releases", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<GuaranteeReleaseRequest>>(
          "/guarantee-releases/",
          { params: { client: client.id, page_size: 20 } },
        )
      ).data,
    enabled: canViewReleases,
  });
  const cases = useQuery({
    queryKey: ["collection-cases", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<CollectionCase>>("/collection-cases/", {
          params: { client: client.id, page_size: 20 },
        })
      ).data,
    enabled: canViewCollections,
  });
  const documents = useQuery({
    queryKey: ["ged-documents", "client", client.id],
    queryFn: async () =>
      (
        await api.get<Paginated<GedDocument>>("/documents/", {
          params: { client: client.id, page_size: 1 },
        })
      ).data,
    enabled: canViewDocuments,
  });

  if (!show) return null;

  return (
    <Card
      title={
        <>
          <Briefcase size={17} /> Portefeuille
        </>
      }
    >
      {canViewCredits && (
        <SubSection icon={FileText} title="Dossiers de crédit">
          {credits.data && credits.data.results.length > 0 ? (
            <ul className="link-list">
              {credits.data.results.map((app) => (
                <li
                  key={app.id}
                  className="row-clickable"
                  onClick={() => navigate(`/dossiers/${app.id}`)}
                >
                  <span>
                    <FileText size={14} /> {app.reference || app.id.slice(0, 8)}
                    {app.product_label ? (
                      <em className="muted small"> · {app.product_label}</em>
                    ) : null}
                  </span>
                  <span className="muted small">
                    {formatMoney(app.amount_requested, app.currency)}
                  </span>
                  {canViewCollections && app.collection_case_id ? (
                    <Link
                      className="muted small"
                      to={`/recouvrement/${app.collection_case_id}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {app.collection_stage_display || "Recouvrement"}
                    </Link>
                  ) : null}
                  <Badge
                    value={app.status}
                    label={app.status_display || app.status}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucun dossier de crédit.</p>
          )}
          <div className="row-actions">
            {canCreateCredit && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/dossiers/nouveau?client=${client.id}`}
              >
                <Plus size={15} />
                Nouveau dossier
              </Link>
            )}
            {(credits.data?.count ?? 0) > 0 && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/dossiers?client=${client.id}`}
              >
                Voir tous
              </Link>
            )}
          </div>
        </SubSection>
      )}

      {canViewGuarantees && (
        <SubSection icon={ShieldCheck} title="Garanties">
          {guarantees.data && guarantees.data.results.length > 0 ? (
            <ul className="link-list">
              {guarantees.data.results.map((g) => (
                <li
                  key={g.id}
                  className="row-clickable"
                  onClick={() => navigate(`/garanties/${g.id}`)}
                >
                  <span>
                    <ShieldCheck size={14} /> {g.reference || g.id.slice(0, 8)}
                    {g.type_display ? (
                      <em className="muted small"> · {g.type_display}</em>
                    ) : null}
                  </span>
                  {canViewCredits && g.application ? (
                    <Link
                      className="muted small"
                      to={`/dossiers/${g.application}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {g.application_reference || "Dossier"}
                    </Link>
                  ) : null}
                  {canViewCollections && g.collection_case_id ? (
                    <Link
                      className="muted small"
                      to={`/recouvrement/${g.collection_case_id}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {g.collection_stage_display || "Recouvrement"}
                    </Link>
                  ) : null}
                  <Badge value={g.status} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucune garantie.</p>
          )}
          {(guarantees.data?.count ?? 0) > 0 && (
            <Link
              className="btn btn-ghost btn-sm"
              to={`/garanties?client=${client.id}`}
            >
              Voir toutes
            </Link>
          )}
        </SubSection>
      )}

      {canViewSureties && (
        <SubSection icon={Scale} title="Cautions">
          {engagements.data && engagements.data.results.length > 0 ? (
            <ul className="link-list">
              {engagements.data.results.map((e) => (
                <li
                  key={e.id}
                  className="row-clickable"
                  onClick={() =>
                    navigate(`/dossiers/${e.application}/cautions/${e.surety}`)
                  }
                >
                  <span>
                    <Scale size={14} /> {e.surety_display || "Caution"}
                    {e.application_reference ? (
                      <em className="muted small">
                        {" "}
                        · {e.application_reference}
                      </em>
                    ) : null}
                  </span>
                  <span className="muted small">{formatMoney(e.amount)}</span>
                  <Badge
                    value={e.status}
                    label={e.status_display || e.status}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucun engagement de caution.</p>
          )}
        </SubSection>
      )}

      {canViewDations && (
        <SubSection icon={HandCoins} title="Dations">
          {dations.data && dations.data.results.length > 0 ? (
            <ul className="link-list">
              {dations.data.results.map((d) => (
                <li
                  key={d.id}
                  className="row-clickable"
                  onClick={() => navigate(`/dations/${d.id}`)}
                >
                  <span>
                    <HandCoins size={14} /> {d.reference || "Dation"}
                    {d.application_reference ? (
                      <em className="muted small">
                        {" "}
                        · {d.application_reference}
                      </em>
                    ) : null}
                  </span>
                  <Badge
                    value={d.status}
                    label={d.status_display || d.status}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucune dation.</p>
          )}
          <div className="row-actions">
            {canInitiateDation && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/dations/nouvelle?client=${client.id}`}
              >
                <Plus size={15} />
                Nouvelle dation
              </Link>
            )}
            {(dations.data?.count ?? 0) > 0 && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/dations?client=${client.id}`}
              >
                Voir toutes
              </Link>
            )}
          </div>
        </SubSection>
      )}

      {canViewFormalizations && (
        <SubSection icon={FileSignature} title="Formalisations">
          {formalizations.data && formalizations.data.results.length > 0 ? (
            <ul className="link-list">
              {formalizations.data.results.map((f) => (
                <li
                  key={f.id}
                  className="row-clickable"
                  onClick={() => navigate(`/formalisations/${f.id}`)}
                >
                  <span>
                    <FileSignature size={14} /> {f.reference || "Formalisation"}
                    {f.guarantee_reference ? (
                      <em className="muted small">
                        {" "}
                        · {f.guarantee_reference}
                      </em>
                    ) : null}
                  </span>
                  <Badge
                    value={f.status}
                    label={f.status_display || f.status}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucune formalisation.</p>
          )}
          <div className="row-actions">
            {canInitiateFormalization && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/formalisations/nouvelle?client=${client.id}`}
              >
                <Plus size={15} />
                Nouvelle formalisation
              </Link>
            )}
            {(formalizations.data?.count ?? 0) > 0 && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/formalisations?client=${client.id}`}
              >
                Voir toutes
              </Link>
            )}
          </div>
        </SubSection>
      )}

      {canViewReleases && (
        <SubSection icon={Unlock} title="Mains levées">
          {releases.data && releases.data.results.length > 0 ? (
            <ul className="link-list">
              {releases.data.results.map((r) => (
                <li
                  key={r.id}
                  className="row-clickable"
                  onClick={() => navigate(`/mains-levees/${r.id}`)}
                >
                  <span>
                    <Unlock size={14} /> {r.reference || "Main levée"}
                    {r.guarantee_reference ? (
                      <em className="muted small">
                        {" "}
                        · {r.guarantee_reference}
                      </em>
                    ) : null}
                  </span>
                  <Badge
                    value={r.status}
                    label={r.status_display || r.status}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucune main levée.</p>
          )}
          <div className="row-actions">
            {canInitiateRelease && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/mains-levees/nouvelle?client=${client.id}`}
              >
                <Plus size={15} />
                Nouvelle main levée
              </Link>
            )}
            {(releases.data?.count ?? 0) > 0 && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/mains-levees?client=${client.id}`}
              >
                Voir toutes
              </Link>
            )}
          </div>
        </SubSection>
      )}

      {canViewCollections && (
        <SubSection icon={CircleDollarSign} title="Recouvrement">
          {cases.data && cases.data.results.length > 0 ? (
            <ul className="link-list">
              {cases.data.results.map((c) => (
                <li
                  key={c.id}
                  className="row-clickable"
                  onClick={() => navigate(`/recouvrement/${c.id}`)}
                >
                  <span>
                    <CircleDollarSign size={14} />{" "}
                    {c.application_reference || "Dossier"}
                    {c.stage_display ? (
                      <em className="muted small"> · {c.stage_display}</em>
                    ) : null}
                  </span>
                  <span className="muted small">
                    {c.days_overdue} j · {formatMoney(c.overdue_amount)}
                  </span>
                  <Badge value={c.par_class} label={c.par_class_display} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucun dossier de recouvrement.</p>
          )}
          {(cases.data?.count ?? 0) > 0 && (
            <Link
              className="btn btn-ghost btn-sm"
              to={`/recouvrement?client=${client.id}`}
            >
              Voir tous
            </Link>
          )}
        </SubSection>
      )}

      {canViewDocuments && (
        <SubSection icon={FolderOpen} title="GED — Documents">
          <p className="muted small">
            {(documents.data?.count ?? 0) > 0
              ? `${documents.data?.count} document${(documents.data?.count ?? 0) > 1 ? "s" : ""} rattaché${(documents.data?.count ?? 0) > 1 ? "s" : ""} à ce client.`
              : "Aucun document indexé pour ce client."}
          </p>
          <Link
            className="btn btn-ghost btn-sm"
            to={`/documents?client=${client.id}`}
          >
            Voir les documents
          </Link>
        </SubSection>
      )}
    </Card>
  );
}

export function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const canChange = hasPerm(user, "clients.change_client");
  const canDelete = hasPerm(user, "clients.delete_client");

  const { data: c, isLoading, isError, refetch } = useQuery({
    queryKey: ["client", id],
    queryFn: async () => (await api.get<Client>(`/clients/${id}/`)).data,
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/clients/${id}/`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      navigate("/clients");
    },
  });

  if (isLoading) return <Spinner />;
  if (isError || !c) {
    return (
      <ErrorState
        message="Impossible de charger le client."
        onRetry={() => refetch()}
      />
    );
  }

  const isCorporate = c.client_type === "CORPORATE";
  const isLegalEntity =
    c.client_type === "CORPORATE" || c.client_type === "PROFESSIONAL";
  const fullName = `${c.first_name} ${c.last_name}`.trim();

  const bannerName = isLegalEntity
    ? c.company_name || c.display_name
    : fullName || c.display_name;

  return (
    <div className="page-shell client-detail-page">
      {confirmDelete && (
        <div className="confirm-bar">
          <span>
            <TriangleAlert size={17} />
            Confirmer la suppression définitive de <strong>{c.display_name}</strong> ?
          </span>
          <div className="row-actions">
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setConfirmDelete(false)}
              disabled={deleteMutation.isPending}
            >
              Annuler
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Suppression…" : "Oui, supprimer"}
            </button>
          </div>
        </div>
      )}

      {/* Bandeau : identité, actions et photo */}
      <div className="client-banner">
        <div className="client-banner-main">
          <div className="client-banner-info">
            <span className="client-banner-icon">
              {isLegalEntity ? <Building2 size={26} /> : <UserRound size={26} />}
            </span>
            <div className="client-banner-identity">
              <h2 className="client-banner-name">{bannerName}</h2>
              <p className="client-banner-ref">
                Matricule <code>{c.reference || "—"}</code>
              </p>
              <div className="client-banner-meta">
                <Badge
                  value={c.client_type}
                  label={label(CLIENT_LABELS.client_type, c.client_type)}
                />
                <Badge value={c.kyc_status} />
                <span className={`dot-status ${c.is_active ? "on" : "off"}`}>
                  {c.is_active ? "Actif" : "Inactif"}
                </span>
              </div>
            </div>
          </div>

          <div className="client-banner-actions">
            <Link className="btn btn-banner" to="/clients">
              <ArrowLeft size={15} />
              Retour
            </Link>
            {canChange && (
              <Link className="btn btn-banner" to={`/clients/${c.id}/modifier`}>
                <Pencil size={15} />
                Modifier
              </Link>
            )}
            {canDelete && (
              <button
                className="btn btn-banner btn-banner-danger"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 size={15} />
                Supprimer
              </button>
            )}
          </div>
        </div>

        <div className="client-photo-panel">
          {c.photo ? (
            <a
              className="client-photo-frame"
              href={c.photo}
              target="_blank"
              rel="noreferrer"
            >
              <img
                // Ne pas ajouter de query (?v=) : une URL MinIO présignée
                // serait invalidée (signature cassée) alors que le href marche.
                src={c.photo}
                alt="Photo du client"
              />
            </a>
          ) : (
            <div className="client-photo-frame client-photo-empty">
              <ImageOff size={26} />
              <span>Aucune photo</span>
            </div>
          )}
          <span className="client-photo-caption">Photo du client</span>
        </div>
      </div>

      <div className="detail-grid stacked client-detail-sections">
        {isLegalEntity ? (
          <Card
            title={
              <>
                <Building2 size={17} />{" "}
                {isCorporate
                  ? "Informations de l'entreprise"
                  : "Informations du groupement"}
              </>
            }
          >
            <SubSection
              icon={Building2}
              title={isCorporate ? "Entreprise" : "Groupement"}
            >
              <dl className="def-list two">
                <Row term="Raison sociale" value={c.company_name} />
                <Row term="Sigle" value={c.sigle} />
                <Row
                  term="Statut juridique"
                  value={
                    c.legal_form && label(CLIENT_LABELS.legal_form, c.legal_form)
                  }
                />
                <Row term="Numéro IFU" value={c.ifu} />
                <Row term="Numéro RCCM" value={c.rccm} />
              </dl>
              {(c.ifu_scan || c.rccm_scan) && (
                <div className="doc-row">
                  <DocLink label="Scan IFU" url={c.ifu_scan} />
                  <DocLink label="Scan RCCM" url={c.rccm_scan} />
                </div>
              )}
            </SubSection>

              <SubSection icon={Phone} title="Coordonnées">
              <dl className="def-list two">
                <Row term="Téléphone principal" value={c.phone} />
                <Row
                  term="Autres numéros"
                  value={
                    c.phones && c.phones.length > 0
                      ? c.phones.map((p) => p.number).join(" · ")
                      : undefined
                  }
                />
                <Row term="Email" value={c.email} />
                <Row term="Adresse" value={c.address} />
                <Row term="Siège social" value={c.head_office} />
                <Row term="Ville" value={c.city} />
                <Row term="Boîte postale" value={c.postal_box} />
              </dl>
            </SubSection>

            <CbsFieldsBlock client={c} />

            <SubSection icon={Contact} title="Gérant">
              <dl className="def-list two">
                <Row
                  term="Nom & prénom"
                  value={`${c.manager_first_name} ${c.manager_last_name}`.trim()}
                />
                <Row term="Téléphone" value={c.manager_phone} />
                <Row term="Email" value={c.manager_email} />
                <Row term="Adresse" value={c.manager_address} />
                <Row
                  term="Pièce d'identité"
                  value={
                    c.manager_id_document_type &&
                    `${label(CLIENT_LABELS.id_document_type, c.manager_id_document_type)} — ${c.manager_id_document_number}`
                  }
                />
              </dl>
              {c.manager_id_document_scan && (
                <div className="doc-row">
                  <DocLink label="Scan pièce du gérant" url={c.manager_id_document_scan} />
                </div>
              )}
            </SubSection>
          </Card>
        ) : (
          <>
            {/* Section fusionnée : Identité + Pièce + Coordonnées + Parents */}
            <Card
              title={
                <>
                  <User size={17} /> Informations personnelles
                </>
              }
            >
              <SubSection icon={User} title="Identité">
                <dl className="def-list two">
                  <Row
                    term="Civilité"
                    value={c.civility && label(CLIENT_LABELS.civility, c.civility)}
                  />
                  <Row term="Nom" value={c.last_name} />
                  <Row term="Prénoms" value={c.first_name} />
                  <Row term="Nom complet" value={fullName} />
                  <Row term="Date de naissance" value={formatDate(c.birth_date)} />
                  <Row term="Lieu / pays de naissance" value={c.birth_country} />
                  <Row term="Nationalité" value={c.nationality} />
                  <Row
                    term="Situation matrimoniale"
                    value={
                      c.marital_status &&
                      label(CLIENT_LABELS.marital_status, c.marital_status)
                    }
                  />
                  <Row term="Profession" value={c.profession} />
                </dl>
              </SubSection>

              <SubSection icon={IdCard} title="Pièce d'identité">
                <dl className="def-list two">
                  <Row
                    term="Type"
                    value={
                      c.id_document_type &&
                      label(CLIENT_LABELS.id_document_type, c.id_document_type)
                    }
                  />
                  <Row term="Numéro" value={c.national_id} />
                  <Row
                    term="Établie le"
                    value={
                      c.id_document_issue_date &&
                      formatDate(c.id_document_issue_date)
                    }
                  />
                  <Row
                    term="Expire le"
                    value={
                      c.id_document_expiry_date &&
                      formatDate(c.id_document_expiry_date)
                    }
                  />
                </dl>
                {c.id_document_scan && (
                  <div className="doc-row">
                    <DocLink label="Scan de la pièce" url={c.id_document_scan} />
                  </div>
                )}
              </SubSection>

              <SubSection icon={Phone} title="Coordonnées">
                <dl className="def-list two">
                  <Row term="Téléphone principal" value={c.phone} />
                  <Row
                    term="Autres numéros"
                    value={
                      c.phones && c.phones.length > 0
                        ? c.phones.map((p) => p.number).join(" · ")
                        : undefined
                    }
                  />
                  <Row term="Email" value={c.email} />
                  <Row term="Adresse" value={c.address} />
                  <Row term="Siège social" value={c.head_office} />
                  <Row term="Ville" value={c.city} />
                  <Row term="Boîte postale" value={c.postal_box} />
                  <Row term="Pays" value={c.country} />
                </dl>
              </SubSection>

              <CbsFieldsBlock client={c} />

              <SubSection icon={Users} title="Parents">
                <dl className="def-list two">
                  <Row
                    term="Père"
                    value={`${c.father_first_name} ${c.father_last_name}`.trim()}
                  />
                  <Row
                    term="Mère"
                    value={`${c.mother_first_name} ${c.mother_last_name}`.trim()}
                  />
                </dl>
              </SubSection>
            </Card>

            <Card
              title={
                <>
                  <Heart size={17} /> Conjoint
                </>
              }
            >
              <dl className="def-list two">
                <Row
                  term="Nom & prénom"
                  value={`${c.spouse_first_name} ${c.spouse_last_name}`.trim()}
                />
                <Row term="Téléphone" value={c.spouse_phone} />
                <Row term="Profession" value={c.spouse_profession} />
              </dl>
            </Card>
          </>
        )}
      </div>

      <ClientPortfolio client={c} />

      {/* Historique des interventions — section discrète */}
      <section className="history-panel">
        <div className="history-head">
          <History size={16} />
          <span>Historique des interventions</span>
        </div>
        <InterventionHistory clientId={c.id} />
      </section>
    </div>
  );
}
