import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { allCbsReferences } from "@/api/cbs";
import type { CbsConnector, CbsProductReference } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { isFinflowAdmin } from "@/auth/routePerms";
import { Card, QueryStatus } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const EMPTY = { connector: "", kind: "CREDIT", cbs_code: "", label: "", currency: "", source_reference: "", is_active: true };

export function CbsProductsCatalog({ creditOnly = false }: { creditOnly?: boolean }) {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const admin = isFinflowAdmin(user);
  const [form, setForm] = useState({ ...EMPTY });
  const [editing, setEditing] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setForm({ ...EMPTY }); setEditing(null); setChecked([]); setError(null); }, [activeTenant]);
  const items = useQuery({ queryKey: ["cbs-product-references", activeTenant, creditOnly],
    queryFn: () => allCbsReferences<CbsProductReference>("/cbs-product-references/", creditOnly ? { kind: "CREDIT" } : {}) });
  const connectors = useQuery({ queryKey: ["cbs-product-connectors", activeTenant],
    queryFn: () => allCbsReferences<CbsConnector>("/cbs-connectors/", { is_active: true }) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["cbs-product-references"] }); qc.invalidateQueries({ queryKey: ["credit-products"] }); };
  const save = useMutation({
    mutationFn: async () => {
      const body = { ...form, kind: creditOnly ? "CREDIT" : form.kind, connector: form.connector || connectors.data?.[0]?.id || "" };
      return editing ? api.patch(`/cbs-product-references/${editing}/`, body) : api.post("/cbs-product-references/", body);
    },
    onSuccess: () => { refresh(); setForm({ ...EMPTY }); setEditing(null); setError(null); },
    onError: (e) => setError(apiErrorMessage(e, "Enregistrement de la référence impossible.")),
  });
  const confirm = useMutation({
    mutationFn: (id: string) => api.post(`/cbs-product-references/${id}/confirm/`, { document_checked: true }),
    onSuccess: () => { refresh(); setChecked([]); setError(null); },
    onError: (e) => setError(apiErrorMessage(e, "Confirmation impossible.")),
  });
  return <>
    <Card title={creditOnly ? "Produits de crédit CBS" : "Produits CBS crédit et remboursement"}>
      <p>Enregistrez les identifiants issus du CBS ou de sa documentation, puis confirmez leur correspondance après vérification du justificatif. Cette confirmation est documentaire ; elle ne constitue pas un test distant du produit.</p>
      <p>Les objets de financement, la périodicité et le mécanisme d’amortissement ont leurs propres références. Seules les références actives et confirmées sont sélectionnables dans les produits de crédit.</p>
      {admin && <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <div className="form-grid two-col">
          <label className="field"><span>Connecteur CBS *</span><select required value={form.connector || connectors.data?.[0]?.id || ""} onChange={(e) => setForm({ ...form, connector: e.target.value })}>
            <option value="">Sélectionner</option>{connectors.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></label>
          {!creditOnly && <label className="field"><span>Nature du produit *</span><select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="CREDIT">Produit crédit — idProduitCrd</option><option value="REPAYMENT">Produit remboursement — idProduitRemb</option>
          </select></label>}
          <label className="field"><span>Identifiant réel CBS *</span><input required maxLength={64} value={form.cbs_code} onChange={(e) => setForm({ ...form, cbs_code: e.target.value })} /></label>
          <label className="field"><span>Libellé *</span><input required maxLength={255} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></label>
          <label className="field"><span>Devise locale compatible (facultative)</span><input maxLength={8} placeholder="XOF" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
          <label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Référence active</label>
        </div>
        <label className="field"><span>Source ou justificatif de la correspondance *</span><textarea required maxLength={2000} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} placeholder="Référence de documentation CBS, export ou réponse du fournisseur permettant de vérifier cet identifiant" /></label>
        <p>Une modification de l’identifiant, du connecteur, de la nature, de la devise ou du justificatif nécessite une nouvelle confirmation.</p>
        <button className="btn btn-primary btn-sm" disabled={save.isPending}>{editing ? "Enregistrer la modification" : "Ajouter à confirmer"}</button>
        {editing && <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setEditing(null); setForm({ ...EMPTY }); }}>Annuler</button>}
      </form>}
      {error && <p className="form-error">{error}</p>}
    </Card>
    <QueryStatus isLoading={items.isLoading} isError={items.isError} isEmpty={!items.data?.length} emptyMessage="Aucun produit CBS documenté. Les anciens codes de démonstration ne sont pas confirmés automatiquement." onRetry={() => items.refetch()}>
      <div className="table-wrap"><table className="table"><thead><tr><th>Nature et identifiant</th><th>Libellé et source</th><th>Confirmation</th>{admin && <th>Actions</th>}</tr></thead><tbody>
        {items.data?.map((row) => <tr key={row.id}>
          <td>{row.kind === "CREDIT" ? "Crédit" : "Remboursement"}<br /><strong>{row.cbs_code}</strong><br />{row.currency || "Toutes devises"}{!row.is_active && " — inactive"}</td>
          <td>{row.label}<br /><small style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.source_reference}</small><br /><small>{connectors.data?.find((c) => c.id === row.connector)?.name || row.connector}</small></td>
          <td>{row.verification_status === "VERIFIED" ? `Confirmée sur justificatif le ${row.verified_at ? new Date(row.verified_at).toLocaleDateString("fr-FR") : "—"}` : "À confirmer"}</td>
          {admin && <td><button type="button" className="btn btn-ghost btn-sm" onClick={() => { setEditing(row.id); setForm({ connector: row.connector, kind: row.kind, cbs_code: row.cbs_code, label: row.label, currency: row.currency, source_reference: row.source_reference, is_active: row.is_active }); }}>Modifier</button>
            {row.verification_status !== "VERIFIED" && row.is_active && <>
              <label className="checkbox"><input type="checkbox" checked={checked.includes(row.id)} onChange={(e) => setChecked(e.target.checked ? [...checked, row.id] : checked.filter((id) => id !== row.id))} />Justificatif vérifié</label>
              <button type="button" className="btn btn-primary btn-sm" disabled={!checked.includes(row.id) || confirm.isPending} onClick={() => confirm.mutate(row.id)}>Confirmer</button>
            </>}
          </td>}
        </tr>)}
      </tbody></table></div>
    </QueryStatus>
  </>;
}
