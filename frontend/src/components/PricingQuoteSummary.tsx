import type { PricingQuote } from "@/api/types";
import { formatMoney } from "@/components/ui";
import { DAY_COUNT_LABELS, DUE_ADJUSTMENT_LABELS } from "@/api/simulation";

export function PricingQuoteSummary({ quote }: { quote: PricingQuote }) {
  return <div className="stack">
    <p className="muted small">{quote.engine === "CONFIGURED" ? "Barème configuré" : "Conditions du dossier"}{quote.band ? ` · Tranche ${quote.band}` : ""} · {quote.currency}. Taux annuel : {quote.rates.interest_rate} % ; frais de dossier : {quote.rates.fees_rate} % ; épargne par échéance : {quote.rates.mandatory_savings_rate} %.</p>
    {quote.simulation_conventions?.engine === "CONFIGURED" && <p className="muted small">Intérêts : {DAY_COUNT_LABELS[quote.simulation_conventions.day_count]}. Pas monétaire : {quote.simulation_conventions.amount_step} {quote.currency}. Arrondi {quote.simulation_conventions.rounding === "HALF_EVEN" ? "moitié vers le pair" : "moitié supérieure"}. Dates : {DUE_ADJUSTMENT_LABELS[quote.simulation_conventions.due_adjustment]}. Base : dates {quote.simulation_conventions.interest_dates === "NOMINAL" ? "nominales" : "ajustées"}{quote.simulation_conventions.calendar_snapshot ? ` · ${quote.simulation_conventions.calendar_snapshot.name}` : ""}.</p>}
    {quote.failures.length > 0 && <ul className="form-error">{quote.failures.map((failure) => <li key={failure}>{failure}</li>)}</ul>}
    {quote.fees.lines.length > 0 && <table className="table"><thead><tr><th>Frais</th><th className="num">Base / hors taxe</th><th className="num">Taxe sur frais</th><th className="num">Total</th></tr></thead><tbody>
      {quote.fees.lines.map((line, index) => <tr key={index}><td>{line.label}</td><td className="num">{formatMoney(line.base_excluding_tax ?? line.amount, quote.currency)}</td><td className="num">{line.tax_amount == null ? "—" : formatMoney(line.tax_amount, quote.currency)}</td><td className="num">{formatMoney(line.amount, quote.currency)}</td></tr>)}
    </tbody><tfoot><tr><td colSpan={3}>Total des frais et taxes sur frais</td><td className="num">{formatMoney(quote.fees.total, quote.currency)}</td></tr></tfoot></table>}
    <p className="muted small">Le détail couvre les frais renseignés et les taxes paramétrées sur ces frais. Les prélèvements sont réalisés dans le CBS ; les conditions doivent y être vérifiées avant mise en place. L'épargne est présentée séparément du coût du crédit.</p>
  </div>;
}
