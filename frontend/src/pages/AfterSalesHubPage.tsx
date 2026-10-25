import { useQuery } from "@tanstack/react-query";
import {
  CircleDollarSign,
  Layers,
  Plus,
  ShieldOff,
  Stamp,
  Unlock,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { AfterSalesHub } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import {
  PERM_COLLECTIONS,
  PERM_DATIONS,
  PERM_FORMALIZATIONS,
  PERM_RELEASES,
} from "@/auth/routePerms";
import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  TenantScopeNotice,
} from "@/components/ui";

const KIND_LABEL: Record<string, string> = {
  MAIN_LEVEE: "Main levée",
  DATION: "Dation",
  FORMALISATION: "Formalisation",
  COLLECTION: "Recouvrement",
};

export function AfterSalesHubPage() {
  const navigate = useNavigate();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);

  const canMl = hasAnyPerm(user, PERM_RELEASES);
  const canDation = hasAnyPerm(user, PERM_DATIONS);
  const canForm = hasAnyPerm(user, PERM_FORMALIZATIONS);
  const canColl = hasAnyPerm(user, PERM_COLLECTIONS);

  const hub = useQuery({
    queryKey: ["after-sales-hub", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<AfterSalesHub>("/reporting/after-sales-hub/", {
          params: activeTenant ? { tenant: activeTenant } : {},
        })
      ).data,
    enabled: !needsTenant,
  });

  const m = hub.data?.modules;

  const tiles = [
    canMl && {
      key: "ml",
      to: "/mains-levees",
      createTo: "/mains-levees/nouvelle",
      canCreate: hasPerm(user, "guarantees.initiate_guaranteereleaserequest"),
      icon: ShieldOff,
      title: "Mains levées",
      desc: "Radiation / libération de garanties après solde",
      open: m?.main_levee?.open,
      extra: m?.main_levee
        ? `${m.main_levee.in_approval} en circuit`
        : null,
    },
    canDation && {
      key: "dation",
      to: "/dations",
      createTo: "/dations/nouvelle",
      canCreate: hasPerm(user, "guarantees.initiate_dationrequest"),
      icon: Unlock,
      title: "Dations",
      desc: "Dation en paiement et transfert d'actifs",
      open: m?.dation?.open,
      extra: m?.dation ? `${m.dation.in_approval} en circuit` : null,
    },
    canForm && {
      key: "form",
      to: "/formalisations",
      createTo: "/formalisations/nouvelle",
      canCreate: hasPerm(
        user,
        "guarantees.initiate_guaranteeformalizationrequest",
      ),
      icon: Stamp,
      title: "Formalisations",
      desc: "Actes notariés et publicité des garanties",
      open: m?.formalisation?.open,
      extra: m?.formalisation
        ? `${m.formalisation.in_approval} en circuit`
        : null,
    },
    canColl && {
      key: "coll",
      to: "/recouvrement",
      createTo: null as string | null,
      canCreate: false,
      icon: CircleDollarSign,
      title: "Recouvrement",
      desc: "Impayés, relances, contentieux",
      open: m?.collection?.open,
      extra: m?.collection
        ? `${m.collection.followups_due} actions dues · ${m.collection.unassigned} non affectés`
        : null,
    },
  ].filter(Boolean) as Array<{
    key: string;
    to: string;
    createTo: string | null;
    canCreate: boolean;
    icon: typeof ShieldOff;
    title: string;
    desc: string;
    open: number | undefined;
    extra: string | null;
  }>;

  const recent = (hub.data?.recent ?? []).filter((row) => {
    if (row.kind === "MAIN_LEVEE") return canMl;
    if (row.kind === "DATION") return canDation;
    if (row.kind === "FORMALISATION") return canForm;
    if (row.kind === "COLLECTION") return canColl;
    return false;
  });

  return (
    <div className="page-shell">
      <PageHeader
        icon={Layers}
        title="Après-vente"
        subtitle="Mains levées, dations, formalisations et recouvrement"
      />

      {needsTenant ? (
        <TenantScopeNotice />
      ) : hub.isLoading ? (
        <Spinner />
      ) : hub.isError ? (
        <EmptyState message="Impossible de charger le hub après-vente." />
      ) : (
        <>
          {m && (
            <div className="mini-kpis" style={{ marginBottom: 16 }}>
              {canMl && m.main_levee && (
                <Link to="/mains-levees" className="mini-kpi">
                  <span className="mk-value">{m.main_levee.open}</span>
                  <span className="mk-label">ML ouvertes</span>
                </Link>
              )}
              {canDation && m.dation && (
                <Link to="/dations" className="mini-kpi">
                  <span className="mk-value">{m.dation.open}</span>
                  <span className="mk-label">Dations ouvertes</span>
                </Link>
              )}
              {canForm && m.formalisation && (
                <Link to="/formalisations" className="mini-kpi">
                  <span className="mk-value">{m.formalisation.open}</span>
                  <span className="mk-label">Formalisations ouvertes</span>
                </Link>
              )}
              {canColl && m.collection && (
                <Link to="/recouvrement" className="mini-kpi">
                  <span className="mk-value">{m.collection.open}</span>
                  <span className="mk-label">Recouvrements ouverts</span>
                </Link>
              )}
              {canColl && m.collection && (
                <Link
                  to="/recouvrement"
                  className="mini-kpi"
                  state={{ followupDue: true }}
                >
                  <span className="mk-value">{m.collection.followups_due}</span>
                  <span className="mk-label">Actions dues</span>
                </Link>
              )}
            </div>
          )}

          <div
            className="detail-grid"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              gap: 16,
              marginBottom: 20,
            }}
          >
            {tiles.map((t) => {
              const Icon = t.icon;
              return (
                <Card key={t.key} title="">
                  <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                    <Icon size={22} aria-hidden />
                    <div style={{ flex: 1 }}>
                      <Link to={t.to} style={{ fontWeight: 600, fontSize: "1.05rem" }}>
                        {t.title}
                      </Link>
                      <p className="muted small" style={{ margin: "6px 0 10px" }}>
                        {t.desc}
                      </p>
                      <div className="row-actions" style={{ gap: 8, flexWrap: "wrap" }}>
                        <Badge
                          value="info"
                          label={
                            t.open === undefined
                              ? "—"
                              : `${t.open} ouvert${t.open > 1 ? "s" : ""}`
                          }
                        />
                        {t.extra && (
                          <span className="muted small">{t.extra}</span>
                        )}
                      </div>
                      {t.canCreate && t.createTo && (
                        <div className="row-actions" style={{ marginTop: 12, gap: 8 }}>
                          <Link className="btn btn-primary btn-sm" to={t.createTo}>
                            <Plus size={14} />
                            Nouvelle
                          </Link>
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>

          <Card title="Files récentes">
            {!recent.length ? (
              <EmptyState message="Aucun dossier après-vente ouvert." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Référence</th>
                    <th>Client</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((row) => (
                    <tr
                      key={`${row.kind}-${row.id}`}
                      className="row-clickable"
                      onClick={() => navigate(row.detail_path)}
                    >
                      <td>
                        <Badge
                          value="info"
                          label={KIND_LABEL[row.kind] || row.kind}
                        />
                      </td>
                      <td>{row.reference || "—"}</td>
                      <td>{row.client_name}</td>
                      <td className="small">
                        {row.status_display || row.status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {hub.data?.as_of && (
              <p className="muted small" style={{ marginTop: 10 }}>
                Au {hub.data.as_of}
              </p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
