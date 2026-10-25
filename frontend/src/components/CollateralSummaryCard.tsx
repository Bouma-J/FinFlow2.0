import { useQuery } from "@tanstack/react-query";
import { Landmark, Shield, TriangleAlert, Users } from "lucide-react";

import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { PERM_CREDITS } from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import { Card, formatMoney } from "@/components/ui";

export type CollateralSummary = {
  reference_amount: string | null;
  currency: string;
  guarantees: {
    id: string;
    reference: string;
    guarantee_type_display: string;
    gross_value: string;
    retained_value: string;
    haircut_pct: string;
  }[];
  guarantees_retained_total: string;
  guarantee_coverage_pct: string | null;
  guarantee_gap: string | null;
  min_guarantee_coverage: string;
  guarantee_ok: boolean | null;
  sureties: {
    id: string;
    surety_name: string;
    amount: string;
    ceiling: string;
  }[];
  sureties_total: string;
  surety_coverage_pct: string | null;
  requires_guarantee: boolean;
  alerts: string[];
  haircuts: Record<string, string>;
};

export function CollateralSummaryCard({
  applicationId,
  currency = "XOF",
  embedded = false,
}: {
  applicationId: string;
  currency?: string;
  /** Sans carte englobante (déjà dans une section dossier). */
  embedded?: boolean;
}) {
  const { user } = useAuth();
  const { data, isLoading, error } = useQuery({
    queryKey: ["collateral-summary", applicationId],
    queryFn: async () =>
      (
        await api.get<CollateralSummary>(
          `/credit-applications/${applicationId}/collateral-summary/`,
        )
      ).data,
  });

  if (isLoading) {
    const body = <p className="muted">Chargement du collatéral…</p>;
    return embedded ? (
      <div className="collateral-summary">{body}</div>
    ) : (
      <Card title={<><Shield size={17} /> Garanties & cautions</>}>{body}</Card>
    );
  }
  if (error || !data) {
    const body = (
      <p className="muted">Impossible de charger la synthèse collatéral.</p>
    );
    return embedded ? (
      <div className="collateral-summary">{body}</div>
    ) : (
      <Card title={<><Shield size={17} /> Garanties & cautions</>}>{body}</Card>
    );
  }

  const cur = data.currency || currency;

  const body = (
    <>
      {!embedded && (
        <p className="muted" style={{ marginTop: 0 }}>
          Capacité (ci-dessus) · Garanties réelles · Cautions — piliers séparés.
          Les haircuts sont ceux de la filiale.
        </p>
      )}

      {data.alerts.length > 0 && (
        <div className="notice-warning" style={{ marginBottom: "1rem" }}>
          <TriangleAlert size={18} />
          <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
            {data.alerts.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="collateral-pillars">
        <div className="collateral-pillar">
          <h4 className="form-section-title">
            <Landmark size={16} /> Garanties réelles
          </h4>
          <div className="form-grid">
            <label className="field">
              <span>Couverture (valeurs retenues)</span>
              <input
                readOnly
                disabled
                value={
                  data.guarantee_coverage_pct != null
                    ? `${data.guarantee_coverage_pct} % (seuil ${data.min_guarantee_coverage} %)`
                    : "—"
                }
              />
            </label>
            <label className="field">
              <span>Total retenu</span>
              <input
                readOnly
                disabled
                value={formatMoney(data.guarantees_retained_total, cur)}
              />
            </label>
            <label className="field">
              <span>Écart vs crédit</span>
              <input
                readOnly
                disabled
                value={
                  data.guarantee_gap != null
                    ? formatMoney(data.guarantee_gap, cur)
                    : "—"
                }
              />
            </label>
          </div>
          {data.guarantees.length === 0 ? (
            <p className="muted">Aucune garantie ACTIVE rattachée.</p>
          ) : (
            <table className="table" style={{ marginTop: "0.75rem" }}>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Brut</th>
                  <th>Haircut</th>
                  <th>Retenu</th>
                </tr>
              </thead>
              <tbody>
                {data.guarantees.map((g) => (
                  <tr key={g.id}>
                    <td>
                      {g.guarantee_type_display}
                      {g.reference ? ` · ${g.reference}` : ""}
                    </td>
                    <td>{formatMoney(g.gross_value, cur)}</td>
                    <td>{g.haircut_pct} %</td>
                    <td>{formatMoney(g.retained_value, cur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="collateral-pillar">
          <h4 className="form-section-title">
            <Users size={16} /> Cautions (pilier séparé)
          </h4>
          <div className="form-grid">
            <label className="field">
              <span>Total engagements</span>
              <input
                readOnly
                disabled
                value={formatMoney(data.sureties_total, cur)}
              />
            </label>
            <label className="field">
              <span>% du crédit (informatif)</span>
              <input
                readOnly
                disabled
                value={
                  data.surety_coverage_pct != null
                    ? `${data.surety_coverage_pct} %`
                    : "—"
                }
              />
            </label>
          </div>
          {data.sureties.length === 0 ? (
            <p className="muted">Aucune caution ACTIVE rattachée.</p>
          ) : (
            <table className="table" style={{ marginTop: "0.75rem" }}>
              <thead>
                <tr>
                  <th>Caution</th>
                  <th>Engagé</th>
                  <th>Plafond</th>
                </tr>
              </thead>
              <tbody>
                {data.sureties.map((s) => (
                  <tr key={s.id}>
                    <td>{s.surety_name || "—"}</td>
                    <td>{formatMoney(s.amount, cur)}</td>
                    <td>
                      {_dec(s.ceiling) > 0
                        ? formatMoney(s.ceiling, cur)
                        : "Ouvert"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {!embedded && (
        <p className="muted small" style={{ marginTop: "1rem" }}>
          Gérer le collatéral sur le dossier :{" "}
          <PermLink
            user={user}
            anyOf={PERM_CREDITS}
            to={`/dossiers/${applicationId}`}
          >
            ouvrir la fiche
          </PermLink>
          {data.requires_guarantee
            ? " — ce produit exige une garantie ou caution."
            : ""}
        </p>
      )}
      {embedded && data.requires_guarantee && (
        <p className="muted small" style={{ marginTop: "0.75rem" }}>
          Ce produit exige une garantie ou une caution.
        </p>
      )}
    </>
  );

  if (embedded) {
    return <div className="collateral-summary embedded">{body}</div>;
  }

  return (
    <Card
      title={
        <>
          <Shield size={17} /> Collatéral d&apos;instruction
        </>
      }
    >
      {body}
    </Card>
  );
}

function _dec(v: string): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
