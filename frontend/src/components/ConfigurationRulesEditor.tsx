import type { ConfigurationCatalogue, ConfigurationOverrides, EligibilityRule, ScoreCriterion, ScoringGrid } from "@/api/configuration";
import { Card } from "@/components/ui";

export const RULE_EFFECT_LABELS: Record<string, string> = {
  ALERT: "Alerte", BLOCK_SUBMIT: "Blocage à la soumission", BLOCK_APPROVE: "Blocage à l'approbation", BLOCK_SETUP: "Blocage avant mise en place",
};
export const RULE_OPERATOR_LABELS: Record<string, string> = {
  gte: "Au moins", lte: "Au maximum", eq: "Égal à", in: "Parmi les valeurs", not_in: "Hors des valeurs",
};

export function ConfigurationRulesEditor({ value, catalogue, clientType, disabled, onChange }: {
  value: ConfigurationOverrides;
  catalogue: ConfigurationCatalogue;
  clientType: string;
  disabled: boolean;
  onChange: (value: ConfigurationOverrides) => void;
}) {
  const ownRules = Object.prototype.hasOwnProperty.call(value.eligibility || {}, "rules");
  const rules = value.eligibility?.rules || [];
  const ownGrid = !!value.scoring?.grid;
  const grid = value.scoring?.grid || catalogue.default_grid;
  const metricLabel = (key: string) => catalogue.score_metrics.find((field) => field.key === key)?.label || key;
  function setRules(next: EligibilityRule[]) { onChange({ ...value, eligibility: { rules: next } }); }
  function setRule(index: number, next: EligibilityRule) { setRules(rules.map((row, position) => position === index ? next : row)); }
  function setGrid(next: ScoringGrid) { onChange({ ...value, scoring: { grid: next } }); }
  function setCriterion(index: number, next: ScoreCriterion) {
    setGrid({ ...grid, criteria: grid.criteria.map((row, position) => position === index ? next : row) });
  }
  const total = grid.criteria.reduce((sum, row) => sum + (Number(row.weight) || 0), 0);

  return <>
    <Card title="Éligibilité du produit et de la clientèle">
      <p className="muted">Les conditions utilisent des données du dossier et de son analyse de référence. Elles ne remplacent pas une consultation du CBS ou du bureau de crédit.</p>
      <label className="checkbox-line"><input type="checkbox" disabled={disabled} checked={ownRules} onChange={(e) => {
        if (e.target.checked) setRules([]); else onChange({ ...value, eligibility: {} });
      }} />Définir la liste des règles dans ce profil</label>
      {ownRules ? <>
        <p className="muted">Cette liste remplace celle héritée. Une liste vide supprime les règles héritées pour ce périmètre ; l'aperçu permet de voir cet effet.</p>
        {rules.map((rule, index) => {
          const definition = catalogue.eligibility_criteria.find((field) => field.key === rule.criterion);
          const kind = definition?.type || "number";
          return <div className="card" key={rule.id}><div className="card-body">
            <div className="form-grid two-col">
              <label className="field"><span>Condition {index + 1}</span><select disabled={disabled} value={rule.criterion} onChange={(e) => {
                const field = catalogue.eligibility_criteria.find((item) => item.key === e.target.value);
                setRule(index, { ...rule, criterion: e.target.value, operator: field?.type === "text" ? "in" : field?.type === "boolean" ? "eq" : "gte",
                  value: field?.type === "text" ? [""] : field?.type === "boolean" ? true : "0" });
              }}>{catalogue.eligibility_criteria.map((field) => <option key={field.key} value={field.key}>{field.label}</option>)}</select></label>
              <label className="field"><span>Comparaison</span><select disabled={disabled} value={rule.operator} onChange={(e) => setRule(index, { ...rule, operator: e.target.value as EligibilityRule["operator"] })}>
                {(kind === "text" ? ["in", "not_in"] : kind === "boolean" ? ["eq"] : ["gte", "lte", "eq"]).map((key) => <option key={key} value={key}>{RULE_OPERATOR_LABELS[key]}</option>)}</select></label>
              <label className="field"><span>Valeur attendue</span>{kind === "boolean" ? <select disabled={disabled} value={String(rule.value)} onChange={(e) => setRule(index, { ...rule, value: e.target.value === "true" })}>
                <option value="true">Oui</option><option value="false">Non</option></select>
                : kind === "text" ? <><input disabled={disabled} value={Array.isArray(rule.value) ? rule.value.join(", ") : String(rule.value)}
                  onChange={(e) => setRule(index, { ...rule, value: e.target.value.split(",").map((item) => item.trim()) })} />
                  <small className="muted">Valeurs séparées par des virgules, selon les codes du référentiel concerné.</small></>
                  : <input type="number" step="any" min="0" disabled={disabled} value={String(rule.value)} onChange={(e) => setRule(index, { ...rule, value: e.target.value })} />}</label>
              {kind === "text" && !!definition?.choices.length && <label className="field"><span>Ajouter une valeur du référentiel</span><select value="" disabled={disabled} onChange={(e) => {
                const selected = Array.isArray(rule.value) ? rule.value.filter(Boolean) : [];
                if (e.target.value && !selected.includes(e.target.value)) setRule(index, { ...rule, value: [...selected, e.target.value] });
              }}><option value="">Choisir une valeur…</option>{definition.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label} ({choice.value})</option>)}</select></label>}
              <label className="field"><span>Effet si la condition échoue</span><select disabled={disabled} value={rule.effect} onChange={(e) => setRule(index, { ...rule, effect: e.target.value as EligibilityRule["effect"] })}>
                {Object.entries(RULE_EFFECT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
              <label className="field"><span>Donnée manquante</span><select disabled={disabled} value={rule.missing} onChange={(e) => setRule(index, { ...rule, missing: e.target.value as EligibilityRule["missing"] })}>
                <option value="FAIL">Considérer la condition non satisfaite</option><option value="IGNORE">Ignorer le contrôle et le signaler</option></select></label>
            </div>
            {definition?.clients && (!clientType || !definition.clients.includes(clientType)) && <p className="form-error">Sélectionnez un type de clientèle compatible dans le périmètre du profil avant publication.</p>}
            {!disabled && <button type="button" className="btn btn-ghost" onClick={() => setRules(rules.filter((_, position) => position !== index))}>Retirer cette condition</button>}
          </div></div>;
        })}
        {!disabled && <button type="button" className="btn btn-ghost" disabled={rules.length >= 60} onClick={() => setRules([...rules, {
          id: `condition-${Date.now()}-${rules.length}`, criterion: "active_loans_count", operator: "lte", value: "0", effect: "ALERT", missing: "FAIL",
        }])}>Ajouter une condition</button>}
      </> : <p className="muted">Règles héritées. Consultez l'aperçu pour connaître la liste applicable.</p>}
    </Card>
    <Card title="Grille de scoring et classes de risque">
      <label className="checkbox-line"><input type="checkbox" disabled={disabled} checked={ownGrid} onChange={(e) => {
        if (e.target.checked) setGrid(structuredClone(catalogue.default_grid)); else onChange({ ...value, scoring: {} });
      }} />Définir la grille dans ce profil</label>
      {ownGrid ? <>
        <p className="muted">La grille complète remplace celle héritée. Le score intervient dans le circuit selon la méthode de risque choisie dans la politique de crédit.</p>
        <div className="form-grid two-col">
          <label className="field"><span>Méthode de calcul</span><select disabled={disabled} value={grid.engine} onChange={(e) => setGrid({ ...grid,
            engine: e.target.value as ScoringGrid["engine"], criteria: [], missing_data: "RENORMALIZE" })}>
            <option value="LEGACY">Grille existante du logiciel</option><option value="CUSTOM">Grille personnalisée</option></select></label>
          {grid.engine === "CUSTOM" && <label className="field"><span>Indicateur manquant</span><select disabled={disabled} value={grid.missing_data} onChange={(e) => setGrid({ ...grid, missing_data: e.target.value as ScoringGrid["missing_data"] })}>
            <option value="RENORMALIZE">Recalculer sur les indicateurs disponibles</option><option value="ZERO">Attribuer zéro au critère manquant</option><option value="BLOCK_SUBMIT">Exiger tous les indicateurs avant soumission</option></select></label>}
        </div>
        {grid.engine === "CUSTOM" && <>
          <p className={Math.abs(total - 100) < 0.000001 ? "muted" : "form-error"}>Somme des pondérations : {Number(total.toFixed(4))} % — exactement 100 % requis.</p>
          {grid.criteria.map((criterion, index) => <div className="card" key={index}><div className="card-body"><div className="form-grid two-col">
            <label className="field"><span>Indicateur {index + 1}</span><select disabled={disabled} value={criterion.metric} onChange={(e) => setCriterion(index, { ...criterion, metric: e.target.value })}>
              {catalogue.score_metrics.map((field) => <option disabled={grid.criteria.some((row, position) => position !== index && row.metric === field.key)} key={field.key} value={field.key}>{field.label}</option>)}</select></label>
            <label className="field"><span>Pondération (%)</span><input disabled={disabled} type="number" min="0.01" max="100" step="0.01" value={criterion.weight} onChange={(e) => setCriterion(index, { ...criterion, weight: e.target.value })} /></label>
            <label className="field"><span>Sens favorable</span><select disabled={disabled} value={criterion.direction} onChange={(e) => setCriterion(index, { ...criterion, direction: e.target.value as ScoreCriterion["direction"] })}>
              <option value="HIGH">Une valeur plus élevée est meilleure</option><option value="LOW">Une valeur plus faible est meilleure</option></select></label>
            <label className="field"><span>Borne défavorable — note 0</span><input disabled={disabled} type="number" step="any" value={criterion.bad} onChange={(e) => setCriterion(index, { ...criterion, bad: e.target.value })} /></label>
            <label className="field"><span>Borne favorable — note 100</span><input disabled={disabled} type="number" step="any" value={criterion.good} onChange={(e) => setCriterion(index, { ...criterion, good: e.target.value })} /></label>
          </div>
            {!!catalogue.score_metrics.find((field) => field.key === criterion.metric)?.clients && (!clientType || !catalogue.score_metrics.find((field) => field.key === criterion.metric)?.clients?.includes(clientType)) && <p className="form-error">Vérifiez que le type de clientèle du profil correspond à cet indicateur.</p>}
            {!disabled && <button type="button" className="btn btn-ghost" onClick={() => setGrid({ ...grid, criteria: grid.criteria.filter((_, position) => position !== index) })}>Retirer {metricLabel(criterion.metric)}</button>}
          </div></div>)}
          {!disabled && <button type="button" className="btn btn-ghost" disabled={grid.criteria.length >= catalogue.score_metrics.length} onClick={() => {
            const next = catalogue.score_metrics.find((field) => !grid.criteria.some((row) => row.metric === field.key)
              && (!field.clients || (!!clientType && field.clients.includes(clientType))));
            if (next) setGrid({ ...grid, criteria: [...grid.criteria, { metric: next.key, direction: "HIGH", bad: "0", good: "100", weight: "100" }] });
          }}>Ajouter un indicateur</button>}
          <p className="muted small">La note est interpolée entre les deux bornes et limitée à l'intervalle 0–100. Les pondérations ne sont pas ajustées automatiquement.</p>
        </>}
        <p>Seuils des classes de risque : un score au moins égal au seuil entre dans la classe correspondante. La classe 5 regroupe les scores inférieurs au dernier seuil.</p>
        <div className="form-grid two-col">{grid.risk_cutoffs.map((cutoff, index) => <label className="field" key={index}><span>Classe {index + 1} — score minimum</span>
          <input type="number" min="0" max="100" step="0.01" disabled={disabled} value={cutoff} onChange={(e) => setGrid({ ...grid, risk_cutoffs: grid.risk_cutoffs.map((item, position) => position === index ? e.target.value : item) })} /></label>)}</div>
      </> : <p className="muted">Grille héritée. Sans adaptation publiée, le calcul existant et ses classes de risque s'appliquent.</p>}
    </Card>
  </>;
}
