import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { BusinessCalendar, Paginated, WorkflowDefinition } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { Card, QueryStatus } from "@/components/ui";

function errorMessage(error: unknown) {
  const response = (error as { response?: { data?: { errors?: unknown } } }).response?.data;
  const errors = response?.errors;
  if (typeof errors === "string") return errors;
  if (Array.isArray(errors)) return errors.join(" · ");
  if (errors && typeof errors === "object") return Object.values(errors).flat().map(String).join(" · ");
  return "Enregistrement impossible. Vérifiez les paramètres et vos droits.";
}

export function useBusinessCalendars() {
  const { user, activeTenant } = useAuth();
  return useQuery({
    queryKey: ["business-calendars", activeTenant],
    enabled: hasPerm(user, "workflow.view_businesscalendar") && !(user?.is_group_level && !activeTenant),
    queryFn: async () => (await api.get<Paginated<BusinessCalendar>>("/business-calendars/", { params: { page_size: 200 } })).data,
  });
}

export function WorkflowExecutionFields({ mode, calendar, onChange }: {
  mode: string; calendar: string; onChange: (mode: string, calendar: string) => void;
}) {
  const calendars = useBusinessCalendars();
  return <>
    <label className="field"><span>Exécution des étapes</span><select value={mode} onChange={(e) => onChange(e.target.value, calendar)}>
      <option value="EXPLICIT_MODE">Modes séquentiel / parallèle explicites</option>
      <option value="LEGACY_ORDER">Historique : même ordre en parallèle</option>
    </select></label>
    <label className="field"><span>Calendrier des délais ouvrés</span><select value={calendar} onChange={(e) => onChange(mode, e.target.value)}>
      <option value="">Aucun — délais en heures continues</option>
      {(calendars.data?.results ?? []).filter((item) => item.is_active || item.id === calendar).map((item) => <option key={item.id} value={item.id} disabled={!item.is_active}>{item.name}{!item.is_active ? " (inactif)" : ""}</option>)}
    </select>{calendars.isError && <span className="form-error">Chargement des calendriers impossible.</span>}</label>
  </>;
}

export function WorkflowExecutionSettings({ definition }: { definition: WorkflowDefinition }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [mode, setMode] = useState<string>(definition.execution_mode);
  const [calendar, setCalendar] = useState(definition.business_calendar ?? "");
  const [error, setError] = useState("");
  const calendars = useBusinessCalendars();
  const save = useMutation({
    mutationFn: () => api.patch(`/workflow-definitions/${definition.id}/`, { execution_mode: mode, business_calendar: calendar || null }),
    onSuccess: () => { setError(""); qc.invalidateQueries({ queryKey: ["workflow-definitions"] }); },
    onError: (e) => setError(errorMessage(e)),
  });
  return <div className="card" style={{ marginBottom: 14, padding: 12, background: "var(--surface-2)" }}>
    <strong>Exécution et délais</strong>
    {definition.is_used || !hasPerm(user, "workflow.change_workflowdefinition") ? <p className="muted small">
      {definition.execution_mode === "LEGACY_ORDER" ? "Parallélisme historique par numéro d'ordre" : "Modes séquentiel et parallèle explicites"} · Calendrier : {calendars.data?.results.find((item) => item.id === definition.business_calendar)?.name ?? (definition.business_calendar ? "associé" : "aucun")}.
      {definition.is_used && " Dupliquez le circuit pour modifier ces paramètres."}
    </p> : <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="form-grid"><WorkflowExecutionFields mode={mode} calendar={calendar} onChange={(value, id) => { setMode(value); setCalendar(id); }} /></div>
      <p className="muted small">Les étapes d'un même ordre doivent être parallèles en mode explicite. Toutes doivent être traitées pour avancer. Le calendrier est figé à chaque démarrage de circuit.</p>
      {error && <div className="form-error">{error}</div>}
      <button className="btn btn-primary btn-sm" disabled={save.isPending}>Enregistrer l'exécution</button>
    </form>}
  </div>;
}

type CalendarForm = Omit<BusinessCalendar, "id" | "updated_at" | "holidays"> & { holidaysText: string };
const EMPTY: CalendarForm = { code: "", name: "", timezone: "UTC", working_days: [0, 1, 2, 3, 4], opening_time: "08:00", closing_time: "17:00", holidaysText: "", is_active: true };
const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

export function BusinessCalendarsEditor() {
  const { user } = useAuth();
  const calendars = useBusinessCalendars();
  const qc = useQueryClient();
  const [id, setId] = useState<string | null>(null);
  const [form, setForm] = useState<CalendarForm>({ ...EMPTY });
  const [error, setError] = useState("");
  const canView = hasPerm(user, "workflow.view_businesscalendar");
  const canWrite = hasPerm(user, id ? "workflow.change_businesscalendar" : "workflow.add_businesscalendar");
  const save = useMutation({
    mutationFn: () => {
      const { holidaysText, ...values } = form;
      const payload = { ...values, holidays: holidaysText.split(/[\n,;]+/).map((value) => value.trim()).filter(Boolean) };
      return id ? api.patch(`/business-calendars/${id}/`, payload) : api.post("/business-calendars/", payload);
    },
    onSuccess: () => { setError(""); setId(null); setForm({ ...EMPTY }); qc.invalidateQueries({ queryKey: ["business-calendars"] }); },
    onError: (e) => setError(errorMessage(e)),
  });
  if (!canView) return null;
  return <Card title="Calendriers ouvrés de la filiale">
    <p className="muted small">Définissez les horaires locaux, jours ouvrés et jours fériés explicites. Les modifications s'appliquent aux circuits démarrés ensuite.</p>
    <QueryStatus isLoading={calendars.isLoading} isError={calendars.isError} isEmpty={!calendars.data?.results.length} emptyMessage="Aucun calendrier configuré." onRetry={() => calendars.refetch()}>
      <table className="table"><thead><tr><th>Calendrier</th><th>Fuseau et horaires</th><th>Statut</th><th></th></tr></thead><tbody>
        {(calendars.data?.results ?? []).map((item) => <tr key={item.id}><td>{item.code} · {item.name}</td><td>{item.timezone} · {item.opening_time.slice(0, 5)}–{item.closing_time.slice(0, 5)}</td><td>{item.is_active ? "Actif" : "Inactif"}</td><td>
          <button className="btn btn-ghost btn-sm" onClick={() => { const { holidays, ...values } = item; setId(item.id); setForm({ ...values, holidaysText: holidays.join("\n") }); setError(""); }}>Ouvrir</button>
        </td></tr>)}
      </tbody></table>
    </QueryStatus>
    <form className="stack" onSubmit={(e: FormEvent) => { e.preventDefault(); if (canWrite) save.mutate(); }}>
      <p className="field-legend">{id ? "Modifier le calendrier" : "Nouveau calendrier"}</p>
      <fieldset disabled={!canWrite || save.isPending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="form-grid">
          <label className="field"><span>Code</span><input required maxLength={50} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
          <label className="field"><span>Nom</span><input required maxLength={255} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="field"><span>Fuseau IANA</span><input required value={form.timezone} placeholder="Africa/Abidjan" onChange={(e) => setForm({ ...form, timezone: e.target.value })} /><span className="muted small">Ex. Africa/Abidjan, Africa/Dakar, Africa/Porto-Novo.</span></label>
          <label className="field"><span>Ouverture</span><input required type="time" value={form.opening_time.slice(0, 5)} onChange={(e) => setForm({ ...form, opening_time: e.target.value })} /></label>
          <label className="field"><span>Fermeture</span><input required type="time" value={form.closing_time.slice(0, 5)} onChange={(e) => setForm({ ...form, closing_time: e.target.value })} /></label>
          <label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /><span>Actif pour les prochains circuits</span></label>
        </div>
        <div className="row-actions" style={{ flexWrap: "wrap", marginTop: 12 }}>{DAYS.map((day, index) => <label className="checkbox" key={day}><input type="checkbox" checked={form.working_days.includes(index)} onChange={(e) => setForm({ ...form, working_days: e.target.checked ? [...form.working_days, index].sort() : form.working_days.filter((value) => value !== index) })} /><span>{day}</span></label>)}</div>
        <label className="field"><span>Jours fériés (une date AAAA-MM-JJ par ligne)</span><textarea rows={4} value={form.holidaysText} onChange={(e) => setForm({ ...form, holidaysText: e.target.value })} /></label>
      </fieldset>
      {error && <div className="form-error">{error}</div>}
      <div className="row-actions">{canWrite && <button className="btn btn-primary btn-sm" disabled={save.isPending}>Enregistrer le calendrier</button>}{id && <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setId(null); setForm({ ...EMPTY }); setError(""); }}>Fermer / Nouveau</button>}</div>
    </form>
  </Card>;
}
