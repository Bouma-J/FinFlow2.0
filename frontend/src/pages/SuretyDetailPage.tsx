import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  Contact,
  FileText,
  HandCoins,
  IdCard,
  ImageOff,
  Pencil,
  Phone,
  Trash2,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import { CLIENT_LABELS, type Surety } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import { PERM_CREDITS } from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import { SuretyEngagementActions } from "@/components/SuretyEngagementActions";
import { Badge, Card, ErrorState, Spinner, formatDate, formatMoney } from "@/components/ui";

function label(map: Record<string, string>, key: string) {
  return map[key] || key || "—";
}

function Row({ term, value }: { term: string; value?: ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <dt>{term}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function DocLink({ label: text, url }: { label: string; url: string | null }) {
  if (!url) return null;
  return (
    <a className="doc-chip" href={url} target="_blank" rel="noreferrer">
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
  icon: typeof UserRound;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="page-shell subsection">
      <div className="subsection-title">
        <Icon size={15} />
        {title}
      </div>
      {children}
    </div>
  );
}

export function SuretyDetailPage({
  manageable = false,
}: {
  manageable?: boolean;
}) {
  const { id, appId } = useParams<{ id: string; appId?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const canViewCredits = hasAnyPerm(user, PERM_CREDITS);
  const backTo = appId && canViewCredits ? `/dossiers/${appId}` : "/cautions";
  const canEdit = manageable && hasPerm(user, "sureties.change_surety");
  const canDelete = manageable && hasPerm(user, "sureties.delete_surety");
  const canManageEng = hasPerm(user, "sureties.change_suretyengagement");
  const canContracts = hasPerm(user, "contracts.add_generatedcontract");

  const { data: s, isLoading, isError, refetch } = useQuery({
    queryKey: ["surety", id],
    queryFn: async () => (await api.get<Surety>(`/sureties/${id}/`)).data,
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/sureties/${id}/`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sureties"] });
      navigate("/cautions");
    },
  });

  if (isLoading) return <Spinner />;
  if (isError || !s) {
    return (
      <ErrorState
        message="Impossible de charger la caution."
        onRetry={() => refetch()}
      />
    );
  }

  const isMoral = s.surety_type === "MORAL";
  const typeLabel = isMoral ? "personne morale" : "personne physique";
  const BannerIcon = isMoral ? Building2 : UserRound;

  return (
    <div className="page-shell detail-banner-page">
      {confirmDelete && (
        <div className="confirm-bar">
          <span>
            <TriangleAlert size={17} />
            Confirmer la suppression définitive de <strong>{s.display_name}</strong> ?
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

      <div className="client-banner">
        <div className="client-banner-main">
          <div className="client-banner-info">
            <span className="client-banner-icon">
              <BannerIcon size={26} />
            </span>
            <div className="client-banner-identity">
              <h2 className="client-banner-name">{s.display_name}</h2>
              <p className="client-banner-ref">
                Caution <code>{typeLabel}</code>
                {appId && canViewCredits && (
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    className="client-banner-inline-link"
                    to={`/dossiers/${appId}`}
                    fallback={null}
                  >
                    · Dossier crédit
                  </PermLink>
                )}
              </p>
              <div className="client-banner-meta">
                <Badge value="ACTIVE" label={isMoral ? "Entreprise" : "Caution"} />
                {s.activity && <code>{s.activity}</code>}
                <span className={`dot-status ${s.is_active ? "on" : "off"}`}>
                  {s.is_active ? "Active" : "Inactive"}
                </span>
                <span className="muted">
                  Plafond {formatMoney(s.commitment_ceiling)} · Engagé{" "}
                  {formatMoney(s.total_committed)} · Dispo{" "}
                  {formatMoney(s.available_ceiling)}
                </span>
              </div>
            </div>
          </div>

          <div className="client-banner-actions">
            <Link className="btn btn-banner" to={backTo}>
              <ArrowLeft size={15} />
              Retour
            </Link>
            {canEdit && (
              <Link
                className="btn btn-banner btn-banner-primary"
                to={`/cautions/${s.id}/modifier`}
              >
                <Pencil size={15} />
                Modifier
              </Link>
            )}
            {canDelete && (
              <button
                type="button"
                className="btn btn-banner btn-banner-danger"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 size={15} />
                Supprimer
              </button>
            )}
          </div>
        </div>

        {!isMoral && (
          <div className="client-photo-panel">
            {s.photo ? (
              <a href={s.photo} target="_blank" rel="noreferrer">
                <img src={s.photo} alt={`Photo de ${s.display_name}`} />
              </a>
            ) : (
              <div className="client-photo-empty">
                <ImageOff size={26} />
                <span>Aucune photo</span>
              </div>
            )}
            <span className="client-photo-caption">Photo de la caution</span>
          </div>
        )}
      </div>

      <div className="detail-sections">
        <div className="detail-sections-row">
          <Card
            title={
              <>
                <HandCoins size={17} /> Plafond &amp; risque
              </>
            }
          >
            <dl className="def-list two">
              <div>
                <dt>Plafond</dt>
                <dd>{formatMoney(s.commitment_ceiling)}</dd>
              </div>
              <div>
                <dt>Engagé (actif + appelé)</dt>
                <dd>{formatMoney(s.total_committed)}</dd>
              </div>
              <div>
                <dt>Disponible</dt>
                <dd>{formatMoney(s.available_ceiling)}</dd>
              </div>
              <div>
                <dt>Engagements</dt>
                <dd>{s.engagements?.length ?? 0}</dd>
              </div>
            </dl>
          </Card>

          <Card
            title={
              <>
                <HandCoins size={17} /> Historique des engagements
              </>
            }
          >
            {(s.engagements?.length ?? 0) === 0 ? (
              <p className="muted small">Aucun engagement enregistré.</p>
            ) : (
              <ul className="link-list stacked">
                {(s.engagements ?? []).map((e) => (
                  <li
                    key={e.id}
                    className="row-clickable"
                    style={{ flexDirection: "column", alignItems: "stretch" }}
                    onClick={() => navigate(`/dossiers/${e.application}`)}
                  >
                    <div className="row-actions" style={{ width: "100%" }}>
                      <span>
                        <PermLink
                          user={user}
                          anyOf={PERM_CREDITS}
                          to={`/dossiers/${e.application}`}
                          onClick={(ev) => ev.stopPropagation()}
                        >
                          {e.application_reference || e.application.slice(0, 8)}
                        </PermLink>
                        {e.client_display ? (
                          <em className="muted small"> · {e.client_display}</em>
                        ) : null}
                      </span>
                      <span className="muted small">
                        {formatDate(e.created_at)}
                      </span>
                    </div>
                    <div onClick={(ev) => ev.stopPropagation()}>
                      <SuretyEngagementActions
                        engagement={e}
                        canManage={canManageEng}
                        canContracts={canContracts}
                        invalidateKeys={[["surety", id]]}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="detail-sections-row full">
        <Card
          title={
            <>
              <BannerIcon size={17} /> Informations de la caution
            </>
          }
        >
          {isMoral ? (
            <>
              <SubSection icon={Building2} title="Entreprise">
                <dl className="def-list two">
                  <Row term="Raison sociale" value={s.company_name || s.name} />
                  <Row
                    term="Forme juridique"
                    value={
                      s.legal_form &&
                      label(CLIENT_LABELS.legal_form, s.legal_form)
                    }
                  />
                  <Row term="N° IFU" value={s.ifu} />
                  <Row term="N° RCCM" value={s.rccm || s.identifier} />
                  <Row term="Activité" value={s.activity} />
                  <Row term="Ville" value={s.city} />
                </dl>
                {(s.ifu_scan || s.rccm_scan) && (
                  <div className="doc-row">
                    <DocLink label="Scan IFU" url={s.ifu_scan} />
                    <DocLink label="Scan RCCM" url={s.rccm_scan} />
                  </div>
                )}
              </SubSection>

              <SubSection icon={Contact} title="Gérant">
                <dl className="def-list two">
                  <Row term="Nom" value={s.manager_last_name} />
                  <Row term="Prénom" value={s.manager_first_name} />
                  <Row term="Poste" value={s.manager_position} />
                  <Row term="Téléphone" value={s.manager_phone} />
                  <Row term="Email" value={s.manager_email} />
                  <Row term="Adresse" value={s.manager_address} />
                  <Row
                    term="Date de naissance"
                    value={s.manager_birth_date && formatDate(s.manager_birth_date)}
                  />
                  <Row term="Pays de naissance" value={s.manager_birth_country} />
                  <Row term="Ville de naissance" value={s.manager_birth_city} />
                  <Row
                    term="Type de pièce"
                    value={
                      s.manager_id_document_type &&
                      label(CLIENT_LABELS.id_document_type, s.manager_id_document_type)
                    }
                  />
                  <Row term="N° de pièce" value={s.manager_id_document_number} />
                  <Row
                    term="Établie le"
                    value={
                      s.manager_id_document_issue_date &&
                      formatDate(s.manager_id_document_issue_date)
                    }
                  />
                  <Row
                    term="Expire le"
                    value={
                      s.manager_id_document_expiry_date &&
                      formatDate(s.manager_id_document_expiry_date)
                    }
                  />
                </dl>
                {s.manager_id_document_scan && (
                  <div className="doc-row">
                    <DocLink
                      label="Scan pièce du gérant"
                      url={s.manager_id_document_scan}
                    />
                  </div>
                )}
              </SubSection>
            </>
          ) : (
            <>
              <SubSection icon={UserRound} title="Identité">
                <dl className="def-list two">
                  <Row term="Nom" value={s.last_name} />
                  <Row term="Prénom" value={s.first_name} />
                  <Row term="Date de naissance" value={formatDate(s.birth_date)} />
                  <Row term="Pays de naissance" value={s.birth_country} />
                  <Row term="Activité" value={s.activity} />
                  <Row
                    term="Estimation de revenu"
                    value={s.estimated_income && formatMoney(s.estimated_income)}
                  />
                </dl>
              </SubSection>

              <SubSection icon={IdCard} title="Pièce d'identité">
                <dl className="def-list two">
                  <Row
                    term="Type"
                    value={
                      s.id_document_type &&
                      label(CLIENT_LABELS.id_document_type, s.id_document_type)
                    }
                  />
                  <Row term="Numéro" value={s.national_id} />
                  <Row
                    term="Établie le"
                    value={
                      s.id_document_issue_date && formatDate(s.id_document_issue_date)
                    }
                  />
                  <Row
                    term="Expire le"
                    value={
                      s.id_document_expiry_date && formatDate(s.id_document_expiry_date)
                    }
                  />
                </dl>
                {s.id_document_scan && (
                  <div className="doc-row">
                    <DocLink label="Scan de la pièce" url={s.id_document_scan} />
                  </div>
                )}
              </SubSection>
            </>
          )}

          <SubSection icon={Phone} title="Coordonnées">
            <dl className="def-list two">
              <Row term="Téléphone principal" value={s.phone} />
              {s.phones && s.phones.length > 0 && (
                <Row
                  term="Autres numéros"
                  value={s.phones.map((p) => p.number).join(" · ")}
                />
              )}
              <Row term="Email" value={s.email} />
              <Row term="Adresse" value={s.address} />
              {isMoral && <Row term="Ville" value={s.city} />}
            </dl>
          </SubSection>

          <SubSection icon={FileText} title="Documents complémentaires">
            {s.documents && s.documents.length > 0 ? (
              <div className="doc-row">
                {s.documents.map((d) => (
                  <DocLink key={d.id} label={d.title || "Document"} url={d.file} />
                ))}
              </div>
            ) : (
              <p className="muted small">Aucun document complémentaire.</p>
            )}
          </SubSection>
        </Card>
        </div>
      </div>
    </div>
  );
}
