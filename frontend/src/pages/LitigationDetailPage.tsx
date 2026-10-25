import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Scale } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type {
  LegalParty,
  LitigationActionType,
  LitigationCost,
  LitigationDocument,
  LitigationEventType,
  LitigationFile,
  LitigationStatus,
  Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import { PERM_COLLECTIONS, PERM_LEGAL_PARTIES_MANAGE } from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import {
  Badge,
  Card,
  ErrorState,
  PageHeader,
  Spinner,
  formatMoney,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";
import { exportLitigationPdf } from "@/utils/exportLitigationPdf";

const STATUSES: { value: LitigationStatus; label: string }[] = [
  { value: "PRE_LITIGATION", label: "Précontentieux" },
  { value: "FILED", label: "Introduite" },
  { value: "IN_PROGRESS", label: "En cours" },
  { value: "JUDGMENT", label: "Jugement rendu" },
  { value: "ENFORCEMENT", label: "Exécution" },
  { value: "APPEAL", label: "Appel / opposition" },
  { value: "SETTLED", label: "Transaction" },
  { value: "ABANDONED", label: "Abandonnée" },
  { value: "CLOSED", label: "Clôturée" },
];

const ACTIONS: { value: LitigationActionType; label: string }[] = [
  { value: "PAYMENT_ORDER", label: "Injonction de payer" },
  { value: "SUMMONS", label: "Assignation" },
  { value: "SUMMARY", label: "Référé" },
  { value: "ATTACHMENT", label: "Saisie-arrêt" },
  { value: "OHADA", label: "Procédure OHADA" },
  { value: "APPEAL", label: "Appel" },
  { value: "OTHER", label: "Autre" },
];

const EVENT_TYPES: { value: LitigationEventType; label: string }[] = [
  { value: "NOTICE", label: "Mise en demeure" },
  { value: "FILING", label: "Introduction" },
  { value: "HEARING", label: "Audience" },
  { value: "BRIEF", label: "Conclusions" },
  { value: "JUDGMENT", label: "Jugement" },
  { value: "SERVICE", label: "Signification" },
  { value: "SEIZURE", label: "Saisie" },
  { value: "APPEAL", label: "Appel" },
  { value: "SETTLEMENT", label: "Transaction" },
  { value: "OTHER", label: "Autre" },
];

const DOC_CATS = [
  { value: "LIT_ASSIGNATION", label: "Assignation" },
  { value: "LIT_CONCLUSIONS", label: "Conclusions" },
  { value: "LIT_JUDGMENT", label: "Jugement" },
  { value: "LIT_PV_HUISSIER", label: "PV huissier" },
  { value: "LIT_MISE_EN_DEMEURE", label: "Mise en demeure" },
  { value: "LIT_PIECE_ADVERSE", label: "Pièce adverse" },
  { value: "LIT_FACTURE", label: "Facture" },
  { value: "LIT_OTHER", label: "Autre" },
];

export function LitigationDetailPage() {
  const { caseId, litId } = useParams<{ caseId: string; litId: string }>();
  const { user } = useAuth();
  const canChangePerm = hasPerm(user, "collections.change_litigationfile");
  const canAddEventPerm = hasPerm(user, "collections.add_litigationevent");
  const canAddSeizurePerm = hasPerm(user, "collections.add_litigationseizure");
  const canAddCostPerm = hasPerm(user, "collections.add_litigationcost");
  const canInitiateDationPerm = hasPerm(
    user,
    "guarantees.initiate_dationrequest",
  );
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [form, setForm] = useState<Partial<LitigationFile>>({});
  const [eventType, setEventType] = useState<LitigationEventType>("HEARING");
  const [eventDate, setEventDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [eventTime, setEventTime] = useState("");
  const [eventLocation, setEventLocation] = useState("");
  const [eventComment, setEventComment] = useState("");

  const [seizureType, setSeizureType] = useState("ATTRIBUTION");
  const [seizureDate, setSeizureDate] = useState("");
  const [seizureAmount, setSeizureAmount] = useState("");
  const [seizureRef, setSeizureRef] = useState("");

  const [costType, setCostType] = useState("FEE");
  const [costAmount, setCostAmount] = useState("");
  const [costDate, setCostDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [costLabel, setCostLabel] = useState("");

  const [docName, setDocName] = useState("");
  const [docCat, setDocCat] = useState("LIT_OTHER");
  const [docFile, setDocFile] = useState<File | null>(null);

  const litQuery = useQuery({
    queryKey: ["litigation", litId],
    queryFn: async () =>
      (await api.get<LitigationFile>(`/litigations/${litId}/`)).data,
    enabled: !!litId,
  });

  const parties = useQuery({
    queryKey: ["legal-parties", "all-active"],
    queryFn: async () =>
      (
        await api.get<Paginated<LegalParty>>("/legal-parties/", {
          params: { is_active: true, page_size: 200 },
        })
      ).data.results,
  });

  const docs = useQuery({
    queryKey: ["litigation-docs", litId],
    queryFn: async () =>
      (
        await api.get<LitigationDocument[]>(`/litigations/${litId}/documents/`)
      ).data,
    enabled: !!litId,
  });

  useEffect(() => {
    if (litQuery.data) setForm(litQuery.data);
  }, [litQuery.data]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["litigation", litId] });
    qc.invalidateQueries({ queryKey: ["collection-case", caseId] });
    qc.invalidateQueries({ queryKey: ["litigation-docs", litId] });
    qc.invalidateQueries({ queryKey: ["hearings-agenda"] });
  };

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.patch(`/litigations/${litId}/`, {
          title: form.title,
          action_type: form.action_type,
          status: form.status,
          court_name: form.court_name,
          court_registry: form.court_registry,
          case_reference: form.case_reference,
          chamber: form.chamber,
          law_firm: form.law_firm || null,
          lawyer_party: form.lawyer_party || null,
          bailiff_party: form.bailiff_party || null,
          mandate_start: form.mandate_start || null,
          mandate_end: form.mandate_end || null,
          mandate_fee: form.mandate_fee || null,
          mandate_notes: form.mandate_notes,
          claimed_principal: form.claimed_principal || null,
          claimed_interest: form.claimed_interest || null,
          claimed_penalties: form.claimed_penalties || null,
          claimed_costs: form.claimed_costs || null,
          notice_date: form.notice_date || null,
          filing_date: form.filing_date || null,
          service_date: form.service_date || null,
          first_hearing_date: form.first_hearing_date || null,
          hearing_date: form.hearing_date || null,
          hearing_time: form.hearing_time || null,
          hearing_location: form.hearing_location,
          judgment_date: form.judgment_date || null,
          judgment_outcome: form.judgment_outcome || "",
          judgment_amount: form.judgment_amount || null,
          judgment_enforceable: form.judgment_enforceable || false,
          judgment_served_at: form.judgment_served_at || null,
          notes: form.notes,
          related_guarantee_ids: form.related_guarantee_ids || [],
        })
      ).data,
    onSuccess: () => {
      setMsg("Dossier contentieux enregistré.");
      setErr(null);
      invalidate();
    },
    onError: (err) => setErr(apiErrorMessage(err, "Enregistrement impossible.")),
  });

  const addEvent = useMutation({
    mutationFn: async () =>
      api.post(`/litigations/${litId}/events/`, {
        event_type: eventType,
        event_date: eventDate,
        event_time: eventTime || null,
        location: eventLocation,
        comment: eventComment,
      }),
    onSuccess: () => {
      setEventComment("");
      setMsg("Événement ajouté.");
      invalidate();
    },
    onError: (err) => setErr(apiErrorMessage(err, "Événement non enregistré.")),
  });

  const addSeizure = useMutation({
    mutationFn: async () =>
      api.post(`/litigations/${litId}/seizures/`, {
        seizure_type: seizureType,
        seizure_date: seizureDate || null,
        amount: seizureAmount || null,
        report_reference: seizureRef,
        status: "PLANNED",
      }),
    onSuccess: () => {
      setSeizureAmount("");
      setSeizureRef("");
      setMsg("Saisie enregistrée.");
      invalidate();
    },
    onError: (err) => setErr(apiErrorMessage(err, "Saisie non enregistrée.")),
  });

  const addCost = useMutation({
    mutationFn: async () =>
      api.post(`/litigations/${litId}/costs/`, {
        cost_type: costType,
        amount: costAmount,
        cost_date: costDate,
        label: costLabel,
        is_paid: false,
        recoverable: true,
      }),
    onSuccess: () => {
      setCostAmount("");
      setCostLabel("");
      setMsg("Frais enregistrés.");
      invalidate();
    },
    onError: (err) => setErr(apiErrorMessage(err, "Frais non enregistrés.")),
  });

  const uploadDoc = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (docFile) fd.append("file", docFile);
      fd.append("name", docName || docFile?.name || "Document");
      fd.append("category", docCat);
      return api.post(`/litigations/${litId}/documents/`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    },
    onSuccess: () => {
      setDocFile(null);
      setDocName("");
      setMsg("Pièce déposée.");
      invalidate();
    },
    onError: (err) => setErr(apiErrorMessage(err, "Dépôt de pièce impossible.")),
  });

  if (litQuery.isLoading) return <Spinner />;
  if (litQuery.isError || !litQuery.data) {
    return (
      <ErrorState
        message="Impossible de charger le contentieux."
        onRetry={() => litQuery.refetch()}
      />
    );
  }
  const lit = litQuery.data;
  const canWrite = Boolean(lit.can_operate);
  const canChange = canChangePerm && canWrite;
  const canAddEvent = canAddEventPerm && canWrite;
  const canAddSeizure = canAddSeizurePerm && canWrite;
  const canAddCost = canAddCostPerm && canWrite;
  const canInitiateDation = canInitiateDationPerm && canWrite;
  const firms = (parties.data || []).filter((p) => p.party_type === "LAW_FIRM");
  const lawyers = (parties.data || []).filter(
    (p) => p.party_type === "LAWYER" || p.party_type === "LAW_FIRM",
  );
  const bailiffs = (parties.data || []).filter((p) => p.party_type === "BAILIFF");
  const costsTotal = (lit.costs || []).reduce(
    (s: number, c: LitigationCost) => s + Number(c.amount || 0),
    0,
  );

  function set<K extends keyof LitigationFile>(key: K, value: LitigationFile[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={Scale}
        title={lit.title || lit.case_reference || "Contentieux"}
        subtitle={`${lit.court_name || "Juridiction n/c"} · ${lit.status_display}`}
        actions={
          <>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => exportLitigationPdf(lit)}
            >
              <Download size={14} /> PDF
            </button>
            <PermLink
              user={user}
              anyOf={PERM_COLLECTIONS}
              to={`/recouvrement/${caseId}`}
              className="btn btn-ghost btn-sm"
              fallback={null}
            >
              <ArrowLeft size={14} /> Retour dossier
            </PermLink>
          </>
        }
      />

      {msg && <div className="form-success" style={{ marginBottom: 12 }}>{msg}</div>}
      {err && <div className="form-error" style={{ marginBottom: 12 }}>{err}</div>}
      {!canWrite && (
        <p className="muted" style={{ marginBottom: 12 }}>
          Consultation : les modifications contentieuses sont réservées au
          responsable de cette tranche. Utilisez le dialogue du dossier.
        </p>
      )}

      <Card title="Procédure">
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="form-grid">
            <label className="field">
              <span>Intitulé</span>
              <input
                value={form.title || ""}
                onChange={(e) => set("title", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Nature</span>
              <select
                value={form.action_type || "SUMMONS"}
                onChange={(e) =>
                  set("action_type", e.target.value as LitigationActionType)
                }
              >
                {ACTIONS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Statut</span>
              <select
                value={form.status || "PRE_LITIGATION"}
                onChange={(e) =>
                  set("status", e.target.value as LitigationStatus)
                }
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Juridiction</span>
              <input
                value={form.court_name || ""}
                onChange={(e) => set("court_name", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Greffe</span>
              <input
                value={form.court_registry || ""}
                onChange={(e) => set("court_registry", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Réf. RG / rôle</span>
              <input
                value={form.case_reference || ""}
                onChange={(e) => set("case_reference", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Chambre</span>
              <input
                value={form.chamber || ""}
                onChange={(e) => set("chamber", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Cabinet</span>
              <select
                value={form.law_firm || ""}
                onChange={(e) => set("law_firm", e.target.value || null)}
              >
                <option value="">—</option>
                {firms.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Avocat</span>
              <select
                value={form.lawyer_party || ""}
                onChange={(e) => set("lawyer_party", e.target.value || null)}
              >
                <option value="">—</option>
                {lawyers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Huissier</span>
              <select
                value={form.bailiff_party || ""}
                onChange={(e) => set("bailiff_party", e.target.value || null)}
              >
                <option value="">—</option>
                {bailiffs.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Début mandat</span>
              <input
                type="date"
                value={form.mandate_start || ""}
                onChange={(e) => set("mandate_start", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Fin mandat</span>
              <input
                type="date"
                value={form.mandate_end || ""}
                onChange={(e) => set("mandate_end", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Honoraires forfait</span>
              <input
                type="number"
                value={form.mandate_fee || ""}
                onChange={(e) => set("mandate_fee", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Capital réclamé</span>
              <input
                type="number"
                value={form.claimed_principal || ""}
                onChange={(e) => set("claimed_principal", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Intérêts</span>
              <input
                type="number"
                value={form.claimed_interest || ""}
                onChange={(e) => set("claimed_interest", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Pénalités</span>
              <input
                type="number"
                value={form.claimed_penalties || ""}
                onChange={(e) => set("claimed_penalties", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Frais réclamés</span>
              <input
                type="number"
                value={form.claimed_costs || ""}
                onChange={(e) => set("claimed_costs", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Mise en demeure</span>
              <input
                type="date"
                value={form.notice_date || ""}
                onChange={(e) => set("notice_date", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Introduction</span>
              <input
                type="date"
                value={form.filing_date || ""}
                onChange={(e) => set("filing_date", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Signification</span>
              <input
                type="date"
                value={form.service_date || ""}
                onChange={(e) => set("service_date", e.target.value)}
              />
            </label>
            <label className="field">
              <span>1ʳᵉ audience</span>
              <input
                type="date"
                value={form.first_hearing_date || ""}
                onChange={(e) => set("first_hearing_date", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Prochaine audience</span>
              <input
                type="date"
                value={form.hearing_date || ""}
                onChange={(e) => set("hearing_date", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Heure</span>
              <input
                type="time"
                value={(form.hearing_time || "").slice(0, 5)}
                onChange={(e) => set("hearing_time", e.target.value || null)}
              />
            </label>
            <label className="field">
              <span>Lieu audience</span>
              <input
                value={form.hearing_location || ""}
                onChange={(e) => set("hearing_location", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Date jugement</span>
              <input
                type="date"
                value={form.judgment_date || ""}
                onChange={(e) => set("judgment_date", e.target.value)}
              />
            </label>
            <label className="field">
              <span>Sens jugement</span>
              <select
                value={form.judgment_outcome || ""}
                onChange={(e) => set("judgment_outcome", e.target.value)}
              >
                <option value="">—</option>
                <option value="FAVORABLE">Favorable</option>
                <option value="PARTIAL">Partiel</option>
                <option value="UNFAVORABLE">Défavorable</option>
                <option value="SETTLEMENT">Transaction</option>
                <option value="PENDING">En attente</option>
              </select>
            </label>
            <label className="field">
              <span>Montant accordé</span>
              <input
                type="number"
                value={form.judgment_amount || ""}
                onChange={(e) => set("judgment_amount", e.target.value)}
              />
            </label>
            <label className="field checkbox-field">
              <input
                type="checkbox"
                checked={!!form.judgment_enforceable}
                onChange={(e) => set("judgment_enforceable", e.target.checked)}
              />
              <span>Exécutoire</span>
            </label>
          </div>
          <label className="field">
            <span>Notes</span>
            <textarea
              rows={2}
              value={form.notes || ""}
              onChange={(e) => set("notes", e.target.value)}
            />
          </label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {canChange && (
              <button className="btn btn-primary" disabled={save.isPending}>
                Enregistrer
              </button>
            )}
            {hasAnyPerm(user, PERM_LEGAL_PARTIES_MANAGE) && (
              <Link
                className="btn btn-ghost btn-sm"
                to="/admin/intervenants-juridiques"
              >
                Gérer les cabinets
              </Link>
            )}
            {caseId && (
              <>
                {canInitiateDation && (
                  <Link
                    className="btn btn-ghost btn-sm"
                    to={
                      lit.application_id
                        ? `/dations/nouvelle?application=${lit.application_id}${
                            lit.client_id ? `&client=${lit.client_id}` : ""
                          }`
                        : "/dations/nouvelle"
                    }
                  >
                    Proposer dation
                  </Link>
                )}
                <PermLink
                  user={user}
                  anyOf={PERM_COLLECTIONS}
                  to={`/recouvrement/${caseId}`}
                  className="btn btn-ghost btn-sm"
                  fallback={null}
                >
                  Passage en perte (fiche)
                </PermLink>
              </>
            )}
          </div>
        </form>
      </Card>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        <Card title="Agenda & événements">
          {canAddEvent && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              addEvent.mutate();
            }}
            style={{ marginBottom: 12 }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Type</span>
                <select
                  value={eventType}
                  onChange={(e) =>
                    setEventType(e.target.value as LitigationEventType)
                  }
                >
                  {EVENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={eventDate}
                  onChange={(e) => setEventDate(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Heure</span>
                <input
                  type="time"
                  value={eventTime}
                  onChange={(e) => setEventTime(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Lieu</span>
                <input
                  value={eventLocation}
                  onChange={(e) => setEventLocation(e.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span>Commentaire</span>
              <input
                value={eventComment}
                onChange={(e) => setEventComment(e.target.value)}
              />
            </label>
            <button className="btn btn-primary btn-sm" disabled={addEvent.isPending}>
              Ajouter
            </button>
          </form>
          )}
          <ul className="timeline-list">
            {(lit.events || []).map((ev) => (
              <li key={ev.id}>
                <strong>
                  {ev.event_type_display} — {ev.event_date}
                  {ev.event_time ? ` ${String(ev.event_time).slice(0, 5)}` : ""}
                </strong>
                {ev.location && (
                  <span className="muted small"> · {ev.location}</span>
                )}
                {ev.comment && <p className="muted small">{ev.comment}</p>}
              </li>
            ))}
          </ul>
        </Card>

        <Card title={`Frais (total ${formatMoney(String(costsTotal))})`}>
          {canAddCost && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              addCost.mutate();
            }}
            style={{ marginBottom: 12 }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Type</span>
                <select
                  value={costType}
                  onChange={(e) => setCostType(e.target.value)}
                >
                  <option value="RETAINER">Provision</option>
                  <option value="FEE">Honoraire</option>
                  <option value="REGISTRY">Greffe</option>
                  <option value="BAILIFF">Huissier</option>
                  <option value="TRAVEL">Déplacement</option>
                  <option value="OTHER">Autre</option>
                </select>
              </label>
              <label className="field">
                <span>Montant</span>
                <input
                  type="number"
                  value={costAmount}
                  onChange={(e) => setCostAmount(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={costDate}
                  onChange={(e) => setCostDate(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Libellé</span>
                <input
                  value={costLabel}
                  onChange={(e) => setCostLabel(e.target.value)}
                />
              </label>
            </div>
            <button className="btn btn-primary btn-sm" disabled={addCost.isPending}>
              Ajouter
            </button>
          </form>
          )}
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th className="num">Montant</th>
                <th>Payé</th>
              </tr>
            </thead>
            <tbody>
              {(lit.costs || []).map((c) => (
                <tr key={c.id}>
                  <td>{c.cost_date}</td>
                  <td>{c.cost_type_display}</td>
                  <td className="num">{formatMoney(c.amount)}</td>
                  <td>{c.is_paid ? "Oui" : "Non"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        <Card title="Saisies / exécution">
          {canAddSeizure && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              addSeizure.mutate();
            }}
            style={{ marginBottom: 12 }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Type</span>
                <select
                  value={seizureType}
                  onChange={(e) => setSeizureType(e.target.value)}
                >
                  <option value="ATTRIBUTION">Saisie-attribution</option>
                  <option value="MOVABLE">Mobilière</option>
                  <option value="IMMOVABLE">Immobilière</option>
                  <option value="SALE">Vente forcée</option>
                  <option value="WAGE">Sur salaire</option>
                  <option value="OTHER">Autre</option>
                </select>
              </label>
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={seizureDate}
                  onChange={(e) => setSeizureDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Montant</span>
                <input
                  type="number"
                  value={seizureAmount}
                  onChange={(e) => setSeizureAmount(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Réf. PV</span>
                <input
                  value={seizureRef}
                  onChange={(e) => setSeizureRef(e.target.value)}
                />
              </label>
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={addSeizure.isPending}
            >
              Ajouter la saisie
            </button>
          </form>
          )}
          <ul className="timeline-list">
            {(lit.seizures || []).map((s) => (
              <li key={s.id}>
                <strong>
                  {s.seizure_type_display} — {s.seizure_date || "—"}
                </strong>
                <Badge value={s.status_display} />
                {s.amount && (
                  <span className="muted small">
                    {" "}
                    · {formatMoney(s.amount)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Pièces (GED)">
          {canChange && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!docFile) {
                setErr("Choisissez un fichier.");
                return;
              }
              uploadDoc.mutate();
            }}
            style={{ marginBottom: 12 }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Catégorie</span>
                <select
                  value={docCat}
                  onChange={(e) => setDocCat(e.target.value)}
                >
                  {DOC_CATS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Nom</span>
                <input
                  value={docName}
                  onChange={(e) => setDocName(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Fichier</span>
                <input
                  type="file"
                  onChange={(e) => setDocFile(e.target.files?.[0] || null)}
                  required
                />
              </label>
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={uploadDoc.isPending}
            >
              Déposer
            </button>
          </form>
          )}
          <ul className="timeline-list">
            {(docs.data || []).map((d) => (
              <li key={d.id}>
                {d.file ? (
                  <a href={d.file} target="_blank" rel="noreferrer">
                    {d.name}
                  </a>
                ) : (
                  d.name
                )}
              </li>
            ))}
            {!docs.data?.length && (
              <li className="muted small">Aucune pièce.</li>
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}
