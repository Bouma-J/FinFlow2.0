import type { ConfigurationCatalogue, ConfigurationOverrides, PricingRateKey, PricingTariff } from "@/api/configuration";
import { Card } from "@/components/ui";

const RATES: [PricingRateKey, string][] = [["interest_rate", "Taux annuel"], ["fees_rate", "Frais de dossier"], ["mandatory_savings_rate", "Épargne par échéance"]];

export function ConfigurationPricingEditor({ value, catalogue, disabled, currency, onChange }: {
  value: ConfigurationOverrides; catalogue: ConfigurationCatalogue; disabled: boolean; currency?: string;
  onChange: (value: ConfigurationOverrides) => void;
}) {
  const tariff = value.pricing?.tariff;
  const update = (tariff: PricingTariff) => onChange({ ...value, pricing: { tariff } });
  return <Card title="Tarification des crédits">
    <label className="checkbox"><input type="checkbox" checked={Boolean(tariff)} disabled={disabled} onChange={(e) => e.target.checked
      ? update({ ...structuredClone(catalogue.default_tariff), currency: currency || "" })
      : onChange({ ...value, pricing: {} })} /><span>Définir le barème dans ce profil (sinon : héritage)</span></label>
    {tariff && <fieldset disabled={disabled} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <div className="form-grid two-col">
        <label className="field"><span>Mode</span><select value={tariff.engine} onChange={(e) => update({ ...tariff, engine: e.target.value as PricingTariff["engine"] })}><option value="LEGACY">Tarification existante au dossier</option><option value="CONFIGURED">Barème configurable</option></select></label>
        {tariff.engine === "CONFIGURED" && <label className="field"><span>Devise du barème</span><input required maxLength={3} value={tariff.currency} onChange={(e) => update({ ...tariff, currency: e.target.value.toUpperCase() })} /><span className="muted small">Aucune conversion implicite.</span></label>}
      </div>
      {tariff.engine === "CONFIGURED" && <>
        <p className="muted small">Les taux laissés vides héritent du produit (intérêt et frais de dossier), ou de zéro pour l'épargne. Les bornes sont des règles de l'établissement et doivent être validées par ses responsables.</p>
        {RATES.map(([key, label]) => <div key={key} className="stack"><strong>{label} (%)</strong><div className="form-grid">
          {(["default", "min", "max"] as const).map((field) => <label className="field" key={field}><span>{field === "default" ? "Défaut" : field === "min" ? "Minimum" : "Maximum"}</span><input type="number" min={0} max={key === "interest_rate" ? 999.999 : 100} step="0.001" value={tariff[key][field] ?? ""} placeholder="Hérité / sans borne" onChange={(e) => update({ ...tariff, [key]: { ...tariff[key], [field]: e.target.value || null } })} /></label>)}
          <label className="checkbox"><input type="checkbox" checked={tariff[key].negotiable} onChange={(e) => update({ ...tariff, [key]: { ...tariff[key], negotiable: e.target.checked } })} /><span>Négociable dans les bornes</span></label>
        </div></div>)}
        <div className="form-grid">
          <label className="field"><span>Taxe sur les frais de dossier (%)</span><input type="number" min={0} max={100} step="0.001" value={tariff.processing_tax_rate} onChange={(e) => update({ ...tariff, processing_tax_rate: e.target.value })} /></label>
          <label className="field"><span>Plafond global des frais, taxes comprises (% du capital)</span><input type="number" min={0} max={100} step="0.001" value={tariff.max_total_fees_pct ?? ""} placeholder="Sans plafond supplémentaire" onChange={(e) => update({ ...tariff, max_total_fees_pct: e.target.value || null })} /></label>
          <label className="checkbox"><input type="checkbox" checked={tariff.allow_manual_fees} onChange={(e) => update({ ...tariff, allow_manual_fees: e.target.checked })} /><span>Autoriser les frais additionnels manuels</span></label>
        </div>
        <p className="field-legend">Tranches de montant et durée</p>
        <p className="muted small">Bornes inclusives ; les tranches ne doivent pas se chevaucher. Sans tranche correspondante, les taux par défaut s'appliquent. Un taux vide dans une tranche conserve le défaut.</p>
        {tariff.bands.map((band, index) => <div className="card stack" key={index}>
          <div className="form-grid"><label className="field"><span>Identifiant</span><input required maxLength={40} value={band.id} onChange={(e) => update({ ...tariff, bands: tariff.bands.map((row, i) => i === index ? { ...row, id: e.target.value } : row) })} /></label>
            {(["min_amount", "max_amount", "min_months", "max_months", ...RATES.map(([key]) => key)] as const).map((field) => <label className="field" key={field}><span>{({ min_amount: "Montant min", max_amount: "Montant max", min_months: "Durée min (mois)", max_months: "Durée max (mois)", interest_rate: "Taux annuel (%)", fees_rate: "Frais dossier (%)", mandatory_savings_rate: "Épargne (%)" })[field]}</span><input type="number" min={field.endsWith("months") ? 1 : 0} step={field.endsWith("months") ? "1" : field.endsWith("amount") ? "0.01" : "0.001"} value={band[field] ?? ""} onChange={(e) => update({ ...tariff, bands: tariff.bands.map((row, i) => i === index ? { ...row, [field]: e.target.value === "" ? null : field.endsWith("months") ? Number(e.target.value) : e.target.value } : row) })} /></label>)}
          </div><button type="button" className="btn btn-ghost btn-sm" onClick={() => update({ ...tariff, bands: tariff.bands.filter((_, i) => i !== index) })}>Retirer la tranche</button>
        </div>)}
        <button type="button" className="btn btn-ghost btn-sm" disabled={tariff.bands.length >= 50} onClick={() => update({ ...tariff, bands: [...tariff.bands, { id: `T_${Date.now()}`, min_amount: null, max_amount: null, min_months: null, max_months: null, interest_rate: null, fees_rate: null, mandatory_savings_rate: null }] })}>Ajouter une tranche</button>
        <p className="field-legend">Frais complémentaires du barème</p>
        {tariff.charges.map((fee, index) => <div className="card stack" key={index}><div className="form-grid">
          <label className="field"><span>Code</span><input required maxLength={40} value={fee.code} onChange={(e) => update({ ...tariff, charges: tariff.charges.map((row, i) => i === index ? { ...row, code: e.target.value } : row) })} /></label>
          <label className="field"><span>Libellé</span><input required maxLength={150} value={fee.label} onChange={(e) => update({ ...tariff, charges: tariff.charges.map((row, i) => i === index ? { ...row, label: e.target.value } : row) })} /></label>
          <label className="field"><span>Mode</span><select value={fee.mode} onChange={(e) => update({ ...tariff, charges: tariff.charges.map((row, i) => i === index ? { ...row, mode: e.target.value as "PERCENT" | "AMOUNT" } : row) })}><option value="AMOUNT">Montant fixe</option><option value="PERCENT">Pourcentage du capital</option></select></label>
          {(["value", "min_amount", "max_amount", "tax_rate"] as const).map((field) => <label className="field" key={field}><span>{{ value: "Valeur", min_amount: "Plancher hors taxe", max_amount: "Plafond hors taxe", tax_rate: "Taxe (%)" }[field]}</span><input required={field === "value" || field === "tax_rate"} type="number" min={0} step={field === "tax_rate" || (field === "value" && fee.mode === "PERCENT") ? "0.001" : "0.01"} value={fee[field] ?? ""} onChange={(e) => update({ ...tariff, charges: tariff.charges.map((row, i) => i === index ? { ...row, [field]: e.target.value === "" && (field === "min_amount" || field === "max_amount") ? null : e.target.value } : row) })} /></label>)}
        </div><button type="button" className="btn btn-ghost btn-sm" onClick={() => update({ ...tariff, charges: tariff.charges.filter((_, i) => i !== index) })}>Retirer le frais</button></div>)}
        <button type="button" className="btn btn-ghost btn-sm" disabled={tariff.charges.length >= 30} onClick={() => update({ ...tariff, charges: [...tariff.charges, { code: `F_${Date.now()}`, label: "", mode: "AMOUNT", value: "0", min_amount: null, max_amount: null, tax_rate: "0" }] })}>Ajouter un frais</button>
      </>}
    </fieldset>}
  </Card>;
}
