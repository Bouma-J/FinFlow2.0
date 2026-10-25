import type { ReactNode } from "react";
import { CREDIT_LABELS, type FinancialAnalysis } from "@/api/types";
import { formatDate, formatMoney } from "@/components/ui";
import { FINANCIAL_SUPPLEMENTS } from "@/components/FinancialAnalysisSupplements";

type Field = [keyof FinancialAnalysis, string, ("money" | "text" | "count" | "bool" | "percent")?];
const INCOME: Field[] = [["salary_income", "Salaire net"], ["spouse_income", "Revenus du conjoint"], ["rental_income", "Loyers / rentes"], ["pension_income", "Pension"], ["variable_income", "Primes / revenus variables"], ["other_activity_income", "Revenus d'activité hors bloc dédié"], ["other_income", "Autres revenus"]];
const HOUSEHOLD: Field[] = [["rent_expense", "Logement"], ["food_expense", "Alimentation"], ["utilities_expense", "Eau / électricité / téléphone"], ["transport_expense", "Transport"], ["education_expense", "Scolarité"], ["health_expense", "Santé"], ["other_household_expenses", "Autres charges"], ["tontine_expense", "Tontines"], ["social_contributions", "Cotisations / assurances"], ["family_support_expense", "Soutien familial"], ["other_monthly_obligations", "Autres obligations sur la période"]];
const RESULT: Field[] = [["turnover", "Chiffre d'affaires"], ["cogs", "Coût des marchandises vendues"], ["gross_margin", "Marge brute"], ["other_operating_income", "Autres produits d'exploitation"], ["op_rent", "Loyer"], ["op_salaries", "Salaires"], ["op_utilities", "Eau / électricité"], ["op_transport", "Transport"], ["op_telecom", "Télécoms"], ["op_taxes", "Impôts d'exploitation / patente"], ["op_maintenance", "Entretien"], ["op_other", "Autres charges d'exploitation"], ["total_operating_expenses", "Total charges d'exploitation"], ["ebe", "EBE reconstitué"], ["depreciation", "Amortissements"], ["financial_charges", "Charges financières"], ["net_result", "Résultat reconstitué"], ["cash_flow", "Résultat + charges non décaissées nettes"]];
const ASSETS: Field[] = [["stock_value", "Stock"], ["receivables", "Créances clients"], ["cash_in_hand", "Caisse"], ["bank_balance", "Banque disponible"], ["cash_available", "Ancien agrégat de trésorerie"], ["other_current_assets", "Autres actifs courants"], ["land_building_value", "Terrains / bâtiments"], ["equipment_value", "Équipements"], ["vehicle_value", "Véhicules"], ["other_fixed_assets", "Autres immobilisations"], ["fixed_assets", "Ancien agrégat d'immobilisations"], ["total_assets", "Total de l'actif retenu"]];
const DEBTS: Field[] = [["supplier_debt", "Dettes fournisseurs"], ["tax_social_debt", "Dettes fiscales et sociales"], ["other_current_debt", "Autres dettes d'exploitation"], ["short_term_debt", "Autres dettes court terme (hors postes précédents)"], ["ongoing_credit_balance", "Encours financier total"], ["long_term_debt", "Dont part long terme (déjà incluse)"], ["shareholder_debt", "Comptes courants d'associés"], ["total_debts", "Total dettes"], ["equity", "Fonds propres reconstitués (actif − dettes)"]];
const ACTIVITY: Field[] = [["activity_name", "Activité", "text"], ["activity_business_age_months", "Ancienneté (mois)", "count"], ["activity_sales_days", "Jours de vente sur la période", "count"], ["activity_turnover", "CA / recettes"], ["activity_expenses", "Charges totales, achats inclus"], ["activity_purchases", "Dont achats (déjà inclus)"], ["activity_stock_value", "Stock"], ["activity_receivables", "Créances clients"], ["activity_cash_available", "Trésorerie"], ["activity_fixed_assets", "Actifs productifs"], ["activity_supplier_debt", "Fournisseurs"], ["activity_is_formal", "Activité formalisée", "bool"], ["activity_records_available", "Cahier / pièces disponibles", "bool"]];
const GROUP: Field[] = [["members_count", "Membres", "count"], ["active_contributing_members", "Cotisants actifs", "count"], ["members_with_arrears", "Membres en retard", "count"], ["group_age_months", "Ancienneté (mois)", "count"], ["collective_contributions", "Cotisations"], ["collective_other_income", "Autres recettes"], ["group_activity_turnover", "CA commun"], ["collective_operating_expenses", "Fonctionnement"], ["group_activity_expenses", "Charges de l'activité"], ["collective_savings", "Épargne (solde, pas un revenu)"], ["collective_savings_locked", "Épargne mobilisable / nantie", "bool"], ["group_records_verified", "Registres / épargne vérifiés", "bool"], ["solidarity_commitment", "Engagement de solidarité", "bool"]];

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  if (typeof value !== "string" && typeof value !== "number") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function Detail({ title, children, open = false }: { title: string; children: ReactNode; open?: boolean }) {
  return <details className="subsection" open={open}><summary className="subsection-title">{title}</summary>{children}</details>;
}

function ForecastChart({ rows, currency }: { rows: Record<string, unknown>[]; currency: string }) {
  const flows = rows.map((row) => numeric(row.net_flow));
  const balances = rows.map((row) => numeric(row.closing));
  const values = [...flows, ...balances].filter((value): value is number => value != null);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const x = (index: number) => 44 + (index + 0.5) * 560 / rows.length;
  const y = (value: number) => 20 + (high - value) * 130 / span;
  const width = Math.max(1, Math.min(30, 400 / rows.length));
  const closingKnown = balances.every((value) => value != null);
  return <figure style={{ margin: "16px 0" }}>
    <svg viewBox="0 0 640 190" role="img" aria-label="Flux mensuels en barres et trésorerie cumulée de clôture en courbe lorsqu'elle est connue" style={{ width: "100%", maxHeight: 240 }}>
      <line x1="40" y1={y(0)} x2="610" y2={y(0)} stroke="currentColor" opacity="0.3" />
      {flows.map((flow, index) => flow == null ? null : <rect key={index} x={x(index) - width / 2} y={Math.min(y(0), y(flow))} width={width} height={Math.max(1, Math.abs(y(flow) - y(0)))} fill={flow < 0 ? "var(--danger, #b91c1c)" : "var(--brand)"} opacity="0.75"><title>{`${rows[index].month} : flux ${formatMoney(flow, currency)}`}</title></rect>)}
      {closingKnown && <polyline points={balances.map((value, index) => `${x(index)},${y(value!)}`).join(" ")} fill="none" stroke="var(--accent)" strokeWidth="2.5" />}
      {closingKnown && balances.map((value, index) => <circle key={index} cx={x(index)} cy={y(value!)} r="3" fill="var(--accent)"><title>{`${rows[index].month} : clôture ${formatMoney(value, currency)}`}</title></circle>)}
      {rows.map((row, index) => index % Math.max(1, Math.ceil(rows.length / 8)) === 0 ? <text key={index} x={x(index)} y="176" textAnchor="middle" fill="currentColor" fontSize="10">{String(row.month || "—")}</text> : null)}
      <text x="4" y="16" fill="currentColor" fontSize="10">{formatMoney(high, currency)}</text><text x="4" y="154" fill="currentColor" fontSize="10">{formatMoney(low, currency)}</text>
    </svg>
    <figcaption className="muted small">Barres : flux mensuels (rouge si négatifs). {closingKnown ? "Courbe accent : trésorerie cumulée de clôture." : "Solde cumulé non tracé : données d'ouverture ou mois manquants."} Les montants exacts figurent dans le tableau.</figcaption>
  </figure>;
}

export function FinancialAnalysisReadout({ analysis: a, currency }: { analysis: FinancialAnalysis; currency: string }) {
  const m = a.metrics;
  const n = (key: string) => numeric(m[key]);
  const money = (key: string) => formatMoney(n(key), currency);
  const corp = a.client_type === "CORPORATE";
  const group = a.client_type === "PROFESSIONAL";
  const context = a.calculation_context;
  const period = ({ MONTHLY: "mois", QUARTERLY: "trimestre", ANNUAL: "année" } as Record<string, string>)[a.reference_period] || a.reference_period;
  const format = (value: unknown, type = "money") => value == null || value === "" ? "Non renseigné"
    : type === "bool" ? (value ? "Oui" : "Non")
    : type === "text" ? String(value)
    : type === "count" ? String(value)
    : type === "percent" ? `${numeric(value)?.toLocaleString("fr-FR") ?? "—"} %`
    : formatMoney(numeric(value), currency);
  const fields = (items: Field[]) => <dl className="def-list two">{items.map(([key, label, type]) => <div key={key}><dt>{label}</dt><dd>{format(a[key], type)}</dd></div>)}</dl>;
  const card = (label: string, key: string) => <div className="metric" key={key}><span className="metric-label">{label}</span><span className="metric-value">{money(key)}</span></div>;
  const rows = Array.isArray(m.forecast_rows) ? m.forecast_rows as Record<string, unknown>[] : [];
  const warnings: string[] = [];
  if (m.installment_known === false) warnings.push("Échéancier non calculable : les indicateurs dépendant de la nouvelle échéance sont indisponibles. Vérifier les conditions du crédit.");
  if (m.income_positive === false) warnings.push("Revenu retenu nul ou négatif : le taux d'endettement n'est pas interprétable et la capacité ne peut pas être qualifiée favorable.");
  if (a.flags.capacity_ok === false) warnings.push("Les ressources disponibles ne couvrent pas l'effort total du crédit après charges et dettes existantes.");
  if (["FAVORABLE", "CONDITIONAL"].includes(a.recommendation) && (a.flags.capacity_ok === false || a.flags.dscr_ok === false || m.income_positive === false)) warnings.push("Divergence avec l'avis enregistré : l'analyste a donné un avis favorable ou favorable sous conditions, mais le recalcul signale une capacité ou une couverture du service de la dette insuffisante. L'avis enregistré et les résultats recalculés doivent être rapprochés avant une nouvelle décision.");
  if (["product_details_complete", "stock_details_complete", "debt_details_complete"].some((key) => m[key] === false)) warnings.push("Des lignes produits, stocks ou engagements sont incomplètes. Les totaux concernés restent inconnus ; compléter les montants, y compris les zéros vérifiés.");
  for (const [key, label] of [["sales_reconciled", "ventes détaillées / chiffre d'affaires"], ["stock_reconciled", "inventaire / stock déclaré"], ["outstanding_reconciled", "engagements détaillés / encours déclaré"], ["fixed_costs_reconciled", "charges fixes + variables / charges d'exploitation"], ["forecast_service_reconciled", "prévisions / échéancier du nouveau crédit"]]) {
    if (m[key] === false) warnings.push(`Écart à expliquer : ${label}.`);
  }
  if (rows.length && m.forecast_opening_balance == null) warnings.push("Trésorerie cumulée indisponible : renseigner le solde d'ouverture et tous les mois successifs. Un flux négatif n'est pas nécessairement un solde de trésorerie négatif.");
  if (n("equity_gap") != null && n("equity_gap") !== 0) warnings.push("Les fonds propres déclarés et reconstitués présentent un écart à expliquer.");

  const specs: { key: string; label: string; formula: string; unit?: string; threshold?: string; min?: boolean; flag?: string }[] = corp ? [
    { key: "global_dscr", label: "DSCR global", formula: `${money("repayment_cash_flow")} / ${money("global_debt_service")} par mois`, unit: "×", threshold: "min_dscr", min: true, flag: "dscr_ok" },
    { key: "dscr_stress", label: "DSCR sous stress", formula: "Flux disponible sous baisse du CA, hausse des achats et retard clients / service global", unit: "×", threshold: "min_dscr", min: true, flag: "dscr_stress_ok" },
    { key: "financial_autonomy", label: "Autonomie financière", formula: "Fonds propres reconstitués / actif × 100", unit: "%", threshold: "min_financial_autonomy", min: true, flag: "autonomy_ok" },
    { key: "gearing", label: "Gearing brut", formula: "Encours financier (hors comptes d'associés) / fonds propres positifs", unit: "×", threshold: "max_gearing", flag: "gearing_ok" },
    { key: "current_ratio", label: "Liquidité générale", formula: "Actif courant / passif courant (part financière court terme incluse)", unit: "×", threshold: "min_current_ratio", min: true, flag: "current_ratio_ok" },
    { key: "quick_ratio", label: "Liquidité réduite", formula: "(Actif courant − stocks) / passif courant", unit: "×" },
    { key: "dso_days", label: "Délai clients", formula: "Créances moyennes si ouverture connue, sinon clôture / CA annualisé × 360", unit: "jours" },
    { key: "dpo_days", label: "Délai fournisseurs", formula: "Fournisseurs moyens si ouverture connue, sinon clôture / achats annualisés (CAMV si achats inconnus) × 360", unit: "jours" },
    { key: "dio_days", label: "Rotation stock", formula: "Stock moyen si ouverture connue, sinon clôture / CAMV annualisé × 360", unit: "jours" },
    { key: "break_even_turnover", label: "Seuil de rentabilité sur la période", formula: "(Charges fixes + amortissements + charges financières) / taux de marge sur coûts variables ; nécessite une ventilation rapprochée" },
    { key: "result_growth", label: "Évolution du résultat", formula: "(Résultat N − N-1) / |résultat N-1| × 100 ; permet de distinguer pertes aggravées et amélioration", unit: "%" },
  ] : [
    { key: "debt_ratio", label: "Taux d'endettement", formula: `Service global ${money("global_debt_service")} / ${group ? "recettes collectives" : "revenu retenu"} ${money(group ? "collective_income" : "weighted_income")} × 100`, unit: "%", threshold: "max_debt_ratio", flag: "debt_ratio_ok" },
    { key: "debt_ratio_stress", label: "Taux sous stress", formula: "Service global / revenu positif retenu sous stress × 100", unit: "%", threshold: "max_debt_ratio", flag: "debt_ratio_stress_ok" },
    ...(group ? [{ key: "contribution_concentration", label: "Participation des cotisants", formula: "Cotisants actifs / membres × 100 (ne mesure pas la concentration des montants)", unit: "%" }, { key: "members_arrears_rate", label: "Membres en retard", formula: "Membres en retard / membres × 100", unit: "%" }] : [
      { key: "disposable_per_capita", label: "Reste après crédit par personne / mois", formula: "(Revenu pondéré − charges − dette existante − nouvelle échéance − épargne obligatoire) / (personnes à charge + 1)", threshold: "min_living_wage_per_capita", min: true, flag: "living_wage_ok" },
      { key: "transferable_quota_available", label: "Quotité disponible / mois", formula: "Salaire net mensuel × fraction configurée − retenues salariales mensuelles ; à comparer à l'échéance institution" },
    ]),
  ];
  specs.push({ key: "guarantee_coverage", label: "Couverture des garanties réelles", formula: "Valeur retenue après décotes / montant de référence × 100 ; cautions séparées", unit: "%", threshold: "min_guarantee_coverage", min: true, flag: "guarantee_ok" });

  return <>
    <div className="subsection">
      <h4 className="subsection-title">Synthèse de capacité — montants mensuels</h4>
      {!corp && !group && <p className="muted small">Profil : {({ SALARIE: "Salarié", INDEPENDANT: "Indépendant", MIXTE: "Mixte — salaire et activité" } as Record<string, string>)[a.individual_profile || ""] || "Non renseigné"}.</p>}
      {context && <p className="muted small">{context.legacy ? "Recalcul indicatif d'un dossier historique" : context.frozen ? "Recalcul selon les règles conservées à la soumission" : "Calcul selon les conditions actuelles du dossier"} du {formatDate(context.calculated_at)} · montant {context.amount_label} : {formatMoney(context.amount, currency)} · durée {context.duration_months} mois · {CREDIT_LABELS.periodicity[context.periodicity] || context.periodicity} · {CREDIT_LABELS.repayment_mechanism[context.mechanism] || context.mechanism}.
        {context.rates.interest_rate != null && ` Taux annuel ${context.rates.interest_rate} %, épargne obligatoire ${context.rates.mandatory_savings_rate ?? 0} % du capital par échéance.`}</p>}
      {context?.legacy && <p className="form-error" role="note">Les règles utilisées lors de la décision initiale n'ont pas été archivées pour ce dossier historique. Ce recalcul ne reconstitue pas la décision passée ; les indicateurs enregistrés sont consultables séparément ci-dessous.</p>}
      <div className="metric-grid">
        {corp ? <>
          <div className="metric"><span className="metric-label">CA / {period}</span><span className="metric-value">{formatMoney(a.turnover, currency)}</span></div>
          <div className="metric"><span className="metric-label">Résultat reconstitué / {period}</span><span className="metric-value">{formatMoney(a.net_result, currency)}</span></div>
          <div className={`metric ${a.flags.dscr_ok === true ? "metric-ok" : a.flags.dscr_ok === false ? "metric-warn" : ""}`}><span className="metric-label">DSCR global</span><span className="metric-value">{n("global_dscr") == null ? "—" : `${n("global_dscr")} ×`}</span></div>
        </> : group ? <>
          <div className="metric"><span className="metric-label">Membres / cotisants actifs</span><span className="metric-value">{a.members_count ?? "—"} / {a.active_contributing_members ?? "—"}</span></div>
          {card("Recettes collectives / mois", "collective_income")}
          {card("Charges collectives / mois", "collective_charges")}
        </> : <>{card("Revenus déclarés / mois", "declared_income")}{card("Revenus retenus après pondération / mois", "weighted_income")}{card("Charges du ménage / mois", "household_charges_monthly")}</>}
        {card("Capacité avant nouveau crédit, dette existante déduite", "repayment_capacity")}
        {card("Équivalent mensuel de la nouvelle échéance institution maximale", "installment")}
        {card("Épargne obligatoire — équivalent mensuel", "monthly_savings")}
        {card("Effort total : dettes existantes + nouveau crédit + épargne", "total_cash_effort")}
        <div className={`metric ${a.flags.capacity_ok === true ? "metric-ok" : a.flags.capacity_ok === false ? "metric-warn" : ""}`}><span className="metric-label">{corp || group ? "Marge de trésorerie après crédit" : "Reste à vivre après crédit et épargne"}</span><span className="metric-value">{money("safety_margin")}</span><small>{a.flags.capacity_ok == null ? "Non calculable" : a.flags.capacity_ok ? "Effort couvert" : "Effort non couvert"}</small></div>
        {card("Effort moyen sur la durée (hors dettes existantes)", "average_monthly_cash_payment")}
        {card("Pic d'échéance du nouveau crédit, épargne comprise", "peak_cash_payment")}
      </div>
      <p className="muted small">Le pic à financer et l'effort moyen sont distincts. Pour un in fine ou un remboursement saisonnier, vérifier les dates et ressources disponibles à chaque échéance. Les frais initiaux ne sont pas des charges mensuelles ; les prévisions doivent inclure les autres prélèvements réels.</p>
      {warnings.map((warning) => <p className="form-error" role="status" key={warning}>{warning}</p>)}
    </div>

    <Detail title={`Données financières saisies — flux par ${period}, patrimoine à la date d'arrêté`}>
      {corp ? <>
        <h5>Compte de résultat reconstitué</h5>{fields(RESULT)}
        <p className="muted small">Reconstitution à partir des postes fournis. Les compléments inconnus ne constituent pas une certification de résultat comptable ou de CAF.</p>
        <h5>Actif</h5>{fields(ASSETS)}<h5>Passif et fonds propres</h5>{fields(DEBTS)}
        <h5>Exercice précédent — même durée à vérifier</h5>{fields([["turnover_prev", "CA N-1"], ["net_result_prev", "Résultat N-1"]])}
        <div className="metric-grid">{card("Flux mensuel avant dette, après ajustements renseignés", "cash_before_debt")}{card("Flux mensuel prudent retenu pour le DSCR", "repayment_cash_flow")}{card("Écart fonds propres reconstitués − déclarés", "equity_gap")}</div>
        <p className="muted small">Flux avant dette = résultat + amortissements + provisions nettes + charges financières − produits exceptionnels + charges exceptionnelles − variation BFR − investissements de maintien. Le DSCR retient le plus faible de ce flux et du solde prévisionnel hors dette lorsqu'il est renseigné. Les ajustements non documentés limitent la précision de l'analyse.</p>
        <p className="muted small">Trésorerie : {a.analysis_details?.cash_detail_mode === "DETAIL" ? "détail, zéro compris" : a.analysis_details?.cash_detail_mode === "LEGACY" ? "agrégat historique" : "détail non nul, sinon agrégat historique"}. Immobilisations : {a.analysis_details?.fixed_assets_detail_mode === "DETAIL" ? "détail, zéro compris" : a.analysis_details?.fixed_assets_detail_mode === "LEGACY" ? "agrégat historique" : "détail non nul, sinon agrégat historique"}.</p>
      </> : group ? <>{fields(GROUP)}{a.group_comment && <p className="prose">{a.group_comment}</p>}</> : <>
        <h5>Revenus déclarés du ménage</h5>{fields(INCOME)}
        <h5>Charges du ménage</h5>{fields(HOUSEHOLD)}
        <h5>Stabilité et retenues salariales</h5>{fields([["employer_name", "Employeur", "text"], ["employer_sector", "Secteur employeur", "text"], ["employment_seniority_months", "Ancienneté (mois)", "count"], ["salary_deductions", "Retenues déjà prélevées"], ["salary_paid_through_bank", "Salaire domicilié / traçable", "bool"], ["salary_verified", "Salaire vérifié", "bool"]])}
        <p>Type d'emploi : {({ PERMANENT: "CDI / fonctionnaire", FIXED_TERM: "CDD", RETIRED: "Retraité", DAILY: "Journalier / intermittent", OTHER: "Autre" } as Record<string, string>)[a.employment_type] || "Non renseigné"}.</p>
        <h5>Patrimoine du ménage — soldes</h5>{fields([["personal_savings", "Épargne disponible"], ["personal_real_estate_value", "Immobilier"], ["personal_vehicle_value", "Véhicules"], ["personal_productive_assets", "Actifs productifs"], ["dependents_count", "Personnes à charge, hors demandeur", "count"]])}
        {(a.has_side_activity || a.individual_profile === "INDEPENDANT" || a.individual_profile === "MIXTE") && <><h5>Activité indépendante — distincte du budget ménage</h5>{fields(ACTIVITY)}
          <div className="metric-grid">{card("Résultat net d'activité / mois avant pondération", "activity_net")}{card("Actif de l'activité", "activity_assets")}{card("BFR simplifié de l'activité", "activity_working_capital_need")}</div>
          {a.activity_comment && <p className="prose">{a.activity_comment}</p>}</>}
        <p className="muted small">Pondération retenue sur les revenus variables et le bénéfice d'activité : {n("income_weight") ?? "—"} %. Les pertes d'activité sont retenues intégralement. Les revenus de l'activité ne doivent pas être saisis une seconde fois dans les autres revenus.</p>
      </>}
      <h5>Contrôles de fiabilité</h5>{fields([["field_visit_confirmed", "Visite confirmée", "bool"], ["stock_count_verified", "Inventaire vérifié", "bool"], ["cash_position_verified", "Caisse / banque vérifiées", "bool"]])}
      <h5>Compléments renseignés</h5><dl className="def-list two">{Object.entries(FINANCIAL_SUPPLEMENTS).filter(([key]) => a.analysis_details?.[key] != null && a.analysis_details[key] !== "").map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{format(a.analysis_details?.[key], key.endsWith("_pct") ? "percent" : key.endsWith("_days") ? "count" : "money")}</dd></div>)}</dl>
      {!!Object.keys(a.custom_fields || {}).length && <><h5>Informations complémentaires configurées</h5><dl className="def-list two">{Object.entries(a.custom_fields || {}).map(([key, value]) => {
        const definition = a.custom_field_definitions?.find((field) => field.id === key);
        return <div key={key}><dt>{definition?.label || key}</dt><dd>{format(value, definition?.type === "boolean" ? "bool" : "text")}</dd></div>;
      })}</dl></>}
    </Detail>

    <Detail title="Prévisions et rapprochements" open={rows.length > 0 || ["sales_reconciled", "stock_reconciled", "outstanding_reconciled"].some((key) => m[key] === false)}>
      {fields([["projected_monthly_inflows", "Encaissements mensuels synthétiques hors nouveau crédit"], ["projected_monthly_outflows", "Sorties mensuelles synthétiques hors service de dette"]])}
      {a.cashflow_comment && <p className="prose">{a.cashflow_comment}</p>}
      <div className="metric-grid">{card("Écart ventes reconstituées − CA déclaré", "sales_gap")}{card("Écart inventaire net − stock déclaré", "stock_gap")}{card("Écart encours détaillés − encours déclaré", "outstanding_gap")}{card("Impayés détaillés", "detailed_debt_arrears")}{card("Marge reconstituée par produits", "reconstituted_margin")}</div>
      {!!rows.length && <>
        <div className="metric-grid">{card("Trésorerie d'ouverture", "forecast_opening_balance")}{card("Plus faible flux mensuel", "forecast_lowest_flow")}{card("Plus faible solde de clôture", "forecast_lowest_balance")}{card("Trésorerie de clôture finale", "forecast_closing_balance")}</div>
        <p className="muted small">Mois à flux négatif : {n("forecast_negative_flow_months") ?? "—"}. Mois à trésorerie de clôture négative : {n("forecast_cash_deficit_months") ?? "Non calculable"}.</p>
        <ForecastChart rows={rows} currency={currency} />
        <div className="table-scroll"><table className="table"><caption>Plan mensuel, dette et investissement déduits ; comparaison à l'échéancier simulé sur les mois saisis</caption><thead><tr>{["Mois", "Ouverture", "Flux net", "Clôture", "Nouveau crédit saisi", "Échéancier attendu", "Écart"].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}><th scope="row">{String(row.month || "Mois manquant")}</th>{["opening", "net_flow", "closing", "new_service", "expected_new_service", "service_gap"].map((key) => <td key={key}>{formatMoney(numeric(row[key]), currency)}</td>)}</tr>)}</tbody></table></div>
      </>}
      {!rows.length && <p className="muted">Aucun plan mensuel détaillé enregistré.</p>}
    </Detail>

    <Detail title="Formules, seuils et interprétation des indicateurs">
      <p className="muted small">« — » indique une donnée absente, une base non positive ou un calcul non applicable, jamais un zéro implicite. Les seuils sont ceux du dossier ; ils ne représentent pas une norme universelle UMOA.</p>
      <div className="table-scroll"><table className="table"><thead><tr>{["Indicateur", "Valeur", "Base de calcul", "Seuil", "Lecture"].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{specs.map((spec) => {
        const value = n(spec.key);
        const threshold = spec.threshold ? a.thresholds[spec.threshold] : undefined;
        const status = spec.flag ? m.flags[spec.flag] : undefined;
        return <tr key={spec.key}><th scope="row">{spec.label}</th><td>{spec.unit ? value == null ? "—" : `${value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} ${spec.unit}` : formatMoney(value, currency)}</td><td>{spec.formula}</td><td>{threshold == null ? "Non défini" : `${spec.min ? "≥" : "≤"} ${threshold.toLocaleString("fr-FR")} ${spec.unit || currency}`}</td><td>{status === false ? "Non conforme" : status === true ? "Conforme" : value == null ? "Non calculable" : "Informatif"}</td></tr>;
      })}</tbody></table></div>
      <p className="muted small">Sous stress, les charges restent présentes : baisse du CA ou des revenus de {a.thresholds.stress_pct} %, hausse supplémentaire des achats {String(a.analysis_details?.purchase_stress_pct || 0)} %{corp ? ` et décalage clients de ${a.analysis_details?.receivable_delay_days || 0} jours (besoin de trésorerie prudent imputé sur le mois)` : ""}.</p>
      {!corp && <p>Reste disponible mensuel sous stress : <strong>{money("stress_residual")}</strong>.</p>}
    </Detail>

    {a.recorded_indicators && <Detail title="Comparaison avec les derniers indicateurs enregistrés">
      <p className="muted small">Enregistrement du {formatDate(a.recorded_indicators.updated_at)}. Ces valeurs conservées ne constituent pas à elles seules un instantané complet de la décision. La consultation affiche les calculs courants sans réécrire cet historique.</p>
      <div className="table-scroll"><table className="table"><thead><tr><th scope="col">Indicateur</th><th scope="col">Enregistré</th><th scope="col">Calcul courant</th></tr></thead><tbody>{([ ["new_installment", "Échéance institution maximale"], ["repayment_capacity", "Capacité mensuelle avant nouveau crédit"], ["debt_ratio", "Taux d'endettement (%)"], ["dscr", "DSCR global (×)"], ["internal_score", "Score (/100)"] ] as const).map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{format(a.recorded_indicators?.[key], key === "new_installment" || key === "repayment_capacity" ? "money" : "count")}</td><td>{format(a[key], key === "new_installment" || key === "repayment_capacity" ? "money" : "count")}</td></tr>)}</tbody></table></div>
    </Detail>}
  </>;
}
