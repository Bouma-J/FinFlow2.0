import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Banknote,
  Car,
  FilePenLine,
  FileText,
  Gem,
  History,
  Images,
  Info,
  CircleDollarSign,
  Landmark,
  ShieldCheck,
  ShieldOff,
  Stamp,
  Trash2,
  Unlock,
  UploadCloud,
  User,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import {
  GUARANTEE_LABELS,
  type Guarantee,
  type GuaranteeFormalizationRequest,
  type Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import {
  PERM_CLIENTS,
  PERM_COLLECTIONS,
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_FORMALIZATIONS,
  PERM_RELEASES,
  PERM_SURETIES,
} from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import {
  Badge,
  Card,
  ErrorState,
  Spinner,
  formatDate,
  formatMoney,
} from "@/components/ui";

const OPEN_FORM_STATUSES = [
  "DRAFT",
  "IN_PROGRESS",
  "IN_APPROVAL",
  "RETURNED",
  "APPROVED",
];

const GENERIC_TYPES = new Set([
  "LIEN",
  "DEPOSIT",
  "BANK_GUARANTEE",
  "DATION",
  "JOINT",
  "OTHER",
]);

function lbl(map: Record<string, string>, key: string) {
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

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <Card
      title={
        <>
          <Icon size={17} /> {title}
        </>
      }
    >
      {children}
    </Card>
  );
}

function DocChip({ label, href }: { label: string; href: string | null }) {
  if (!href) return null;
  return (
    <a className="doc-chip" href={href} target="_blank" rel="noreferrer">
      <FileText size={15} />
      {label}
    </a>
  );
}

export function GuaranteeDetailPage({
  manageable = false,
}: {
  manageable?: boolean;
}) {
  const { id, appId } = useParams<{ id: string; appId?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();

  const { data: g, isLoading, isError, refetch } = useQuery({
    queryKey: ["guarantee", id],
    queryFn: async () => (await api.get<Guarantee>(`/guarantees/${id}/`)).data,
    enabled: !!id,
  });

  const openFormalization = useQuery({
    queryKey: ["guarantee-formalizations", "open", id],
    queryFn: async () => {
      if (g?.open_formalization_id) {
        return {
          id: g.open_formalization_id,
          status: "IN_PROGRESS",
        } as Pick<GuaranteeFormalizationRequest, "id" | "status">;
      }
      const data = (
        await api.get<Paginated<GuaranteeFormalizationRequest>>(
          "/guarantee-formalizations/",
          { params: { guarantee: id, page_size: 10 } },
        )
      ).data;
      return (
        data.results.find((r) => OPEN_FORM_STATUSES.includes(r.status)) ?? null
      );
    },
    enabled: !!id && !!g,
    retry: false,
  });

  const deleteMutation = useMutation({
    mutationFn: async () => api.delete(`/guarantees/${id}/`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["guarantees"] });
      navigate("/garanties");
    },
  });

  if (isLoading) return <Spinner />;
  if (isError || !g) {
    return (
      <ErrorState
        message="Impossible de charger la garantie."
        onRetry={() => refetch()}
      />
    );
  }

  const canViewFormalizations = hasAnyPerm(user, PERM_FORMALIZATIONS);
  const canViewDations = hasAnyPerm(user, PERM_DATIONS);
  const canViewReleases = hasAnyPerm(user, PERM_RELEASES);
  const canViewCollections = hasAnyPerm(user, PERM_COLLECTIONS);
  const canViewCredits = hasAnyPerm(user, PERM_CREDITS);
  const backTo =
    appId && canViewCredits ? `/dossiers/${appId}` : "/garanties";
  const isMortgage = g.guarantee_type === "MORTGAGE";
  const isPledge = g.guarantee_type === "PLEDGE";
  const isVehicle = isPledge && g.pledge_category === "VEHICLE";
  const isValuable = isPledge && g.pledge_category === "VALUABLE";
  const isFinancial = g.guarantee_type === "FINANCIAL";
  const isGeneric = GENERIC_TYPES.has(g.guarantee_type);
  const photos = g.photos ?? [];
  const movements = g.movements ?? [];
  const canEdit = manageable && hasPerm(user, "guarantees.change_guarantee");
  const canDelete = manageable && hasPerm(user, "guarantees.delete_guarantee");
  const busy = g.process_busy ?? null;
  const canRelease =
    g.status === "ACTIVE" &&
    !busy &&
    hasPerm(user, "guarantees.initiate_guaranteereleaserequest");
  const canFormalize =
    g.status === "ACTIVE" &&
    !!g.application &&
    !busy &&
    !g.formalized_at &&
    hasPerm(user, "guarantees.initiate_guaranteeformalizationrequest");
  const openFormId =
    (busy?.kind === "FORMALIZATION" ? busy.id : null) ||
    openFormalization.data?.id ||
    g.open_formalization_id ||
    null;
  const openDationId =
    (busy?.kind === "DATION" ? busy.id : null) || g.open_dation_id || null;
  const openReleaseId =
    (busy?.kind === "RELEASE" ? busy.id : null) || g.open_release_id || null;
  const completedDationId = g.completed_dation_id || null;
  const originDationId = g.origin_dation_id || null;
  const canProposeDation =
    g.status === "ACTIVE" &&
    !busy &&
    hasPerm(user, "guarantees.initiate_dationrequest");

  const scanEntries: { label: string; href: string | null }[] = [
    { label: "Scan du document", href: g.document_scan },
    { label: "Rapport d'expertise", href: g.expertise_report_scan },
    { label: "Contrat de bail", href: g.lease_contract_scan },
    {
      label: "Certificat de situation juridique",
      href: g.legal_situation_certificate_scan,
    },
    { label: "Carte grise", href: g.registration_card_scan },
    { label: "Expertise mécanique", href: g.mechanical_expertise_scan },
    { label: "Visite technique", href: g.technical_inspection_scan },
    { label: "Assurance", href: g.insurance_scan },
    { label: "Facture d'achat", href: g.purchase_invoice_scan },
    { label: "Certificat d'expertise", href: g.expertise_certificate_scan },
    {
      label: "Certificat d'origine / facture",
      href: g.origin_certificate_scan,
    },
    { label: "Acte de nantissement / blocage", href: g.pledge_deed_scan },
  ];
  const hasTypedScans = scanEntries.some((s) => !!s.href);
  const hasFreeDocs = (g.documents?.length ?? 0) > 0;

  function remove() {
    if (
      window.confirm(
        "Supprimer définitivement cette garantie ? Cette action est irréversible.",
      )
    ) {
      deleteMutation.mutate();
    }
  }

  return (
    <div className="page-shell detail-banner-page">
      <div className="client-banner">
        <div className="client-banner-main">
          <div className="client-banner-info">
            <span className="client-banner-icon">
              <ShieldCheck size={26} />
            </span>
            <div className="client-banner-identity">
              <h2 className="client-banner-name">
                {g.type_display || "Garantie"}
              </h2>
              <p className="client-banner-ref">
                Garantie <code>{g.reference || g.id.slice(0, 8)}</code>
                {isPledge && g.pledge_category && (
                  <span className="muted">
                    {" "}
                    · {lbl(GUARANTEE_LABELS.pledge_category, g.pledge_category)}
                  </span>
                )}
                {g.application && canViewCredits && (
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    className="client-banner-inline-link"
                    to={`/dossiers/${g.application}`}
                    fallback={
                      g.application_reference ? (
                        <span className="muted">
                          · Crédit {g.application_reference}
                        </span>
                      ) : null
                    }
                  >
                    · Dossier crédit{" "}
                    {g.application_reference || g.application.slice(0, 8)}
                  </PermLink>
                )}
              </p>
              <div className="client-banner-meta">
                <Badge
                  value={g.status}
                  label={
                    g.status_display ||
                    lbl(GUARANTEE_LABELS.status, g.status)
                  }
                />
                {openFormId && (
                  <Badge value="IN_PROGRESS" label="Formalisation en cours" />
                )}
                {g.formalized_at && <Badge value="OK" label="Formalisée" />}
                {completedDationId && (
                  <Badge value="REALIZED" label="Réalisée par dation" />
                )}
                {originDationId && (
                  <Badge value="DATION" label="Issue d'une dation" />
                )}
                <span className="muted">
                  Valeur actualisée : {formatMoney(g.current_value)}
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
                className="btn btn-banner"
                to={`/garanties/${id}/modifier`}
              >
                <FilePenLine size={15} />
                Modifier
              </Link>
            )}
            {canFormalize && (
              <Link
                className="btn btn-banner btn-banner-primary"
                to={`/formalisations/nouvelle?client=${g.client}&application=${g.application}&guarantee=${g.id}`}
              >
                <Stamp size={15} />
                Formaliser
              </Link>
            )}
            {canViewFormalizations && openFormId && (
              <Link
                className="btn btn-banner"
                to={`/formalisations/${openFormId}`}
              >
                <Stamp size={15} />
                Voir formalisation
              </Link>
            )}
            {canViewCollections && g.collection_case_id && (
              <Link
                className="btn btn-banner"
                to={`/recouvrement/${g.collection_case_id}`}
              >
                <CircleDollarSign size={15} />
                Recouvrement
                {g.collection_stage_display
                  ? ` · ${g.collection_stage_display}`
                  : ""}
              </Link>
            )}
            {canViewDations && openDationId && (
              <Link className="btn btn-banner" to={`/dations/${openDationId}`}>
                <Unlock size={15} />
                Voir dation
              </Link>
            )}
            {canViewReleases && openReleaseId && (
              <Link
                className="btn btn-banner"
                to={`/mains-levees/${openReleaseId}`}
              >
                <ShieldOff size={15} />
                Voir main levée
              </Link>
            )}
            {canViewDations && completedDationId && (
              <Link
                className="btn btn-banner"
                to={`/dations/${completedDationId}`}
              >
                <Unlock size={15} />
                Voir la dation de réalisation
              </Link>
            )}
            {canViewDations && originDationId && (
              <Link
                className="btn btn-banner"
                to={`/dations/${originDationId}`}
              >
                <Unlock size={15} />
                Dation d&apos;origine
              </Link>
            )}
            {canProposeDation && (
              <Link
                className="btn btn-banner"
                to={`/dations/nouvelle?client=${g.client}&guarantee=${g.id}${
                  g.application ? `&application=${g.application}` : ""
                }`}
              >
                <Unlock size={15} />
                Proposer dation
              </Link>
            )}
            {canRelease && (
              <Link
                className="btn btn-banner btn-banner-primary"
                to={`/mains-levees/nouvelle?client=${g.client}&guarantee=${g.id}${
                  g.application ? `&application=${g.application}` : ""
                }`}
              >
                <ShieldOff size={15} />
                Main levée
              </Link>
            )}
            {canDelete && (
              <button
                type="button"
                className="btn btn-banner btn-banner-danger"
                onClick={remove}
                disabled={deleteMutation.isPending}
              >
                <Trash2 size={15} />
                Supprimer
              </button>
            )}
          </div>
        </div>
      </div>

      {busy && (
        <div className="callout callout-warning">
          {busy.message}{" "}
          {busy.kind === "DATION" && canViewDations && (
            <Link to={`/dations/${busy.id}`}>Voir la dation</Link>
          )}
          {busy.kind === "FORMALIZATION" && canViewFormalizations && (
            <Link to={`/formalisations/${busy.id}`}>Voir la formalisation</Link>
          )}
          {busy.kind === "RELEASE" && canViewReleases && (
            <Link to={`/mains-levees/${busy.id}`}>Voir la main levée</Link>
          )}
        </div>
      )}

      <div className="detail-row">
        <Section icon={Info} title="Identification">
          <dl className="def-list two">
            <Row term="Référence" value={g.reference || "—"} />
            <Row term="Type" value={g.type_display} />
            {isPledge && (
              <Row
                term="Catégorie de gage"
                value={
                  g.pledge_category
                    ? lbl(GUARANTEE_LABELS.pledge_category, g.pledge_category)
                    : undefined
                }
              />
            )}
            <Row
              term="Statut"
              value={
                g.status_display || lbl(GUARANTEE_LABELS.status, g.status)
              }
            />
            <Row
              term="Client"
              value={
                g.client ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_CLIENTS}
                    to={`/clients/${g.client}`}
                  >
                    {g.client_display || "Voir le client"}
                  </PermLink>
                ) : (
                  g.client_display
                )
              }
            />
            <Row
              term="Dossier de crédit"
              value={
                g.application ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    to={`/dossiers/${g.application}`}
                  >
                    {g.application_reference || "Voir le dossier"}
                  </PermLink>
                ) : undefined
              }
            />
            <Row
              term="Recouvrement"
              value={
                g.collection_case_id ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_COLLECTIONS}
                    to={`/recouvrement/${g.collection_case_id}`}
                  >
                    {g.collection_stage_display || "Voir le dossier"}
                  </PermLink>
                ) : undefined
              }
            />
            <Row
              term="Formalisation"
              value={
                openFormId ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_FORMALIZATIONS}
                    to={`/formalisations/${openFormId}`}
                  >
                    En cours
                  </PermLink>
                ) : g.formalized_at ? (
                  "Formalisée"
                ) : undefined
              }
            />
            <Row
              term="Main levée"
              value={
                openReleaseId ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_RELEASES}
                    to={`/mains-levees/${openReleaseId}`}
                  >
                    En cours
                  </PermLink>
                ) : undefined
              }
            />
            <Row
              term="Dation en cours"
              value={
                openDationId ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_DATIONS}
                    to={`/dations/${openDationId}`}
                  >
                    Voir la dation
                  </PermLink>
                ) : undefined
              }
            />
            <Row
              term="Réalisée par"
              value={
                completedDationId ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_DATIONS}
                    to={`/dations/${completedDationId}`}
                  >
                    Voir la dation
                  </PermLink>
                ) : undefined
              }
            />
            <Row
              term="Issue de la dation"
              value={
                originDationId ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_DATIONS}
                    to={`/dations/${originDationId}`}
                  >
                    Voir la dation
                  </PermLink>
                ) : undefined
              }
            />
            <Row term="Agence" value={g.agency_name} />
            <Row term="Propriétaires" value={g.owners} />
            <Row
              term="Reconduite depuis"
              value={
                g.renewed_from ? (
                  <Link to={`/garanties/${g.renewed_from}`}>
                    {g.renewed_from_reference || "Garantie d'origine"}
                  </Link>
                ) : undefined
              }
            />
            <Row
              term="Créée le"
              value={g.created_at && formatDate(g.created_at)}
            />
            <Row
              term="Modifiée le"
              value={g.updated_at && formatDate(g.updated_at)}
            />
          </dl>
          {g.description && (
            <div style={{ marginTop: 12 }}>
              <h4 className="section-subtitle">Description</h4>
              <p className="prose">{g.description}</p>
            </div>
          )}
        </Section>

        <Section icon={Banknote} title="Valorisation & assurance">
          <dl className="def-list two">
            <Row
              term="Valeur d'expertise"
              value={
                g.expertise_value != null && g.expertise_value !== ""
                  ? formatMoney(g.expertise_value)
                  : undefined
              }
            />
            <Row
              term="Valeur actualisée"
              value={
                g.current_value != null && g.current_value !== ""
                  ? formatMoney(g.current_value)
                  : undefined
              }
            />
            <Row
              term="Valeur à considérer"
              value={
                g.value_to_consider != null && g.value_to_consider !== ""
                  ? formatMoney(g.value_to_consider)
                  : undefined
              }
            />
            <Row
              term="Taux de couverture (LTV)"
              value={
                g.ltv_ratio
                  ? `${(Number(g.ltv_ratio) * 100).toFixed(0)} %`
                  : undefined
              }
            />
            <Row
              term="Date d'expertise"
              value={g.expertise_date && formatDate(g.expertise_date)}
            />
            <Row
              term="Dernière valorisation"
              value={
                g.last_valuation_date && formatDate(g.last_valuation_date)
              }
            />
            <Row term="Cabinet d'expertise" value={g.expertise_firm} />
            <Row term="Nom de l'expert" value={g.expert_name} />
            <Row term="Référence du rapport" value={g.expertise_reference} />
            <Row term="Bien assuré" value={g.is_insured ? "Oui" : "Non"} />
            <Row term="Réf. assurance" value={g.insurance_reference} />
          </dl>
        </Section>

        <Section icon={User} title="Propriété du bien">
          <dl className="def-list two">
            <Row
              term="Appartient au client demandeur"
              value={g.belongs_to_applicant === false ? "Non" : "Oui"}
            />
            {g.belongs_to_applicant === false && (
              <Row
                term="Caution (propriétaire)"
                value={
                  g.surety ? (
                    <PermLink
                      user={user}
                      anyOf={PERM_SURETIES}
                      to={`/cautions/${g.surety}`}
                    >
                      {g.surety_display || "Voir la caution"}
                    </PermLink>
                  ) : (
                    g.surety_display
                  )
                }
              />
            )}
            <Row term="Nom du propriétaire" value={g.owner_last_name} />
            <Row term="Prénom du propriétaire" value={g.owner_first_name} />
            <Row
              term="Situation matrimoniale"
              value={
                g.owner_marital_status
                  ? lbl(
                      GUARANTEE_LABELS.marital_status,
                      g.owner_marital_status,
                    )
                  : undefined
              }
            />
            <Row
              term="Régime matrimonial"
              value={
                g.matrimonial_regime
                  ? lbl(
                      GUARANTEE_LABELS.matrimonial_regime,
                      g.matrimonial_regime,
                    )
                  : undefined
              }
            />
          </dl>
        </Section>

        {(g.formalized_at ||
          g.registration_number ||
          g.registration_date ||
          g.registration_authority) && (
          <Section icon={Stamp} title="Constitution juridique">
            <dl className="def-list two">
              <Row
                term="Formalisée le"
                value={g.formalized_at && formatDate(g.formalized_at)}
              />
              <Row term="N° d'enregistrement" value={g.registration_number} />
              <Row
                term="Date d'enregistrement"
                value={
                  g.registration_date && formatDate(g.registration_date)
                }
              />
              <Row term="Organisme" value={g.registration_authority} />
            </dl>
            <p className="muted small" style={{ marginTop: 8 }}>
              La formalisation est parallèle au crédit et ne bloque pas le
              mise en place.
            </p>
          </Section>
        )}

        {isMortgage && (
          <Section icon={Landmark} title="Bien immobilier">
            <dl className="def-list two">
              <Row
                term="Type de document"
                value={
                  g.document_type
                    ? lbl(GUARANTEE_LABELS.document_type, g.document_type)
                    : undefined
                }
              />
              <Row term="Numéro du document" value={g.document_number} />
              <Row
                term="Date d'établissement"
                value={
                  g.document_issue_date && formatDate(g.document_issue_date)
                }
              />
              <Row
                term="Date de validité"
                value={
                  g.document_validity_date && formatDate(g.document_validity_date)
                }
              />
              <Row term="Adresse du bien" value={g.address} />
              <Row
                term="Statut d'occupation"
                value={
                  g.occupancy_status
                    ? lbl(GUARANTEE_LABELS.occupancy_status, g.occupancy_status)
                    : undefined
                }
              />
            </dl>
          </Section>
        )}

        {isVehicle && (
          <Section icon={Car} title="Moyen roulant">
            <dl className="def-list two">
              <Row term="Numéro de châssis" value={g.chassis_number} />
              <Row
                term="Type de document"
                value={
                  g.document_type
                    ? lbl(GUARANTEE_LABELS.document_type, g.document_type)
                    : undefined
                }
              />
              <Row term="Numéro du document" value={g.document_number} />
              <Row
                term="Date d'établissement"
                value={
                  g.document_issue_date && formatDate(g.document_issue_date)
                }
              />
              <Row
                term="Date de validité"
                value={
                  g.document_validity_date && formatDate(g.document_validity_date)
                }
              />
              <Row term="Numéro du moteur" value={g.engine_number} />
              <Row term="Marque" value={g.brand} />
              <Row term="Modèle" value={g.model_name} />
              <Row term="Immatriculation" value={g.registration} />
              <Row term="Puissance" value={g.power} />
              <Row
                term="Année de 1re mise en circulation"
                value={g.first_registration_year ?? undefined}
              />
              <Row
                term="Date d'acquisition"
                value={g.acquisition_date && formatDate(g.acquisition_date)}
              />
              <Row
                term="Valeur d'acquisition"
                value={
                  g.acquisition_value && formatMoney(g.acquisition_value)
                }
              />
              <Row
                term="Valeur estimée à la revente"
                value={g.resale_value && formatMoney(g.resale_value)}
              />
              <Row
                term="Date d'estimation"
                value={g.estimation_date && formatDate(g.estimation_date)}
              />
            </dl>
            {g.additional_info && (
              <p className="prose" style={{ marginTop: 12 }}>
                {g.additional_info}
              </p>
            )}
          </Section>
        )}

        {isValuable && (
          <Section icon={Gem} title="Objet de valeur">
            <dl className="def-list two">
              <Row
                term="Cours de la matière première"
                value={
                  g.raw_material_price && formatMoney(g.raw_material_price)
                }
              />
            </dl>
            {g.jewelry_items && g.jewelry_items.length > 0 && (
              <div className="jewelry-list" style={{ marginTop: 16 }}>
                <h4 className="section-subtitle">Composantes du gage</h4>
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Nature</th>
                      <th>Poids (g)</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.jewelry_items.map((item, idx) => (
                      <tr key={item.id ?? idx}>
                        <td>{idx + 1}</td>
                        <td>{item.nature || "—"}</td>
                        <td>
                          {item.weight !== null &&
                          item.weight !== undefined &&
                          item.weight !== ""
                            ? String(item.weight)
                            : "—"}
                        </td>
                        <td>{item.description || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        )}

        {isFinancial && (
          <Section icon={Banknote} title="Garantie financière">
            <dl className="def-list two">
              <Row
                term="Type"
                value={
                  g.financial_type
                    ? lbl(GUARANTEE_LABELS.financial_type, g.financial_type)
                    : undefined
                }
              />
              <Row term="Numéro de compte" value={g.account_number} />
              <Row term="Solde" value={g.balance && formatMoney(g.balance)} />
              <Row
                term="Taux de rémunération"
                value={g.remuneration_rate && `${g.remuneration_rate} %`}
              />
              <Row
                term="Échéance du dépôt"
                value={
                  g.deposit_maturity_date &&
                  formatDate(g.deposit_maturity_date)
                }
              />
              <Row term="Code ISIN / valeur" value={g.isin_code} />
              <Row
                term="Décote de sécurité"
                value={g.security_discount && `${g.security_discount} %`}
              />
            </dl>
            {g.volatility_history && (
              <p className="prose" style={{ marginTop: 12 }}>
                {g.volatility_history}
              </p>
            )}
          </Section>
        )}

        {isGeneric && (
          <Section icon={ShieldCheck} title="Détails du bien / engagement">
            <dl className="def-list two">
              <Row
                term="Type de garantie"
                value={
                  lbl(GUARANTEE_LABELS.guarantee_type, g.guarantee_type) ||
                  g.type_display
                }
              />
              <Row term="Adresse / localisation" value={g.address} />
              <Row term="N° de document" value={g.document_number} />
              <Row
                term="Date du document"
                value={
                  g.document_issue_date && formatDate(g.document_issue_date)
                }
              />
              <Row term="Informations complémentaires" value={g.additional_info} />
            </dl>
          </Section>
        )}

        <Section icon={UploadCloud} title="Pièces justificatives">
          <div className="doc-row">
            {scanEntries.map((s) => (
              <DocChip key={s.label} label={s.label} href={s.href} />
            ))}
          </div>
          {!hasTypedScans && !hasFreeDocs && (
            <p className="muted small">Aucune pièce jointe.</p>
          )}
          {hasFreeDocs && (
            <div className="doc-row" style={{ marginTop: 12 }}>
              {g.documents!.map((d) => (
                <DocChip
                  key={d.id}
                  label={d.title || "Document"}
                  href={d.file}
                />
              ))}
            </div>
          )}
        </Section>

        <Section icon={Images} title="Photos">
          {photos.length > 0 ? (
            <div className="photo-gallery">
              {photos.map((p) => (
                <figure key={p.id} className="photo-item">
                  <a href={p.image} target="_blank" rel="noreferrer">
                    <img
                      src={p.image}
                      alt={p.caption || "Photo de la garantie"}
                    />
                  </a>
                  {p.caption && <figcaption>{p.caption}</figcaption>}
                </figure>
              ))}
            </div>
          ) : (
            <p className="muted small">Aucune photo pour cette garantie.</p>
          )}
        </Section>

        <Section icon={History} title="Historique des mouvements">
          {movements.length > 0 ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Valeur</th>
                  <th>Commentaire</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((m) => (
                  <tr key={m.id}>
                    <td>{formatDate(m.movement_date)}</td>
                    <td>{m.movement_type_display || m.movement_type}</td>
                    <td>
                      {m.value != null && m.value !== ""
                        ? formatMoney(m.value)
                        : "—"}
                    </td>
                    <td>{m.comment || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted small">Aucun mouvement enregistré.</p>
          )}
        </Section>
      </div>
    </div>
  );
}
