import type { CustomFieldDefinition } from "@/api/configuration";

export function CustomFields({ definitions, value, onChange }: {
  definitions: CustomFieldDefinition[]; value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void;
}) {
  if (!definitions.length) return null;
  return <div className="form-grid two-col">{definitions.map((field) => {
    const current = value[field.id];
    const set = (next: unknown) => onChange({ ...value, [field.id]: next });
    return <label className="field" key={field.id}><span>{field.label}{field.required ? " *" : ""}</span>
      {field.type === "boolean" ? <select value={current == null ? "" : String(current)} onChange={(event) => set(event.target.value === "" ? null : event.target.value === "true")}>
        <option value="">Non renseigné</option><option value="true">Oui</option><option value="false">Non</option></select>
        : field.type === "choice" ? <select value={String(current ?? "")} onChange={(event) => set(event.target.value || null)}>
          <option value="">Sélectionner…</option>{field.choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}</select>
          : <input type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
            step={field.type === "number" ? "0.000001" : undefined} maxLength={field.type === "text" ? 4000 : undefined}
            value={String(current ?? "")} onChange={(event) => set(event.target.value || null)} />}
      {field.required && <small className="muted">Requis pour la validation KYC ou la soumission du dossier ; le brouillon peut rester incomplet.</small>}
    </label>;
  })}</div>;
}
