import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { Agency, CreditProduct, CreditApplication, Paginated } from "@/api/types";
import {
  DETAIL_TABLE_LABELS, type ConfigurationCatalogue, type ConfigurationOverrides,
  type ConfigurationPreview, type ConfigurationProfile, type EffectiveConfiguration, type ParameterDefinition,
} from "@/api/configuration";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { Card, ErrorState, PageHeader, PaginationBar, Spinner, TenantScopeNotice } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";
import { ConfigurationRulesEditor, RULE_EFFECT_LABELS, RULE_OPERATOR_LABELS } from "@/components/ConfigurationRulesEditor";
import { ConfigurationPricingEditor } from "@/components/ConfigurationPricingEditor";
import { PricingQuoteSummary } from "@/components/PricingQuoteSummary";
import { ConfigurationFormsEditor } from "@/components/ConfigurationFormsEditor";
import { SimulationConventionsEditor } from "@/components/SimulationConventionsEditor";
import { ConfigurationExposureEditor } from "@/components/ConfigurationExposureEditor";

type Editable = Pick<ConfigurationProfile, "code" | "name" | "product" | "agency" | "client_type" |
  "individual_profile" | "effective_from" | "overrides" | "reason" | "locked_keys">;
const empty = (): Editable => ({ code: "", name: "", product: null, agency: null, client_type: "",
  individual_profile: "", effective_from: null, reason: "", locked_keys: [], overrides: { policy: {}, thresholds: {}, analysis: {} } });
const STATUS: Record<string, string> = { DRAFT: "Brouillon", REVIEW: "À valider", PUBLISHED: "Publié", RETIRED: "Retiré" };
const CLIENTS: Record<string, string> = { "": "Tous", INDIVIDUAL: "Personne physique", CORPORATE: "Personne morale", PROFESSIONAL: "Groupement" };
const PROFILES: Record<string, string> = { "": "Tous", SALARIE: "Salarié", INDEPENDANT: "Indépendant / AGR", MIXTE: "Mixte" };
const ANALYSIS_LABELS: Record<string, string> = {
  required_fields: "Champs et vérifications requis", required_detail_tables: "Tableaux détaillés requis",
  minimum_bank_statement_months: "Nombre minimal de mois de relevés",
};

async function options<T>(path: string): Promise<T[]> {
  const result: T[] = [];
  let page = 1;
  while (true) {
    const { data } = await api.get<Paginated<T>>(path, { params: { page, page_size: 200 } });
    result.push(...data.results);
    if (!data.next) return result;
    page++;
  }
}

function localDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function AdminConfigurationPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const [manageGroup, setManageGroup] = useState(false);
  const groupMode = Boolean(user?.is_group_level && (manageGroup || !activeTenant));
  const scope = `${activeTenant || user?.tenant || ""}:${groupMode ? "GROUP" : "TENANT"}`;
  const needsTenant = false;
  const configurationUrl = (path: string) => `${path}${groupMode ? "?scope=group" : ""}`;
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<ConfigurationProfile | null>(null);
  const [form, setForm] = useState<Editable | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<ConfigurationPreview | null>(null);
  const [previewApplication, setPreviewApplication] = useState("");
  const [withdrawReason, setWithdrawReason] = useState("");
  const [context, setContext] = useState({ product: "", agency: "", client_type: "", individual_profile: "" });
  const canCreate = hasPerm(user, "configuration.add_configurationprofile");
  const canEdit = hasPerm(user, "configuration.change_configurationprofile");
  const canPublish = hasPerm(user, "configuration.publish_configurationprofile");
  const canPreview = hasPerm(user, "configuration.preview_configurationprofile");
  const editable = !!form && (!selected ? canCreate : selected.status === "DRAFT" && canEdit);
  const catalogue = useQuery({ queryKey: ["configuration-catalogue", scope], enabled: !needsTenant,
    queryFn: async () => (await api.get<ConfigurationCatalogue>(configurationUrl("/configuration-profiles/catalogue/"))).data });
  const profiles = useQuery({ queryKey: ["configuration-profiles", scope, page], enabled: !needsTenant,
    queryFn: async () => (await api.get<Paginated<ConfigurationProfile>>(configurationUrl("/configuration-profiles/"), { params: { page } })).data });
  const products = useQuery({ queryKey: ["configuration-products", scope], enabled: !!(activeTenant || user?.tenant),
    queryFn: () => options<CreditProduct>("/credit-products/") });
  const agencies = useQuery({ queryKey: ["configuration-agencies", scope], enabled: !!(activeTenant || user?.tenant),
    queryFn: () => options<Agency>("/agencies/") });
  const applications = useQuery({ queryKey: ["configuration-preview-applications", scope],
    enabled: !!(activeTenant || user?.tenant) && canPreview && !!selected && hasPerm(user, "credits.view_creditapplication"),
    queryFn: () => options<CreditApplication>("/credit-applications/") });

  useEffect(() => {
    setSelected(null); setForm(null); setPreview(null); setError(null); setNotice(null); setPage(1); setDirty(false);
    setPreviewApplication("");
  }, [scope]);

  function open(profile: ConfigurationProfile) {
    setSelected(profile); setForm(structuredClone(profile)); setDirty(false);
    setPreview(null); setError(null); setNotice(null); setWithdrawReason("");
    setPreviewApplication("");
    setContext({ product: profile.product || "", agency: profile.agency || "",
      client_type: profile.client_type, individual_profile: profile.individual_profile });
  }
  function update(next: Editable) {
    const keys = new Set(Object.entries(next.overrides).flatMap(([section, values]) => Object.keys(values || {}).map((key) => `${section}.${key}`)));
    setForm({ ...next, locked_keys: next.locked_keys.filter((key) => keys.has(key)) }); setDirty(true); setPreview(null); setNotice(null);
  }
  function setValue(section: "policy" | "thresholds", key: string, value: string | number | boolean | undefined) {
    if (!form) return;
    const values = { ...form.overrides[section] };
    if (value === undefined) delete values[key]; else values[key] = value;
    update({ ...form, overrides: { ...form.overrides, [section]: values } });
  }
  function setAnalysis(key: keyof ConfigurationOverrides["analysis"], value: string[] | number) {
    if (form) update({ ...form, overrides: { ...form.overrides, analysis: { ...form.overrides.analysis, [key]: value } } });
  }
  const save = useMutation({ mutationFn: async () => {
    if (!form) throw new Error("Aucun formulaire");
    const payload = { code: form.code, name: form.name, product: form.product, agency: form.agency,
      client_type: form.client_type, individual_profile: form.individual_profile,
      effective_from: form.effective_from, overrides: form.overrides, locked_keys: form.locked_keys, reason: form.reason };
    return selected
      ? (await api.patch<ConfigurationProfile>(configurationUrl(`/configuration-profiles/${selected.id}/`), { ...payload, expected_updated_at: selected.updated_at })).data
      : (await api.post<ConfigurationProfile>(configurationUrl("/configuration-profiles/"), payload)).data;
  }, onSuccess: (data) => { open(data); setNotice("Brouillon enregistré. Simulez ses effets avant de le soumettre."); qc.invalidateQueries({ queryKey: ["configuration-profiles"] }); },
  onError: (err) => setError(apiErrorMessage(err, "Enregistrement impossible.")) });

  const transition = useMutation({ mutationFn: async (action: string) =>
    (await api.post<ConfigurationProfile>(configurationUrl(`/configuration-profiles/${selected?.id}/${action}/`), action === "retire" ? { reason: withdrawReason } : {})).data,
  onSuccess: (data) => { open(data); setNotice("État mis à jour.");
    for (const key of ["configuration-profiles", "credit-readiness", "credit-configuration", "credit-configuration-context", "financial-analysis", "credit-application"]) qc.invalidateQueries({ queryKey: [key] }); },
  onError: (err) => setError(apiErrorMessage(err, "Action impossible.")) });
  const simulate = useMutation({ mutationFn: async () =>
    (await api.post<ConfigurationPreview>(configurationUrl(`/configuration-profiles/${selected?.id}/preview/`), { ...context, application: previewApplication || undefined })).data,
  onSuccess: setPreview, onError: (err) => setError(apiErrorMessage(err, "Simulation impossible.")) });
  const busy = save.isPending || transition.isPending || simulate.isPending;

  function parameterLabel(section: string, key: string) {
    if (section === "simulation") return "Conventions du simulateur";
    if (section === "forms") return ({ client_fields: "Champs additionnels client", analysis_fields: "Champs additionnels analyse", analysis_sections: "Organisation des sections" } as Record<string, string>)[key] || key;
    if (section === "kyc") return ({ required_fields: "Informations KYC", required_documents: "Pièces KYC", check_expiry: "Contrôle d'expiration", validity_days: "Validité de la revue KYC" } as Record<string, string>)[key] || key;
    if (section === "references") return `Référentiel : ${key}`;
    if (section === "pricing") return key === "tariff" ? "Barème tarifaire" : "Conditions de base du produit";
    if (section === "eligibility") return "Règles d'éligibilité";
    if (section === "scoring") return "Grille de scoring et classes de risque";
    return (section === "policy" ? catalogue.data?.policy : catalogue.data?.thresholds)?.find((field) => field.key === key)?.label || ANALYSIS_LABELS[key] || key;
  }
  function displayValue(section: string, key: string, value: unknown): string {
    if (section === "simulation") return value && typeof value === "object" ? `Moteur ${(value as { engine?: string }).engine || "LEGACY"}` : "Hérité";
    if (["forms", "references"].includes(section) && Array.isArray(value)) return value.map((entry) => entry.label || `${entry.id}${entry.visible === false ? " (masqué)" : ""}`).join(", ") || "Aucun";
    if (value === undefined || value === null) return "Non défini";
    if (typeof value === "boolean") return value ? "Oui" : "Non";
    if (section === "pricing" && value && typeof value === "object") {
      if (key === "tariff") { const tariff = value as EffectiveConfiguration["pricing"]["tariff"]; return `${tariff.engine === "CONFIGURED" ? "Configuré" : "Existant"} · ${tariff.currency || "devise produit"} · ${tariff.bands.length} tranche(s) · ${tariff.charges.length} frais`; }
      return JSON.stringify(value);
    }
    if (section === "eligibility" && Array.isArray(value)) return `${value.length} condition(s)`;
    if (section === "scoring" && value && typeof value === "object") {
      const grid = value as EffectiveConfiguration["scoring"]["grid"];
      return `${grid.engine === "CUSTOM" ? "Personnalisée" : "Existante"} — ${grid.criteria.length} critère(s) — seuils : ${grid.risk_cutoffs.join(" / ")}`;
    }
    if (Array.isArray(value)) return value.map((item) => key === "required_detail_tables" ? DETAIL_TABLE_LABELS[String(item)] || String(item)
      : catalogue.data?.analysis_fields.find((field) => field.key === item)?.label || String(item)).join(", ") || "Aucun";
    const field = (section === "policy" ? catalogue.data?.policy : catalogue.data?.thresholds)?.find((item) => item.key === key);
    return field?.choices.find((choice) => choice.value === String(value))?.label || String(value);
  }

  function renderParameter(section: "policy" | "thresholds", definition: ParameterDefinition) {
    if (!form) return null;
    const explicit = Object.prototype.hasOwnProperty.call(form.overrides[section], definition.key);
    const value = form.overrides[section][definition.key] ?? definition.default;
    return <div className="field" key={definition.key}>
      <label className="checkbox-line"><input type="checkbox" checked={explicit} disabled={!editable || busy}
        onChange={(e) => setValue(section, definition.key, e.target.checked ? definition.default : undefined)} />
        <span>{definition.label}</span></label>
      {explicit ? definition.type === "boolean" ? <select value={String(value)} disabled={!editable || busy}
        onChange={(e) => setValue(section, definition.key, e.target.value === "true")}>
        <option value="true">Oui</option><option value="false">Non</option></select>
        : definition.type === "choice" ? <select value={String(value)} disabled={!editable || busy}
          onChange={(e) => setValue(section, definition.key, e.target.value)}>
          {definition.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select>
          : <input type="number" min="0" step={definition.type === "integer" ? "1" : "0.01"} value={String(value)} disabled={!editable || busy}
            onChange={(e) => setValue(section, definition.key, definition.type === "integer" ? Number(e.target.value) : e.target.value)} />
        : <span className="muted small">Valeur héritée ; visible dans l'aperçu.</span>}
      {definition.operational && <small className="muted">Règle d'organisation courante, y compris pour les dossiers déjà soumis.</small>}
    </div>;
  }

  if (needsTenant) return <div className="page-shell"><PageHeader title="Centre de configuration" /><TenantScopeNotice /></div>;
  if (catalogue.isLoading || profiles.isLoading) return <Spinner />;
  if (catalogue.isError || profiles.isError) return <ErrorState onRetry={() => { catalogue.refetch(); profiles.refetch(); }} />;

  return <div className="page-shell">
    <PageHeader icon={SlidersHorizontal} title="Centre de configuration" subtitle="Profils métier versionnés par produit et clientèle"
      actions={canCreate ? <button className="btn btn-primary" type="button" disabled={busy} onClick={() => {
        setSelected(null); setForm(empty()); setDirty(true); setPreview(null); setError(null); setNotice(null);
      }}>Nouveau profil</button> : undefined} />
    <Card title="Règles d'application">
      {user?.is_group_level && activeTenant && <label className="checkbox-line"><input type="checkbox" checked={manageGroup} onChange={(event) => setManageGroup(event.target.checked)} />Administrer le socle Groupe</label>}
      <p><strong>Périmètre : {groupMode ? "Groupe — applicable à toutes les filiales" : "Filiale sélectionnée"}.</strong></p>
      {groupMode && <p className="muted">Les références produit/agence restent locales. Sélectionnez une filiale dans la barre supérieure pour simuler le socle Groupe sur ses données. Un verrou Groupe prime sur toute adaptation filiale.</p>}
      <p>{catalogue.data?.precedence.join(" → ")}. Les profils plus spécifiques remplacent les valeurs explicitement définies.</p>
      <p className="muted">Les exigences métier sont conservées à la soumission. Les dossiers historiques déjà soumis gardent leur fonctionnement antérieur. La transmission au CBS suit l'organisation courante.</p>
      <p className="muted">La publication nécessite un autre utilisateur habilité que l'auteur et le dernier rédacteur.</p>
    </Card>
    {error && <p className="form-error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <Card title="Profils et versions">
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Profil</th><th>Version</th><th>Périmètre</th><th>État</th><th>Application</th><th /></tr></thead>
        <tbody>{profiles.data?.results.map((profile) => <tr key={profile.id}>
          <td>{profile.name}<br /><small className="muted">{profile.code}</small></td><td>{profile.version}</td>
          <td>{profile.product_label || "Tous produits"} · {CLIENTS[profile.client_type]} · {PROFILES[profile.individual_profile]}{profile.agency_label && ` · ${profile.agency_label}`}</td>
          <td>{STATUS[profile.status]}</td><td>{profile.effective_from ? new Date(profile.effective_from).toLocaleString("fr-FR") : "À la publication"}</td>
          <td><button type="button" className="btn btn-ghost" disabled={busy} onClick={() => open(profile)}>Ouvrir</button></td>
        </tr>)}</tbody></table></div>
      {!profiles.data?.count && <p className="muted">Aucun profil. La politique actuelle de la filiale s'applique.</p>}
      <PaginationBar page={page} count={profiles.data?.count || 0} onPageChange={setPage} />
    </Card>
    {form && <form className="stack" onSubmit={(e: FormEvent) => { e.preventDefault(); setError(null); save.mutate(); }}>
      <Card title={selected ? `${selected.name} — v${selected.version} — ${STATUS[selected.status]}` : "Nouveau profil"}>
        <div className="form-grid two-col">
          <label className="field"><span>Code stable</span><input required pattern="[a-zA-Z0-9_-]+" maxLength={60} value={form.code} disabled={!editable || !!selected || busy} onChange={(e) => update({ ...form, code: e.target.value })} /></label>
          <label className="field"><span>Intitulé</span><input required maxLength={180} value={form.name} disabled={!editable || busy} onChange={(e) => update({ ...form, name: e.target.value })} /></label>
          <label className="field"><span>Produit</span><select value={form.product || ""} disabled={!editable || busy || groupMode} onChange={(e) => update({ ...form, product: e.target.value || null })}>
            <option value="">Tous les produits</option>{products.data?.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label className="field"><span>Agence</span><select value={form.agency || ""} disabled={!editable || busy || groupMode} onChange={(e) => update({ ...form, agency: e.target.value || null })}>
            <option value="">Toutes les agences</option>{agencies.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label className="field"><span>Type de client</span><select value={form.client_type} disabled={!editable || busy} onChange={(e) => update({ ...form, client_type: e.target.value, individual_profile: "" })}>
            {Object.entries(CLIENTS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="field"><span>Profil particulier</span><select value={form.individual_profile} disabled={!editable || form.client_type !== "INDIVIDUAL" || busy} onChange={(e) => update({ ...form, individual_profile: e.target.value })}>
            {Object.entries(PROFILES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="field"><span>Date d'application (heure locale du navigateur)</span><input type="datetime-local" value={localDate(form.effective_from)} disabled={!editable || busy}
            onChange={(e) => update({ ...form, effective_from: e.target.value ? new Date(e.target.value).toISOString() : null })} /><small className="muted">Vide : à la publication. Une date future permet de programmer l'entrée en vigueur.</small></label>
          <label className="field"><span>Motif de modification</span><textarea required maxLength={10000} value={form.reason} disabled={!editable || busy} onChange={(e) => update({ ...form, reason: e.target.value })} /></label>
        </div>
      </Card>
      {groupMode && <Card title="Verrous Groupe"><p className="muted">Cochez les valeurs explicitement définies que les filiales ne pourront pas remplacer. Le déverrouillage nécessite une nouvelle version publiée.</p>
        {Object.entries(form.overrides).flatMap(([section, values]) => Object.keys(values || {}).map((key) => {
          const path = `${section}.${key}`;
          return <label key={path} className="checkbox-line"><input type="checkbox" checked={form.locked_keys.includes(path)} disabled={!editable || busy}
            onChange={(event) => update({ ...form, locked_keys: event.target.checked ? [...form.locked_keys, path] : form.locked_keys.filter((item) => item !== path) })} />{parameterLabel(section, key)}</label>;
        }))}
      </Card>}
      <Card title="Politique de crédit"><p className="muted">Cochez uniquement les règles à adapter ; les autres sont héritées.</p><div className="form-grid two-col">{catalogue.data?.policy.map((field) => renderParameter("policy", field))}</div></Card>
      <Card title="Seuils financiers"><div className="form-grid two-col">{catalogue.data?.thresholds.map((field) => renderParameter("thresholds", field))}</div></Card>
      <Card title="Exigences de l'analyse avant soumission">
        <p className="muted">Un champ numérique requis accepte zéro ; une vérification requise doit être confirmée. Les exigences ne bloquent pas l'enregistrement d'un brouillon.</p>
        <label className="field"><span>Mois de relevés examinés — minimum</span><input type="number" min={0} max={120} disabled={!editable || busy}
          value={form.overrides.analysis.minimum_bank_statement_months ?? ""} placeholder="Hérité" onChange={(e) => {
            if (!e.target.value) { const analysis = { ...form.overrides.analysis }; delete analysis.minimum_bank_statement_months; update({ ...form, overrides: { ...form.overrides, analysis } }); }
            else setAnalysis("minimum_bank_statement_months", Number(e.target.value));
          }} /></label>
        <details><summary>Champs et vérifications requis</summary><p className="muted">La liste remplace celle héritée lorsqu'elle est définie.</p>
          <div className="form-grid two-col">{catalogue.data?.analysis_fields.map((field) => <label key={field.key} className="checkbox-line">
            <input type="checkbox" disabled={!editable || busy} checked={form.overrides.analysis.required_fields?.includes(field.key) || false} onChange={(e) => {
              const values = new Set(form.overrides.analysis.required_fields || []); if (e.target.checked) values.add(field.key); else values.delete(field.key); setAnalysis("required_fields", [...values]);
            }} />{field.label}</label>)}</div>
          {editable && <button type="button" className="btn btn-ghost" onClick={() => { const analysis = { ...form.overrides.analysis }; delete analysis.required_fields; update({ ...form, overrides: { ...form.overrides, analysis } }); }}>Hériter de la liste des champs</button>}
        </details>
        <details><summary>Tableaux détaillés requis</summary><div className="form-grid two-col">{catalogue.data?.detail_tables.map((key) => <label className="checkbox-line" key={key}>
          <input type="checkbox" disabled={!editable || busy} checked={form.overrides.analysis.required_detail_tables?.includes(key) || false} onChange={(e) => {
            const values = new Set(form.overrides.analysis.required_detail_tables || []); if (e.target.checked) values.add(key); else values.delete(key); setAnalysis("required_detail_tables", [...values]);
          }} />{DETAIL_TABLE_LABELS[key] || key}</label>)}</div>
          {editable && <button type="button" className="btn btn-ghost" onClick={() => { const analysis = { ...form.overrides.analysis }; delete analysis.required_detail_tables; update({ ...form, overrides: { ...form.overrides, analysis } }); }}>Hériter de la liste des tableaux</button>}
        </details>
      </Card>
      {catalogue.data && <ConfigurationRulesEditor value={form.overrides} catalogue={catalogue.data}
        clientType={form.client_type || (["INDIVIDUAL", "PROFESSIONAL"].includes(products.data?.find((item) => item.id === form.product)?.client_type || "")
          ? products.data?.find((item) => item.id === form.product)?.client_type || "" : "")}
        disabled={!editable || busy} onChange={(overrides) => update({ ...form, overrides })} />}
      {catalogue.data && <ConfigurationPricingEditor value={form.overrides} catalogue={catalogue.data} disabled={!editable || busy}
        currency={products.data?.find((product) => product.id === form.product)?.currency} onChange={(overrides) => update({ ...form, overrides })} />}
      {catalogue.data && <ConfigurationFormsEditor value={form.overrides} catalogue={catalogue.data} disabled={!editable || busy} onChange={(overrides) => update({ ...form, overrides })} />}
      {catalogue.data && <ConfigurationExposureEditor value={form.overrides.exposure?.rules} defaults={catalogue.data.default_exposure} disabled={!editable || busy}
        onChange={(rules) => update({ ...form, overrides: { ...form.overrides, exposure: rules ? { rules } : {} } })} />}
      {catalogue.data && <SimulationConventionsEditor value={form.overrides.simulation?.conventions} defaults={catalogue.data.default_simulation} readonly={!editable || busy}
        onChange={(conventions) => update({ ...form, overrides: { ...form.overrides, simulation: conventions ? { conventions } : {} } })} />}
      <div className="page-actions">
        {editable && <button className="btn btn-primary" disabled={busy} type="submit">Enregistrer le brouillon</button>}
        {selected?.status === "DRAFT" && canEdit && <button type="button" className="btn btn-primary" disabled={busy || dirty} onClick={() => transition.mutate("submit")}>Soumettre à validation</button>}
        {selected?.status === "REVIEW" && canPublish && <button type="button" className="btn btn-primary" disabled={busy} onClick={() => transition.mutate("publish")}>Publier</button>}
        {selected?.status === "REVIEW" && canEdit && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => transition.mutate("reopen")}>Renvoyer en brouillon</button>}
        {selected && ["PUBLISHED", "RETIRED"].includes(selected.status) && canCreate && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => transition.mutate("revise")}>Créer une nouvelle version</button>}
      </div>
      {dirty && <p className="muted">Enregistrez les modifications avant la simulation ou la soumission.</p>}
      {selected?.status === "PUBLISHED" && canPublish && <Card title="Retrait du profil"><label className="field"><span>Motif obligatoire</span><textarea value={withdrawReason} onChange={(e) => setWithdrawReason(e.target.value)} /></label>
        <button type="button" className="btn btn-ghost" disabled={busy || !withdrawReason.trim()} onClick={() => transition.mutate("retire")}>Retirer cette version</button>
        <p className="muted">Les dossiers conservant cette version gardent leurs règles. Le retrait d'une version courante ne réactive pas une ancienne version.</p></Card>}
    </form>}
    {selected && canPreview && <Card title="Aperçu des règles applicables">
      {hasPerm(user, "credits.view_creditapplication") && <label className="field"><span>Simuler sur un dossier accessible</span>
        <select value={previewApplication} onChange={(e) => { setPreviewApplication(e.target.value); setPreview(null); }}>
          <option value="">Comparer uniquement les configurations</option>
          {applications.data?.map((item) => <option key={item.id} value={item.id}>{item.reference} — {item.client_display || "Client"}</option>)}
        </select><small className="muted">Avec un dossier, son produit et sa clientèle sont utilisés. Aucun dossier n'est modifié.</small></label>}
      {applications.isError && <p className="form-error">Impossible de charger les dossiers accessibles.</p>}
      <fieldset disabled={!!previewApplication} style={{ border: 0, padding: 0, minWidth: 0 }}>
      <div className="form-grid two-col">
        <label className="field"><span>Produit simulé</span><select value={context.product} onChange={(e) => { setContext({ ...context, product: e.target.value }); setPreview(null); }}><option value="">Sans produit</option>{products.data?.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="field"><span>Agence simulée</span><select value={context.agency} onChange={(e) => { setContext({ ...context, agency: e.target.value }); setPreview(null); }}><option value="">Sans agence</option>{agencies.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label className="field"><span>Clientèle simulée</span><select value={context.client_type} onChange={(e) => { setContext({ ...context, client_type: e.target.value, individual_profile: "" }); setPreview(null); }}>{Object.entries(CLIENTS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field"><span>Profil simulé</span><select value={context.individual_profile} disabled={context.client_type !== "INDIVIDUAL"} onChange={(e) => { setContext({ ...context, individual_profile: e.target.value }); setPreview(null); }}>{Object.entries(PROFILES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      </fieldset>
      <button type="button" className="btn btn-primary" disabled={busy || dirty} onClick={() => { setError(null); simulate.mutate(); }}>Simuler le profil enregistré</button>
      {preview && <>
        <p>{preview.matches ? "Ce profil correspond au contexte simulé." : "Ce profil ne correspond pas au contexte simulé."}</p>
        <p>{preview.impact.editable_matching} dossier(s) modifiable(s) dans le périmètre ; {preview.impact.frozen_matching} dossier(s) avec règles conservées.</p>
        <p className="muted">{preview.impact.note}</p>
        <p>Profils retenus : {preview.after.sources.map((source) => `${source.name} v${source.version}`).join(" → ") || "Politique filiale uniquement"}</p>
        {!!Object.keys(preview.after.locked_keys || {}).length && <details open><summary>Paramètres verrouillés par le Groupe</summary><ul>{Object.entries(preview.after.locked_keys || {}).map(([key, origin]) => <li key={key}>{key} — {origin}</li>)}</ul></details>}
        {!!preview.after.ignored_overrides?.length && <p className="form-error">Des adaptations filiale sont neutralisées par les verrous Groupe : {preview.after.ignored_overrides.map((item) => item.key).join(", ")}.</p>}
        <details open><summary>Conditions d'éligibilité proposées ({preview.after.eligibility.rules.length})</summary>
          <ul>{preview.after.eligibility.rules.map((rule) => <li key={rule.id}>
            {catalogue.data?.eligibility_criteria.find((field) => field.key === rule.criterion)?.label || rule.criterion} — {RULE_OPERATOR_LABELS[rule.operator]} {typeof rule.value === "boolean" ? (rule.value ? "Oui" : "Non") : Array.isArray(rule.value) ? rule.value.join(", ") : rule.value}
            {" · "}{RULE_EFFECT_LABELS[rule.effect]} · donnée manquante : {rule.missing === "FAIL" ? "condition non satisfaite" : "contrôle ignoré"}
          </li>)}</ul>
        </details>
        <details><summary>Grille proposée</summary><p>{displayValue("scoring", "grid", preview.after.scoring.grid)}</p>
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Indicateur</th><th>Poids</th><th>Note 0</th><th>Note 100</th></tr></thead><tbody>
            {preview.after.scoring.grid.criteria.map((row) => <tr key={row.metric}><td>{catalogue.data?.score_metrics.find((field) => field.key === row.metric)?.label || row.metric}</td><td>{row.weight} %</td><td>{row.bad}</td><td>{row.good}</td></tr>)}
          </tbody></table></div>
        </details>
        {preview.evaluation && <details open><summary>Résultat simulé — {preview.evaluation.reference}</summary>
          <p>Score avant : {preview.evaluation.before.score ?? "Non calculable"} ; après : {preview.evaluation.after.score ?? "Non calculable"}.</p>
          <p>Classe issue du score après simulation : {preview.evaluation.after.score_risk_level ?? "Non déterminée"}. Le risque retenu dépend également de la méthode de risque de la politique de crédit.</p>
          <p className="muted">{preview.evaluation.note}</p>
          {!!preview.evaluation.after.score_breakdown.missing_metrics?.length && <p className="form-error">Indicateurs manquants : {preview.evaluation.after.score_breakdown.missing_metrics.join(", ")}.</p>}
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Condition</th><th>Valeur du dossier</th><th>Résultat</th><th>Effet</th></tr></thead><tbody>
            {preview.evaluation.after.checks.map((check) => <tr key={check.id}><td>{check.label}</td><td>{check.actual === null ? "Manquante" : typeof check.actual === "boolean" ? (check.actual ? "Oui" : "Non") : check.actual}</td>
              <td>{check.passed === null ? "Ignoré" : check.passed ? "Satisfait" : "Non satisfait"}</td><td>{RULE_EFFECT_LABELS[check.effect]}</td></tr>)}
          </tbody></table></div>
        </details>}
        <details open><summary>Modifications ({preview.changes.length})</summary><div className="table-wrap"><table className="data-table"><thead><tr><th>Paramètre</th><th>Avant</th><th>Après</th></tr></thead><tbody>
          {preview.changes.map((change) => <tr key={`${change.section}.${change.key}`}><td>{parameterLabel(change.section, change.key)}</td><td>{displayValue(change.section, change.key, change.before)}</td><td>{displayValue(change.section, change.key, change.after)}</td></tr>)}
        </tbody></table></div></details>
        {(["policy", "thresholds"] as const).map((section) => <details key={section}><summary>{section === "policy" ? "Politique applicable et origine" : "Seuils applicables et origine"}</summary>
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Paramètre</th><th>Valeur</th><th>Origine</th></tr></thead><tbody>{catalogue.data?.[section].map((field) => <tr key={field.key}><td>{field.label}</td><td>{displayValue(section, field.key, preview.after[section][field.key])}</td><td>{preview.after.origins[section][field.key]}</td></tr>)}</tbody></table></div>
        </details>)}
        {preview.pricing_evaluation && <details open><summary>Tarification simulée sur le dossier</summary>
          <p className="muted small">Avant : taux {preview.pricing_evaluation.before.rates.interest_rate} % ; frais {preview.pricing_evaluation.before.fees.total ?? "0"} {preview.pricing_evaluation.before.currency}. Après :</p>
          <PricingQuoteSummary quote={preview.pricing_evaluation.after} />
        </details>}
      </>}
    </Card>}
  </div>;
}
