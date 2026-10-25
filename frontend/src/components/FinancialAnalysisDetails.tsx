import type { AnalysisDetails } from "@/api/types";
import { formatMoney } from "@/components/ui";

type Column = { key: string; label: string; type?: string };
export const ANALYSIS_TABLES: Record<string, { label: string; columns: Column[] }> = {
  products: { label: "Fiches produits / services — période de référence", columns: [
    { key: "name", label: "Produit / service" }, { key: "unit", label: "Unité" },
    { key: "quantity", label: "Quantité vendue", type: "number" },
    { key: "sale_price", label: "Prix de vente unitaire", type: "number" },
    { key: "unit_cost", label: "Coût unitaire", type: "number" },
    { key: "comment", label: "Source / observation" },
  ] },
  stocks: { label: "Inventaire et qualité du stock — à la date d'arrêté", columns: [
    { key: "name", label: "Article / catégorie" },
    { key: "quantity", label: "Quantité", type: "number" },
    { key: "unit_cost", label: "Coût unitaire", type: "number" },
    { key: "impaired_value", label: "Dépréciation totale (obsolescence / pertes)", type: "number" },
    { key: "count_date", label: "Date d'inventaire", type: "date" },
    { key: "comment", label: "Propriété, rotation, péremption, gage" },
  ] },
  debts: { label: "Engagements par prêteur — sans double comptage", columns: [
    { key: "lender", label: "Prêteur / institution / tontine" },
    { key: "kind", label: "Nature du concours / garantie donnée" },
    { key: "outstanding", label: "Capital restant dû", type: "number" },
    { key: "monthly_payment", label: "Service mensuel équivalent", type: "number" },
    { key: "arrears", label: "Impayés", type: "number" },
    { key: "maturity", label: "Échéance finale", type: "date" },
    { key: "comment", label: "Source, périodicité, refinancement, sûretés" },
  ] },
  cashflow: { label: "Plan mensuel de trésorerie — inclure les mois creux", columns: [
    { key: "month", label: "Mois", type: "month" },
    { key: "inflows", label: "Encaissements", type: "number" },
    { key: "outflows", label: "Sorties de trésorerie hors dette et investissement", type: "number" },
    { key: "investment", label: "Investissements", type: "number" },
    { key: "existing_service", label: "Service des dettes existantes", type: "number" },
    { key: "new_service", label: "Échéance du nouveau crédit et épargne obligatoire", type: "number" },
    { key: "comment", label: "Hypothèses, saisonnalité, récolte / campagne" },
  ] },
  history: { label: "Historique financier — périodes de même durée", columns: [
    { key: "period", label: "Exercice / période" },
    { key: "turnover", label: "Chiffre d'affaires", type: "number" },
    { key: "net_result", label: "Résultat net", type: "number" },
    { key: "cashflow", label: "Cash-flow", type: "number" },
    { key: "equity", label: "Capitaux propres", type: "number" },
    { key: "comment", label: "Durée, pièces, événements exceptionnels" },
  ] },
};

export function FinancialAnalysisDetails({ name, value, onChange, currency = "XOF" }: {
  name: string;
  value: AnalysisDetails;
  onChange?: (next: AnalysisDetails) => void;
  currency?: string;
}) {
  const schema = ANALYSIS_TABLES[name];
  const source = value[name];
  const rows = Array.isArray(source) ? source : [];
  if (!onChange && !rows.length) return null;
  if (!onChange) {
    const display = (content: unknown, column: Column) => {
      if (content == null || content === "") return "—";
      if (column.type === "number") {
        const number = Number(content);
        return Number.isFinite(number) ? column.key === "quantity" ? number.toLocaleString("fr-FR") : formatMoney(number, currency) : "—";
      }
      if (column.type === "date") return new Date(`${content}T00:00:00`).toLocaleDateString("fr-FR");
      return String(content);
    };
    return <details className="subsection"><summary className="subsection-title">{schema.label} ({rows.length})</summary>
      <div className="table-scroll"><table className="table"><thead><tr>{schema.columns.map((column) => <th scope="col" key={column.key}>{column.label}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => <tr key={index}>{schema.columns.map((column) => <td key={column.key}>{display(row[column.key], column)}</td>)}</tr>)}</tbody>
      </table></div></details>;
  }
  function update(index: number, key: string, content: string) {
    onChange?.({ ...value, [name]: rows.map((row, i) => i === index ? { ...row, [key]: content } : row) });
  }
  return <div className="stack">
    <p className="subsection-label">{schema.label}</p>
    {rows.map((row, index) => <div className="stack" key={index}>
      <p className="muted small">Ligne {index + 1}</p>
      <div className="form-grid two-col">
        {schema.columns.map((column) => <label className="field" key={column.key}>
          <span>{column.label}</span>
          <input
            type={column.type || "text"}
            step={column.type === "number" ? "any" : undefined}
            value={row[column.key] ?? ""}
            onChange={(event) => update(index, column.key, event.target.value)}
          />
        </label>)}
      </div>
      <button type="button" className="btn btn-ghost" onClick={() => onChange({ ...value, [name]: rows.filter((_, i) => i !== index) })}>Retirer la ligne</button>
    </div>)}
    {rows.length < 120 && <button type="button" className="btn btn-ghost" onClick={() => onChange({ ...value, [name]: [...rows, {}] })}>Ajouter une ligne</button>}
  </div>;
}
