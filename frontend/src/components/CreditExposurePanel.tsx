import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "@/api/client";
import type { BorrowerGroup, ExposureAssessment, ExposureObservation } from "@/api/exposure";
import type { Client, GedDocument, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { formatMoney } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

export function CreditExposurePanel({ applicationId, clientId, currency }: { applicationId: string; clientId: string; currency: string }) {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const canView = hasPerm(user, "credits.view_creditexposureobservation");
  const canWrite = hasPerm(user, "credits.add_creditexposureobservation");
  const canVerify = hasPerm(user, "credits.verify_creditexposureobservation");
  const canGroup = hasPerm(user, "credits.view_borrowergroup");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({ as_of: "", drawn_principal: "", undrawn_commitments: "0", guarantees_given: "0", source_reference: "", evidence: "", completeness_confirmed: false, note: "", currency });
  const [search, setSearch] = useState("");
  const [groupForm, setGroupForm] = useState({ code: "", name: "", reason: "", clients: [clientId] });
  const [groupId, setGroupId] = useState<string | null>(null);
  const [revocationReason, setRevocationReason] = useState("");
  const [revoking, setRevoking] = useState<string | null>(null);
  const [showObservationForm, setShowObservationForm] = useState(false);
  const [showGroupForm, setShowGroupForm] = useState(false);
  const [selectedNames, setSelectedNames] = useState<Record<string, string>>({});
  const emptyObservation = () => ({ as_of: "", drawn_principal: "", undrawn_commitments: "0", guarantees_given: "0", source_reference: "", evidence: "", completeness_confirmed: false, note: "", currency });
  const closeObservation = () => { setShowObservationForm(false); setEditing(null); setForm(emptyObservation()); setError(""); };
  const closeGroup = () => { setShowGroupForm(false); setGroupId(null); setSearch(""); setSelectedNames({}); setGroupForm({ code: "", name: "", reason: "", clients: [clientId] }); setError(""); };
  const summary = useQuery({ queryKey: ["exposure", applicationId, activeTenant], queryFn: async () => (await api.get<ExposureAssessment>(`/credit-applications/${applicationId}/exposure/`)).data, enabled: canView });
  const observations = useQuery({ queryKey: ["exposure-observations", clientId, activeTenant], queryFn: async () => (await api.get<Paginated<ExposureObservation>>("/credit-exposure-observations/", { params: { client: clientId, page_size: 100 } })).data, enabled: canView });
  const documents = useQuery({ queryKey: ["exposure-documents", clientId, applicationId, activeTenant], queryFn: async () => {
    const results = await Promise.all([clientId, applicationId].map(async (id) => (await api.get<Paginated<GedDocument>>("/documents/", { params: { object_id: id, page_size: 100 } })).data.results));
    return results.flat().filter((document) => !!document.file && document.verification_status === "VERIFIED");
  }, enabled: canView && showObservationForm && hasPerm(user, "documents.view_document") });
  const groups = useQuery({ queryKey: ["borrower-groups", clientId, activeTenant], queryFn: async () => (await api.get<Paginated<BorrowerGroup>>("/borrower-groups/", { params: { clients: clientId, page_size: 100 } })).data, enabled: canView && canGroup });
  const clients = useQuery({ queryKey: ["borrower-clients", search.trim(), activeTenant], queryFn: async () => (await api.get<Paginated<Client>>("/clients/", { params: { search: search.trim(), page_size: 20 } })).data, enabled: canView && canGroup && showGroupForm && search.trim().length >= 2 && hasPerm(user, "clients.view_client") });
  const refresh = () => {
    ["exposure", "exposure-observations", "borrower-groups", "credit-readiness", "setup-review", "credit-governance"].forEach((key) => qc.invalidateQueries({ queryKey: [key] }));
    setError("");
  };
  const save = useMutation({ mutationFn: async () => editing
    ? api.patch(`/credit-exposure-observations/${editing}/`, { ...form, client: clientId })
    : api.post("/credit-exposure-observations/", { ...form, client: clientId }),
    onSuccess: () => { refresh(); closeObservation(); }, onError: (e) => setError(apiErrorMessage(e, "Enregistrement impossible.")) });
  const transition = useMutation({ mutationFn: ({ id, action }: { id: string; action: "verify" | "revoke" }) => api.post(`/credit-exposure-observations/${id}/${action}/`, action === "revoke" ? { reason: revocationReason } : {}), onSuccess: () => { refresh(); setRevoking(null); setRevocationReason(""); }, onError: (e) => setError(apiErrorMessage(e, "Transition impossible.")) });
  const saveGroup = useMutation({ mutationFn: () => groupId ? api.patch(`/borrower-groups/${groupId}/`, groupForm) : api.post("/borrower-groups/", groupForm), onSuccess: () => { refresh(); closeGroup(); }, onError: (e) => setError(apiErrorMessage(e, "Enregistrement du groupe impossible.")) });
  const deactivate = useMutation({ mutationFn: (group: BorrowerGroup) => api.patch(`/borrower-groups/${group.id}/`, { is_active: !group.is_active }), onSuccess: refresh, onError: (e) => setError(apiErrorMessage(e, "Changement du groupe impossible.")) });
  if (!canView) return null;
  const set = (key: keyof typeof form, value: string | boolean) => setForm({ ...form, [key]: value });
  return <div className="stack">
    {summary.isError && <p className="form-error">Impossible de charger les engagements.</p>}
    {summary.isLoading && <p className="muted">Chargement des engagements…</p>}
    {summary.data && <><div className="form-grid two-col">
      <p>Engagement global du client : <strong>{summary.data.client_total === null ? "Non déterminé" : formatMoney(summary.data.client_total, summary.data.currency)}</strong></p>
      <p>Engagement du groupe économique : <strong>{!summary.data.has_linked_group ? "Aucun groupe déclaré" : summary.data.restricted ? "Accès restreint" : summary.data.group_total === null ? "Non déterminé" : formatMoney(summary.data.group_total, summary.data.currency)}</strong></p>
    </div><p className="muted small">Contrôle {summary.data.enabled ? `actif — ${summary.data.gate === "ALERT" ? "alerte" : `blocage à partir de ${summary.data.gate === "SUBMIT" ? "la soumission" : summary.data.gate === "APPROVE" ? "l'accord" : "la mise en place"}`}` : "désactivé"}. Situation {summary.data.complete ? "complète" : "à compléter"}.</p>
      {summary.data.failures.length > 0 && <ul>{summary.data.failures.map((failure) => <li key={failure}>{failure}</li>)}</ul>}
      {summary.data.members.filter((row) => row.client === clientId).map((row) => <div key={row.client}>
        <dl className="def-list two">
          <div><dt>Engagements existants justifiés</dt><dd>{row.external_total === null ? "Situation vérifiée manquante" : formatMoney(row.external_total, summary.data!.currency)}</dd></div>
          <div><dt>Autres demandes en cours retenues</dt><dd>{formatMoney(row.other_pending_total, summary.data!.currency)}</dd></div>
          <div><dt>Présent dossier ajouté aux engagements</dt><dd>{row.current_application_amount === null ? "Non ajouté comme nouvelle demande" : formatMoney(row.current_application_amount, summary.data!.currency)}</dd></div>
          <div><dt>Date et source de la situation</dt><dd>{row.as_of ? `${row.as_of} — ${row.source_reference}` : "Aucune source vérifiée"}</dd></div>
        </dl>
        {row.issues.map((issue) => <p className="muted small" key={issue}>{issue}</p>)}
      </div>)}
      <p className="muted small">Une situation manquante ne signifie pas une absence de dettes. Un dossier déjà mis en place doit être couvert par les engagements existants justifiés.</p>
    </>}
    <h3>Situations externes du client</h3>
    {canWrite && !showObservationForm && <div><button type="button" className="btn btn-ghost btn-sm" onClick={() => { setEditing(null); setForm(emptyObservation()); setShowObservationForm(true); setError(""); }}>Ajouter une situation</button></div>}
    {observations.isError && <p className="form-error">Impossible de charger les situations documentées.</p>}
    {observations.isLoading && <p className="muted">Chargement des situations…</p>}
    {observations.data?.results.length === 0 && <p className="muted small">Aucune situation d'engagements enregistrée pour ce client.</p>}
    {!!observations.data?.results.length && <div className="table-scroll"><table className="table"><thead><tr><th>Date / source</th><th>Capital tiré</th><th>Non tiré / cautions données</th><th>État</th><th>Actions</th></tr></thead><tbody>
      {observations.data?.results.map((row) => <tr key={row.id}><td>{row.as_of}<br />{row.source_reference}</td><td>{formatMoney(row.drawn_principal, row.currency)}</td><td>{formatMoney(Number(row.undrawn_commitments) + Number(row.guarantees_given), row.currency)}</td><td>{row.status === "VERIFIED" ? "Vérifiée" : row.status === "REVOKED" ? "Révoquée" : "Brouillon"}</td><td>
        {row.status === "DRAFT" && hasPerm(user, "credits.change_creditexposureobservation") && <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setEditing(row.id); setShowObservationForm(true); setError(""); setForm({ as_of: row.as_of, currency: row.currency, drawn_principal: row.drawn_principal, undrawn_commitments: row.undrawn_commitments, guarantees_given: row.guarantees_given, evidence: row.evidence, source_reference: row.source_reference, completeness_confirmed: row.completeness_confirmed, note: row.note }); }}>Modifier</button>}
        {row.status === "DRAFT" && canVerify && row.created_by !== user?.id && row.updated_by !== user?.id && <button type="button" className="btn btn-ghost btn-sm" disabled={transition.isPending} onClick={() => transition.mutate({ id: row.id, action: "verify" })}>Vérifier</button>}
        {row.status === "VERIFIED" && canVerify && <button type="button" className="btn btn-ghost btn-sm" disabled={transition.isPending} onClick={() => { setRevoking(row.id); setRevocationReason(""); setError(""); }}>Révoquer</button>}
      </td></tr>)}
    </tbody></table></div>}
    {canVerify && revoking && <form className="stack" onSubmit={(e) => { e.preventDefault(); transition.mutate({ id: revoking, action: "revoke" }); }}><label className="field"><span>Motif de révocation de la situation sélectionnée</span><input required value={revocationReason} onChange={(e) => setRevocationReason(e.target.value)} /></label><div className="doc-row"><button className="btn btn-primary" disabled={transition.isPending || !revocationReason.trim()}>Confirmer la révocation</button><button type="button" className="btn btn-ghost" disabled={transition.isPending} onClick={() => { setRevoking(null); setRevocationReason(""); }}>Annuler</button></div></form>}
    {showObservationForm && (editing ? hasPerm(user, "credits.change_creditexposureobservation") : canWrite) && <form className="stack" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}><h3>{editing ? "Modifier le brouillon" : "Nouvelle situation justifiée"}</h3><div className="form-grid two-col">
      <label className="field"><span>Date de situation</span><input required type="date" value={form.as_of} onChange={(e) => set("as_of", e.target.value)} /></label>
      <label className="field"><span>Devise</span><input required maxLength={3} value={form.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></label>
      {([['drawn_principal', 'Capital restant dû tiré'], ['undrawn_commitments', 'Engagements accordés non tirés'], ['guarantees_given', 'Cautions et garanties données']] as const).map(([key, label]) => <label className="field" key={key}><span>{label}</span><input required type="number" min="0" step="0.01" value={form[key]} onChange={(e) => set(key, e.target.value)} /></label>)}
      <label className="field"><span>Source et référence</span><input required maxLength={180} value={form.source_reference} onChange={(e) => set("source_reference", e.target.value)} /></label>
      <label className="field"><span>Justificatif GED vérifié</span><select required value={form.evidence} onChange={(e) => set("evidence", e.target.value)}><option value="">Sélectionner une pièce du client ou du dossier</option>{documents.data?.map((doc) => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></label>
      <label className="field"><span>Commentaire et rapprochements</span><textarea value={form.note} onChange={(e) => set("note", e.target.value)} /></label>
    </div><p className="muted small">Importez et faites vérifier le justificatif dans la GED du client ou du dossier avant de le sélectionner. Les engagements externes doivent couvrir l'ensemble des établissements, y compris le CBS, et ne pas inclure les nouvelles demandes FIN_FLOW encore en circuit.</p><label className="field"><span><input type="checkbox" checked={form.completeness_confirmed} onChange={(e) => set("completeness_confirmed", e.target.checked)} /> Je confirme l'exhaustivité de la situation externe à cette date</span></label>
      {documents.isError && <p className="form-error">Impossible de charger les justificatifs GED.</p>}
      <div className="doc-row"><button className="btn btn-primary" disabled={save.isPending}>{save.isPending ? "Enregistrement…" : "Enregistrer le brouillon"}</button><button type="button" className="btn btn-ghost" disabled={save.isPending} onClick={closeObservation}>Annuler</button></div>
    </form>}
    {canGroup && <><h3>Relations économiques déclarées</h3>
      {groups.isError && <p className="form-error">Impossible de charger les relations économiques.</p>}
      {groups.isLoading && <p className="muted">Chargement des relations économiques…</p>}
      {groups.data?.results.length === 0 && <p className="muted small">Aucun groupe économique déclaré pour ce client.</p>}
      {!showGroupForm && hasPerm(user, "credits.add_borrowergroup") && <div><button type="button" className="btn btn-ghost btn-sm" onClick={() => { closeGroup(); setShowGroupForm(true); }}>Déclarer une relation économique</button></div>}
      {groups.data?.results.map((group) => <div key={group.id}><strong>{group.name}</strong> — {group.is_active ? "Actif" : "Inactif"}<p className="muted small">{group.reason} — {group.clients_detail.map((member) => member.name).join(", ")}</p>{hasPerm(user, "credits.change_borrowergroup") && <><button type="button" className="btn btn-ghost btn-sm" onClick={() => { setGroupId(group.id); setShowGroupForm(true); setSearch(""); setSelectedNames(Object.fromEntries(group.clients_detail.map((member) => [member.id, member.name]))); setGroupForm({ code: group.code, name: group.name, reason: group.reason, clients: group.clients }); }}>Modifier la relation</button><button type="button" className="btn btn-ghost btn-sm" disabled={deactivate.isPending} onClick={() => deactivate.mutate(group)}>{group.is_active ? "Désactiver" : "Réactiver"}</button></>}</div>)}
      {showGroupForm && hasPerm(user, groupId ? "credits.change_borrowergroup" : "credits.add_borrowergroup") && <form className="stack" onSubmit={(e) => { e.preventDefault(); saveGroup.mutate(); }}><h3>{groupId ? "Modifier la relation économique" : "Déclarer une relation économique"}</h3><div className="form-grid two-col">
        <label className="field"><span>Code du groupe</span><input required maxLength={60} value={groupForm.code} onChange={(e) => setGroupForm({ ...groupForm, code: e.target.value })} /></label><label className="field"><span>Nom</span><input required maxLength={180} value={groupForm.name} onChange={(e) => setGroupForm({ ...groupForm, name: e.target.value })} /></label>
        <label className="field"><span>Justification du lien</span><textarea required value={groupForm.reason} onChange={(e) => setGroupForm({ ...groupForm, reason: e.target.value })} /></label><label className="field"><span>Rechercher les autres clients à rattacher</span><input value={search} onChange={(e) => setSearch(e.target.value)} /></label>
      </div><p className="muted small">Le client de ce dossier reste rattaché. Sélectionnez au moins un autre client accessible ; les relations hors périmètre doivent être gérées par un utilisateur habilité.</p>
        {groupForm.clients.filter((id) => id !== clientId).map((id) => <label className="field" key={id}><span><input type="checkbox" checked onChange={() => setGroupForm({ ...groupForm, clients: groupForm.clients.filter((member) => member !== id) })} /> {selectedNames[id] || id} — sélectionné</span></label>)}
        {search.trim().length < 2 ? <p className="muted small">Saisissez au moins deux caractères pour rechercher un client à rattacher. Les résultats proposés ne constituent pas des liens déjà déclarés.</p> : <>
          {clients.isFetching && <p className="muted small">Recherche…</p>}
          {clients.isError && <p className="form-error">Recherche de clients indisponible.</p>}
          {clients.data?.results.filter((client) => client.id !== clientId && !groupForm.clients.includes(client.id)).map((client) => <label className="field" key={client.id}><span><input type="checkbox" checked={false} onChange={() => { setSelectedNames({ ...selectedNames, [client.id]: client.display_name }); setGroupForm({ ...groupForm, clients: [...groupForm.clients, client.id] }); }} /> {client.display_name} — {client.reference}</span></label>)}
          {clients.data && clients.data.results.filter((client) => client.id !== clientId && !groupForm.clients.includes(client.id)).length === 0 && <p className="muted small">Aucun autre client à proposer pour cette recherche.</p>}
          {clients.data?.next && <p className="muted small">Affinez la recherche pour accéder aux autres résultats.</p>}
        </>}
        <div className="doc-row"><button className="btn btn-primary" disabled={saveGroup.isPending || groupForm.clients.length < 2}>{groupId ? "Enregistrer la relation" : "Créer le groupe lié"}</button><button type="button" className="btn btn-ghost" disabled={saveGroup.isPending} onClick={closeGroup}>Annuler</button></div>
      </form>}</>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </div>;
}
