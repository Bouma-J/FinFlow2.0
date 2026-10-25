import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Paginated } from "@/api/types";
import { DAY_COUNT_LABELS, DUE_ADJUSTMENT_LABELS, type SimulationConventions } from "@/api/simulation";
import { useAuth } from "@/auth/AuthContext";

export function SimulationConventionsEditor({ value, defaults, readonly, onChange }: {
  value: SimulationConventions | undefined; defaults: SimulationConventions; readonly: boolean;
  onChange: (value: SimulationConventions | undefined) => void;
}) {
  const { activeTenant, user } = useAuth();
  const calendars = useQuery({
    queryKey: ["simulation-calendars", activeTenant, user?.tenant],
    queryFn: async () => (await api.get<Paginated<{ id: string; name: string; is_active: boolean }>>("/business-calendars/", { params: { is_active: true, page_size: 200 } })).data,
    enabled: !readonly && Boolean(user?.tenant || activeTenant),
  });
  const rules = value ?? defaults;
  function set<K extends keyof SimulationConventions>(key: K, next: SimulationConventions[K]) {
    const { calendar_snapshot: _snapshot, periods_per_year: _frequencies, ...editable } = rules;
    onChange({ ...editable, [key]: next });
  }
  return <section className="stack">
    <h3>Conventions du simulateur et des échéanciers</h3>
    <p className="muted">Les mêmes conventions s'appliquent à l'analyse de capacité et à l'échéancier local du prêt. Vérifier leur concordance avec les conditions appliquées dans le CBS.</p>
    <label className="checkbox"><input type="checkbox" disabled={readonly} checked={value !== undefined} onChange={(event) => onChange(event.target.checked ? structuredClone(defaults) : undefined)} /><span>Adapter les conventions de calcul</span></label>
    {value !== undefined && <fieldset disabled={readonly} className="stack">
      <div className="form-grid two-col">
        <label className="field"><span>Moteur</span><select value={rules.engine} onChange={(event) => set("engine", event.target.value as SimulationConventions["engine"])}><option value="LEGACY">Historique conservé</option><option value="CONFIGURED">Conventions configurées</option></select></label>
        {rules.engine === "CONFIGURED" && <>
          <label className="field"><span>Base des intérêts</span><select value={rules.day_count} onChange={(event) => set("day_count", event.target.value as SimulationConventions["day_count"])}>{Object.entries(DAY_COUNT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="field"><span>Pas d'arrondi monétaire</span><input type="number" min="0.01" max="1000" step="0.01" value={rules.amount_step} onChange={(event) => set("amount_step", event.target.value)} /></label>
          <label className="field"><span>Règle d'arrondi</span><select value={rules.rounding} onChange={(event) => set("rounding", event.target.value as SimulationConventions["rounding"])}><option value="HALF_UP">Au plus proche, moitié supérieure</option><option value="HALF_EVEN">Au plus proche, moitié vers le pair</option></select></label>
          <label className="field"><span>Ajustement des dates</span><select value={rules.due_adjustment} onChange={(event) => set("due_adjustment", event.target.value as SimulationConventions["due_adjustment"])}>{Object.entries(DUE_ADJUSTMENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="field"><span>Dates pour calculer les intérêts</span><select value={rules.interest_dates} onChange={(event) => set("interest_dates", event.target.value as SimulationConventions["interest_dates"])}><option value="NOMINAL">Échéances nominales, avant ajustement</option><option value="ADJUSTED">Échéances ajustées</option></select></label>
          <label className="field"><span>Calendrier ouvré de la filiale</span><select value={rules.calendar ?? ""} onChange={(event) => set("calendar", event.target.value || null)}><option value="">Aucun (dates non ajustées)</option>{rules.calendar && !calendars.data?.results.some((calendar) => calendar.id === rules.calendar) && <option value={rules.calendar}>{rules.calendar_snapshot?.name ?? "Calendrier conservé / à vérifier"}</option>}{calendars.data?.results.map((calendar) => <option key={calendar.id} value={calendar.id}>{calendar.name}</option>)}</select></label>
        </>}
      </div>
      {rules.engine === "LEGACY" ? <p className="muted">Calcul historique conservé : base réelle / 365, arrondi à la dizaine, premier intérêt dégressif sur période théorique et report des seules dates intermédiaires du week-end.</p> : <p className="muted">Le calendrier actif sélectionné est copié lors de la conservation des règles du dossier. La première période porte sur les dates réelles choisies ; la dernière échéance solde exactement le capital restant. Les différés et la capitalisation des intérêts ne sont pas définis par ces réglages.</p>}
      {calendars.isError && <p className="form-error">Les calendriers n'ont pas pu être chargés. Le serveur contrôlera leur filiale et leur activation.</p>}
    </fieldset>}
  </section>;
}
