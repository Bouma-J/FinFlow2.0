import type { AnalysisDetails } from "@/api/types";

export const FINANCIAL_SUPPLEMENTS: Record<string, string> = {
  income_tax_expense: "Impôt sur le résultat",
  provision_expense: "Dotations aux provisions",
  provision_reversal: "Reprises de provisions",
  exceptional_income: "Produits exceptionnels",
  exceptional_expense: "Charges exceptionnelles",
  fixed_operating_costs: "Dont charges d'exploitation fixes",
  variable_operating_costs: "Dont charges d'exploitation variables",
  bfr_change: "Variation du BFR (hausse positive, baisse négative)",
  maintenance_investment: "Investissements de maintien payés sur la période",
  period_purchases: "Achats de la période (base du délai fournisseurs)",
  opening_stock: "Stock au début de la période",
  opening_receivables: "Créances clients au début de la période",
  opening_supplier_debt: "Dettes fournisseurs au début de la période",
  declared_equity: "Capitaux propres déclarés dans les états financiers",
  opening_cash_balance: "Trésorerie disponible à l'ouverture du premier mois prévisionnel",
  purchase_stress_pct: "Hausse des achats sous stress (%)",
  receivable_delay_days: "Retard clients supplémentaire sous stress (jours)",
};

export function FinancialAnalysisSupplements({ names, value, onChange }: {
  names: string[]; value: AnalysisDetails; onChange: (next: AnalysisDetails) => void;
}) {
  return <div className="form-grid two-col">{names.map((key) => <label className="field" key={key}>
    <span>{FINANCIAL_SUPPLEMENTS[key]}</span>
    <input type="number" step="any" min={["bfr_change", "declared_equity", "opening_cash_balance"].includes(key) ? undefined : 0}
      max={key === "purchase_stress_pct" ? 100 : undefined}
      value={typeof value[key] === "string" ? value[key] : ""}
      onChange={(event) => onChange({ ...value, [key]: event.target.value })} />
    <small className="muted">Facultatif. Laisser vide si inconnu ; saisir 0 si vérifié nul.</small>
  </label>)}</div>;
}
