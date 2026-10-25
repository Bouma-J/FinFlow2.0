import type { ConfigurationCatalogue, ConfigurationOverrides, CustomFieldDefinition, ClientReferences } from "@/api/configuration";
import { Card } from "@/components/ui";

export function ConfigurationFormsEditor({ value, catalogue, disabled, onChange }: {
  value: ConfigurationOverrides; catalogue: ConfigurationCatalogue; disabled: boolean; onChange: (next: ConfigurationOverrides) => void;
}) {
  const forms = value.forms || {};
  const kyc = value.kyc || {};
  const sections = forms.analysis_sections || catalogue.form_sections.map((item) => ({ id: item.id, visible: true }));
  function fields(key: "client_fields" | "analysis_fields", definitions: CustomFieldDefinition[]) {
    onChange({ ...value, forms: { ...forms, [key]: definitions } });
  }
  function updateField(key: "client_fields" | "analysis_fields", index: number, next: CustomFieldDefinition) {
    fields(key, (forms[key] || []).map((field, position) => position === index ? next : field));
  }
  return <>
    <Card title="Formulaires et champs additionnels"><p className="muted">Les listes définies remplacent celles héritées. Conservez les identifiants pour préserver les données existantes ; les valeurs retirées restent conservées en historique.</p>
      {(["client_fields", "analysis_fields"] as const).map((key) => <details key={key}><summary>{key === "client_fields" ? "Fiche client" : "Analyse financière"} — {(forms[key] || []).length} champ(s) explicite(s)</summary>
        {(forms[key] || []).map((field, index) => <div key={index} className="card"><div className="card-body form-grid two-col">
          <label className="field"><span>Identifiant stable</span><input value={field.id} maxLength={40} disabled={disabled} onChange={(event) => updateField(key, index, { ...field, id: event.target.value })} /></label>
          <label className="field"><span>Libellé</span><input value={field.label} maxLength={150} disabled={disabled} onChange={(event) => updateField(key, index, { ...field, label: event.target.value })} /></label>
          <label className="field"><span>Type</span><select value={field.type} disabled={disabled} onChange={(event) => updateField(key, index, { ...field, type: event.target.value as CustomFieldDefinition["type"], choices: event.target.value === "choice" ? field.choices : [] })}>
            <option value="text">Texte</option><option value="number">Nombre</option><option value="boolean">Oui / Non</option><option value="date">Date</option><option value="choice">Choix</option></select></label>
          <label className="checkbox-line"><input type="checkbox" checked={field.required} disabled={disabled} onChange={(event) => updateField(key, index, { ...field, required: event.target.checked })} />Obligatoire à l'étape de contrôle</label>
          {field.type === "choice" && <label className="field"><span>Choix — une valeur par ligne</span><textarea disabled={disabled} value={field.choices.join("\n")} onChange={(event) => updateField(key, index, { ...field, choices: event.target.value.split("\n") })} /></label>}
          <button type="button" className="btn btn-ghost" disabled={disabled} onClick={() => fields(key, (forms[key] || []).filter((_, position) => position !== index))}>Retirer ce champ</button>
        </div></div>)}
        <button type="button" className="btn btn-ghost" disabled={disabled || (forms[key]?.length || 0) >= 50} onClick={() => fields(key, [...(forms[key] || []), { id: "", label: "", type: "text", required: false, choices: [] }])}>Ajouter un champ</button>
        <button type="button" className="btn btn-ghost" disabled={disabled} onClick={() => { const next = { ...forms }; delete next[key]; onChange({ ...value, forms: next }); }}>Hériter des champs</button>
      </details>)}
      <details><summary>Ordre et visibilité des sections d'analyse</summary><p className="muted">Les sections financières, paramètres et conclusion restent visibles. Seules les sections informatives sectorielle et E&S peuvent être masquées, si elles ne contiennent aucune exigence.</p>
        {sections.map((section, index) => <div className="page-actions" key={section.id}>
          <label className="checkbox-line"><input type="checkbox" checked={section.visible} disabled={disabled || !catalogue.form_sections.find((item) => item.id === section.id)?.can_hide}
            onChange={(event) => onChange({ ...value, forms: { ...forms, analysis_sections: sections.map((item, position) => position === index ? { ...item, visible: event.target.checked } : item) } })} />{catalogue.form_sections.find((item) => item.id === section.id)?.label || section.id}</label>
          <button type="button" className="btn btn-ghost" disabled={disabled || index === 0} onClick={() => { const next = [...sections]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange({ ...value, forms: { ...forms, analysis_sections: next } }); }}>Monter</button>
          <button type="button" className="btn btn-ghost" disabled={disabled || index === sections.length - 1} onClick={() => { const next = [...sections]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; onChange({ ...value, forms: { ...forms, analysis_sections: next } }); }}>Descendre</button>
        </div>)}
        <button type="button" className="btn btn-ghost" disabled={disabled} onClick={() => { const next = { ...forms }; delete next.analysis_sections; onChange({ ...value, forms: next }); }}>Hériter de l'organisation</button>
      </details>
    </Card>
    <Card title="Exigences KYC"><p className="muted">Les exigences s'appliquent à la validation KYC et aux contrôles du dossier selon la clientèle, l'agence et le produit. La fiche client seule utilise le contexte sans produit.</p>
      {(["required_fields", "required_documents"] as const).map((key) => <details key={key}><summary>{key === "required_fields" ? "Informations obligatoires" : "Pièces obligatoires"}</summary><div className="form-grid two-col">
        {(key === "required_fields" ? catalogue.kyc_fields : catalogue.kyc_documents).map((field) => <label className="checkbox-line" key={field.key}><input type="checkbox" disabled={disabled} checked={kyc[key]?.includes(field.key) || false}
          onChange={(event) => onChange({ ...value, kyc: { ...kyc, [key]: event.target.checked ? [...(kyc[key] || []), field.key] : (kyc[key] || []).filter((item) => item !== field.key) } })} />{field.label}</label>)}
      </div><button type="button" className="btn btn-ghost" disabled={disabled} onClick={() => { const next = { ...kyc }; delete next[key]; onChange({ ...value, kyc: next }); }}>Hériter de la liste</button></details>)}
      <label className="field"><span>Contrôle d'expiration de la pièce</span><select disabled={disabled} value={kyc.check_expiry === undefined ? "" : String(kyc.check_expiry)} onChange={(event) => { const next = { ...kyc }; if (!event.target.value) delete next.check_expiry; else next.check_expiry = event.target.value === "true"; onChange({ ...value, kyc: next }); }}><option value="">Hériter</option><option value="true">Date obligatoire et non échue</option><option value="false">Désactivé</option></select></label>
      <label className="field"><span>Validité de la revue KYC en jours — 0 : sans limite</span><input type="number" min={0} max={36500} disabled={disabled} value={kyc.validity_days ?? ""} placeholder="Hérité" onChange={(event) => { const next = { ...kyc }; if (!event.target.value) delete next.validity_days; else next.validity_days = Number(event.target.value); onChange({ ...value, kyc: next }); }} /></label>
    </Card>
    <Card title="Référentiels clients extensibles"><p className="muted">Codes stables, désactivation sans effacer les valeurs historiques. Les correspondances CBS restent vides tant que les codes n'ont pas été confirmés par l'établissement.</p>
      {(Object.keys(catalogue.default_references) as (keyof ClientReferences)[]).map((key) => { const explicit = value.references?.[key]; const entries = explicit || catalogue.default_references[key]; return <details key={key}><summary>{{ civility: "Civilités", marital_status: "Situations matrimoniales", id_document_type: "Types de pièces", legal_form: "Formes juridiques" }[key]}</summary>
        <label className="checkbox-line"><input type="checkbox" disabled={disabled} checked={!!explicit} onChange={(event) => { const next = { ...value.references }; if (event.target.checked) next[key] = structuredClone(entries); else delete next[key]; onChange({ ...value, references: next }); }} />Définir ce référentiel</label>
        {explicit?.map((entry, index) => <div className="form-grid two-col" key={index}>
          {(["code", "label", "cbs_code"] as const).map((field) => <label className="field" key={field}><span>{{ code: "Code stable", label: "Libellé", cbs_code: "Code CBS confirmé (facultatif)" }[field]}</span><input disabled={disabled} value={entry[field]} maxLength={field === "code" ? key === "civility" ? 10 : key === "marital_status" ? 15 : 20 : field === "label" ? 150 : 100}
            onChange={(event) => onChange({ ...value, references: { ...value.references, [key]: explicit.map((item, position) => position === index ? { ...item, [field]: event.target.value } : item) } })} /></label>)}
          <label className="checkbox-line"><input type="checkbox" disabled={disabled} checked={entry.active} onChange={(event) => onChange({ ...value, references: { ...value.references, [key]: explicit.map((item, position) => position === index ? { ...item, active: event.target.checked } : item) } })} />Actif pour les nouvelles saisies</label>
        </div>)}
        {!!explicit && <button type="button" className="btn btn-ghost" disabled={disabled || explicit.length >= 200} onClick={() => onChange({ ...value, references: { ...value.references, [key]: [...explicit, { code: "", label: "", active: true, cbs_code: "" }] } })}>Ajouter une valeur</button>}
      </details>; })}
    </Card>
  </>;
}
