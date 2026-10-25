import type { ExposureRules } from "@/api/exposure";

export function ConfigurationExposureEditor({ value, defaults, onChange, disabled }: {
  value?: ExposureRules; defaults: ExposureRules; onChange: (value: ExposureRules | undefined) => void; disabled: boolean;
}) {
  const rules = value || defaults;
  const set = <K extends keyof ExposureRules>(key: K, next: ExposureRules[K]) => onChange({ ...rules, [key]: next });
  return <section className="card"><div className="card-title">Engagements et plafonds consolidés</div><div className="card-body">
    <p className="muted small">Situations externes complètes et vérifiées sur justificatif. Les relations économiques restent limitées à la filiale et aucune conversion de devise n'est automatique.</p>
    <label className="field"><span><input type="checkbox" disabled={disabled} checked={!!value} onChange={(e) => onChange(e.target.checked ? { ...defaults } : undefined)} /> Adapter ces règles</span></label>
    {value && <fieldset disabled={disabled} style={{ border: 0, padding: 0, margin: 0 }}>
      <label className="field"><span><input type="checkbox" checked={rules.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Activer le contrôle des engagements</span></label>
      <div className="form-grid two-col">
        <label className="field"><span>Devise des plafonds</span><input maxLength={3} value={rules.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></label>
        <label className="field"><span>Début du blocage (contrôles répétés ensuite)</span><select value={rules.gate} onChange={(e) => set("gate", e.target.value as ExposureRules["gate"])}><option value="ALERT">Alerte seulement</option><option value="SUBMIT">Soumission</option><option value="APPROVE">Accord final</option><option value="SETUP">Mise en place</option></select></label>
        {([['client_limit', 'Plafond par client'], ['group_limit', 'Plafond du groupe lié']] as const).map(([key, label]) => <label className="field" key={key}><span>{label} (vide : aucun)</span><input type="number" min="0" step="0.01" value={rules[key] ?? ""} onChange={(e) => set(key, e.target.value === "" ? null : e.target.value)} /></label>)}
        <label className="field"><span>Ancienneté maximale en jours (0 : sans limite)</span><input type="number" min="0" max="36500" value={rules.maximum_age_days} onChange={(e) => set("maximum_age_days", Number(e.target.value))} /></label>
      </div>
      {([['include_pending', 'Inclure les autres demandes en circuit'], ['require_verified_snapshot', 'Exiger une situation complète et vérifiée pour chaque client lié'], ['use_cbs_client_limit', 'Contrôler aussi le plafond client communiqué par le CBS']] as const).map(([key, label]) => <label className="field" key={key}><span><input type="checkbox" checked={rules[key]} onChange={(e) => set(key, e.target.checked)} /> {label}</span></label>)}
    </fieldset>}
  </div></section>;
}
