import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleDollarSign, Download, Mail, MessageSquare } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type {
  AdminUser,
  CollectionActionType,
  CollectionCase,
  CollectionDialogueKind,
  CollectionDialogueMessage,
  CollectionStage,
  Paginated,
  PromiseStatus,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { isSmsEnabled } from "@/auth/features";
import { hasAnyPerm, hasPerm } from "@/auth/permissions";
import {
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_GUARANTEES,
  PERM_LEGAL_PARTIES_MANAGE,
  PERM_LITIGATION,
  PERM_SURETIES,
} from "@/auth/routePerms";
import { PermLink } from "@/components/PermLink";
import { SuretyEngagementActions } from "@/components/SuretyEngagementActions";
import {
  RestructureRequestPanel,
  WriteOffRequestPanel,
} from "@/components/FinancialDecisionPanels";
import {
  Badge,
  Card,
  ErrorState,
  Spinner,
  formatMoney,
} from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";
import { exportCollectionCasePdf } from "@/utils/exportCollectionCasePdf";

const ACTION_TYPES: { value: CollectionActionType; label: string }[] = [
  { value: "CALL", label: "Appel" },
  { value: "SMS", label: "SMS" },
  { value: "EMAIL", label: "Courriel" },
  { value: "LETTER", label: "Courrier" },
  { value: "VISIT", label: "Visite" },
  { value: "LEGAL", label: "Acte judiciaire" },
  { value: "DATION", label: "Dation en paiement" },
];

const DIALOGUE_KINDS: { value: CollectionDialogueKind; label: string }[] = [
  { value: "QUESTION", label: "Question" },
  { value: "REQUEST", label: "Demande d'action" },
  { value: "RECOMMENDATION", label: "Recommandation" },
  { value: "REPLY", label: "Réponse" },
];

function DialogueComposer({
  messages,
  kind,
  body,
  onKind,
  onBody,
  onSubmit,
  pending,
  emptyLabel,
}: {
  messages: CollectionDialogueMessage[];
  kind: CollectionDialogueKind;
  body: string;
  onKind: (kind: CollectionDialogueKind) => void;
  onBody: (body: string) => void;
  onSubmit: () => void;
  pending: boolean;
  emptyLabel: string;
}) {
  return (
    <div className="action-dialogue">
      {!messages.length ? (
        <p className="muted small">{emptyLabel}</p>
      ) : (
        <ul className="timeline-list">
          {messages.map((m) => (
            <li key={m.id}>
              <strong>{m.kind_display}</strong>
              <span className="muted small">
                {" "}
                — {new Date(m.created_at).toLocaleString("fr-FR")}
                {m.created_by_name ? ` · ${m.created_by_name}` : ""}
              </span>
              <p className="muted small">{m.body}</p>
            </li>
          ))}
        </ul>
      )}
      <form
        className="inline-form"
        style={{ boxShadow: "none", border: 0, padding: 0, marginTop: 8 }}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <div className="form-grid">
          <label className="field">
            <span>Type</span>
            <select
              value={kind}
              onChange={(e) =>
                onKind(e.target.value as CollectionDialogueKind)
              }
            >
              {DIALOGUE_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          <span>Commentaire / recommandation</span>
          <textarea
            rows={2}
            value={body}
            onChange={(e) => onBody(e.target.value)}
            required
          />
        </label>
        <button className="btn btn-primary btn-sm" disabled={pending}>
          Envoyer
        </button>
      </form>
    </div>
  );
}

const STAGES: { value: CollectionStage; label: string }[] = [
  { value: "AMICABLE", label: "Amiable" },
  { value: "PRECONTENTIOUS", label: "Précontentieux" },
  { value: "LITIGATION", label: "Contentieux" },
  { value: "CLOSED", label: "Clôturé" },
];

export function CollectionCaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const smsEnabled = isSmsEnabled(user);
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const canRestructure = hasPerm(user, "collections.add_loanrestructure");
  const canDecideRestructure = hasPerm(user, "collections.change_loanrestructure");
  const canWriteOff = hasPerm(user, "collections.add_writeoff");
  const canDecideWriteOff = hasPerm(user, "collections.change_writeoff");
  const canLitigation = hasPerm(user, "collections.change_litigationfile");
  const canManageCase = hasPerm(user, "collections.change_collectioncase");
  const canAddAction = hasPerm(user, "collections.add_collectionaction");
  const canAddPromise = hasPerm(user, "collections.add_paymentpromise");
  const canInitiateDation = hasPerm(user, "guarantees.initiate_dationrequest");
  const canCallSurety = hasPerm(user, "sureties.change_suretyengagement");
  const canViewDations = hasAnyPerm(user, PERM_DATIONS);
  const canViewGuarantees = hasAnyPerm(user, PERM_GUARANTEES);

  const [actionType, setActionType] = useState<CollectionActionType>("CALL");
  const [actionDate, setActionDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [actionResult, setActionResult] = useState("");
  const [actionComment, setActionComment] = useState("");
  const [actionFollowUp, setActionFollowUp] = useState("");
  const [actionFile, setActionFile] = useState<File | null>(null);
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [editResult, setEditResult] = useState("");
  const [editComment, setEditComment] = useState("");
  const [editFile, setEditFile] = useState<File | null>(null);

  const [dialogueKind, setDialogueKind] =
    useState<CollectionDialogueKind>("QUESTION");
  const [dialogueBody, setDialogueBody] = useState("");
  const [actionDialogue, setActionDialogue] = useState<
    Record<string, { kind: CollectionDialogueKind; body: string }>
  >({});

  const [promiseAmount, setPromiseAmount] = useState("");
  const [promiseDate, setPromiseDate] = useState("");
  const [assignUserId, setAssignUserId] = useState<string>("");

  const [nextDate, setNextDate] = useState("");
  const [nextType, setNextType] = useState<CollectionActionType | "">("");
  const [nextNote, setNextNote] = useState("");

  const caseQuery = useQuery({
    queryKey: ["collection-case", id],
    queryFn: async () =>
      (await api.get<CollectionCase>(`/collection-cases/${id}/`)).data,
    enabled: !!id,
  });

  const canOperateCase = Boolean(caseQuery.data?.can_operate);

  const agents = useQuery({
    queryKey: ["collection-assign-users"],
    queryFn: async () =>
      (
        await api.get<Paginated<AdminUser>>("/users/", {
          params: { page_size: 200, is_active: true },
        })
      ).data,
    enabled: canManageCase && canOperateCase,
  });

  useEffect(() => {
    const c = caseQuery.data;
    if (!c) return;
    setNextDate(c.next_action_date || "");
    setNextType(c.next_action_type || "");
    setNextNote(c.next_action_note || "");
    setAssignUserId(c.assigned_to || "");
  }, [caseQuery.data]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["collection-case", id] });
    qc.invalidateQueries({ queryKey: ["collection-cases"] });
    qc.invalidateQueries({ queryKey: ["collection-agent-dashboard"] });
  };

  const refreshCbsMutation = useMutation({
    mutationFn: async () =>
      (await api.post(`/collection-cases/${id}/refresh-cbs/`)).data as CollectionCase,
    onSuccess: (updated) => {
      qc.setQueryData(["collection-case", id], updated);
      setError(null);
      if (updated.stage === "CLOSED") {
        setSuccess("Le CBS indique un crédit soldé — dossier clôturé.");
      } else {
        setSuccess("Situation d'impayé actualisée depuis le CBS.");
      }
      invalidate();
    },
    onError: (err: unknown) => {
      setError(apiErrorMessage(err, "Impossible de lire la situation CBS."));
    },
  });

  const actionMutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("case", id || "");
      fd.append("action_type", actionType);
      fd.append("action_date", actionDate);
      fd.append("result", actionResult);
      fd.append("comment", actionComment);
      if (actionFollowUp) fd.append("next_follow_up_date", actionFollowUp);
      if (actionFile) fd.append("attachment", actionFile);
      return (await api.post("/collection-actions/", fd)).data;
    },
    onSuccess: () => {
      setActionResult("");
      setActionComment("");
      setActionFollowUp("");
      setActionFile(null);
      setSuccess("Action de relance enregistrée.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible d'enregistrer l'action.")),
  });

  const actionEditMutation = useMutation({
    mutationFn: async (actionId: string) => {
      const fd = new FormData();
      fd.append("result", editResult);
      fd.append("comment", editComment);
      if (editFile) fd.append("attachment", editFile);
      return (await api.patch(`/collection-actions/${actionId}/`, fd)).data;
    },
    onSuccess: () => {
      setEditingActionId(null);
      setEditFile(null);
      setSuccess("Action mise à jour.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible de modifier cette action.")),
  });

  const dialogueMutation = useMutation({
    mutationFn: async (payload: {
      kind: CollectionDialogueKind;
      body: string;
      action?: string;
    }) =>
      (
        await api.post(`/collection-cases/${id}/dialogue/`, {
          kind: payload.kind,
          body: payload.body,
          ...(payload.action ? { action: payload.action } : {}),
        })
      ).data,
    onSuccess: (_data, payload) => {
      if (payload.action) {
        setActionDialogue((prev) => ({
          ...prev,
          [payload.action as string]: { kind: "QUESTION", body: "" },
        }));
        setSuccess("Commentaire ajouté à l'action.");
      } else {
        setDialogueBody("");
        setSuccess("Message ajouté au dialogue du dossier.");
      }
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible d'envoyer le message.")),
  });

  const promiseMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post("/payment-promises/", {
          case: id,
          amount: promiseAmount,
          promised_date: promiseDate,
          status: "PENDING" as PromiseStatus,
        })
      ).data,
    onSuccess: () => {
      setPromiseAmount("");
      setPromiseDate("");
      setSuccess("Promesse de paiement enregistrée.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible d'enregistrer la promesse.")),
  });

  const promiseStatusMutation = useMutation({
    mutationFn: async ({
      promiseId,
      status,
    }: {
      promiseId: string;
      status: PromiseStatus;
    }) =>
      (
        await api.patch(`/payment-promises/${promiseId}/`, {
          status,
        })
      ).data,
    onSuccess: () => {
      setSuccess("Statut de la promesse mis à jour.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible de mettre à jour la promesse.")),
  });

  const assignMutation = useMutation({
    mutationFn: async (assignedTo: string | null) =>
      (
        await api.post(`/collection-cases/${id}/assign/`, {
          assigned_to: assignedTo,
        })
      ).data,
    onSuccess: () => {
      setSuccess("Affectation mise à jour.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible d'affecter l'agent.")),
  });

  const stageMutation = useMutation({
    mutationFn: async (stage: CollectionStage) =>
      (await api.post(`/collection-cases/${id}/set-stage/`, { stage })).data,
    onSuccess: () => {
      setSuccess("Stade mis à jour.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible de changer le stade.")),
  });

  const nextActionMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/collection-cases/${id}/set-next-action/`, {
          next_action_date: nextDate || null,
          next_action_type: nextType || "",
          next_action_note: nextNote,
        })
      ).data,
    onSuccess: () => {
      setSuccess("Prochaine action planifiée.");
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible de planifier la prochaine action.")),
  });

  const reminderMutation = useMutation({
    mutationFn: async (channel: "EMAIL" | "SMS") =>
      (
        await api.post(`/collection-cases/${id}/send-reminder/`, { channel })
      ).data,
    onSuccess: (data: { reminder?: { status?: string } }) => {
      setSuccess(`Relance : ${data.reminder?.status || "OK"}`);
      setError(null);
      invalidate();
    },
    onError: (err) =>
      setError(apiErrorMessage(err, "Impossible d'envoyer la relance.")),
  });

  const createLitigation = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/litigations/`, {
          case: id,
          title: "Procédure contentieuse",
          action_type: "SUMMONS",
          status: "PRE_LITIGATION",
        })
      ).data as { id: string },
    onSuccess: (lit) => {
      invalidate();
      navigate(`/recouvrement/${id}/contentieux/${lit.id}`);
    },
    onError: (err) =>
      setError(
        apiErrorMessage(err, "Impossible d'ouvrir une procédure contentieuse."),
      ),
  });

  function submitAction(e: FormEvent) {
    e.preventDefault();
    setSuccess(null);
    actionMutation.mutate();
  }

  function submitPromise(e: FormEvent) {
    e.preventDefault();
    setSuccess(null);
    if (!promiseAmount || !promiseDate) {
      setError("Montant et date de promesse obligatoires.");
      return;
    }
    promiseMutation.mutate();
  }

  function submitNextAction(e: FormEvent) {
    e.preventDefault();
    setSuccess(null);
    nextActionMutation.mutate();
  }

  if (caseQuery.isLoading) {
    return <Spinner />;
  }
  if (caseQuery.isError || !caseQuery.data) {
    return (
      <ErrorState
        message="Impossible de charger le dossier de recouvrement."
        onRetry={() => caseQuery.refetch()}
      />
    );
  }

  const c = caseQuery.data;
  const canOperate = Boolean(c.can_operate);
  const canWrite = canOperate;
  const canCollect = Boolean(c.can_collect);
  const financeFrozen = Boolean(c.financial_ops_frozen);
  const openDation = Boolean(
    c.blocking_dation &&
      c.blocking_dation.status !== "COMPLETED" &&
      c.blocking_dation.status !== "REJECTED" &&
      c.blocking_dation.status !== "CANCELLED",
  );

  return (
    <div className="page-shell detail-banner-page">
      <div className="client-banner">
        <div className="client-banner-main">
          <div className="client-banner-info">
            <span className="client-banner-icon">
              <CircleDollarSign size={26} />
            </span>
            <div className="client-banner-identity">
              <h2 className="client-banner-name">
                {c.client_name || "Recouvrement"}
              </h2>
              <p className="client-banner-ref">
                Recouvrement{" "}
                <code>{c.application_reference || c.id.slice(0, 8)}</code>
                {c.application_id && (
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    className="client-banner-inline-link"
                    to={`/dossiers/${c.application_id}`}
                    fallback={
                      c.application_reference ? (
                        <span className="muted">
                          · Crédit {c.application_reference}
                        </span>
                      ) : null
                    }
                  >
                    · Dossier crédit{" "}
                    {c.application_reference || c.application_id.slice(0, 8)}
                  </PermLink>
                )}
              </p>
              <div className="client-banner-meta">
                <Badge value={c.stage} label={c.stage_display} />
                {c.par_class_display && (
                  <Badge value={c.par_class} label={c.par_class_display} />
                )}
                <span className="muted">
                  {c.days_overdue} j · Impayé {formatMoney(c.overdue_amount)}
                </span>
                {c.agency_name && (
                  <span className="muted">{c.agency_name}</span>
                )}
                {c.product_name && (
                  <span className="muted">{c.product_name}</span>
                )}
              </div>
            </div>
          </div>

          <div className="client-banner-actions">
            <Link className="btn btn-banner" to="/recouvrement">
              <ArrowLeft size={15} />
              Retour
            </Link>
            <button
              type="button"
              className="btn btn-banner"
              onClick={() => exportCollectionCasePdf(c)}
            >
              <Download size={15} />
              PDF
            </button>
            {(canOperate || canManageCase) && (
              <button
                type="button"
                className="btn btn-banner"
                disabled={refreshCbsMutation.isPending}
                onClick={() => {
                  setSuccess(null);
                  refreshCbsMutation.mutate();
                }}
              >
                {refreshCbsMutation.isPending
                  ? "Lecture CBS…"
                  : "Actualiser CBS"}
              </button>
            )}
          </div>
        </div>
      </div>

      {success && (
        <div className="form-success" style={{ marginBottom: 12 }}>
          {success}
        </div>
      )}
      {!canWrite && (
        <p className="muted" style={{ marginBottom: 12 }}>
          Consultation : les actions de recouvrement sont réservées au
          responsable de cette tranche. Vous pouvez dialoguer ci-dessous.
        </p>
      )}
      {financeFrozen && (
        <div className="callout callout-warning">
          {c.financial_ops_frozen_reason}
          {c.blocking_dation?.id && canViewDations && (
            <>
              {" "}
              <Link to={`/dations/${c.blocking_dation.id}`}>
                Voir la dation
                {c.blocking_dation.reference
                  ? ` ${c.blocking_dation.reference}`
                  : ""}
              </Link>
            </>
          )}
        </div>
      )}
      {error && (
        <div className="form-error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      <div className="detail-grid">
        <Card title="Situation">
          <dl className="def-list two">
            <div>
              <dt>Client</dt>
              <dd>{c.client_name}</dd>
            </div>
            <div>
              <dt>Dossier</dt>
              <dd>
                {c.application_id ? (
                  <PermLink
                    user={user}
                    anyOf={PERM_CREDITS}
                    to={`/dossiers/${c.application_id}`}
                  >
                    {c.application_reference || "Voir le dossier"}
                  </PermLink>
                ) : (
                  c.application_reference || "—"
                )}
              </dd>
            </div>
            <div>
              <dt>Produit</dt>
              <dd>{c.product_name || "—"}</dd>
            </div>
            <div>
              <dt>Capital prêt</dt>
              <dd>{formatMoney(c.loan_principal)}</dd>
            </div>
            <div>
              <dt>Statut prêt</dt>
              <dd>
                <Badge value={c.loan_status} />
              </dd>
            </div>
            <div>
              <dt>Réf. CBS</dt>
              <dd>{c.core_banking_reference || "—"}</dd>
            </div>
            <div>
              <dt>Synchro CBS</dt>
              <dd>
                {c.cbs_synced_at
                  ? String(c.cbs_synced_at).replace("T", " ").slice(0, 16)
                  : "—"}
                {c.cbs_sync_error ? (
                  <span className="form-error" style={{ display: "block" }}>
                    {c.cbs_sync_error}
                  </span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt>PAR</dt>
              <dd>
                <Badge value={c.par_class_display} />
              </dd>
            </div>
            <div>
              <dt>Tranche</dt>
              <dd>
                <Badge
                  value={
                    c.tranche_name
                      ? `${c.tranche_name}${
                          c.tranche_owner_kind_display
                            ? ` · ${c.tranche_owner_kind_display}`
                            : ""
                        }`
                      : "—"
                  }
                />
              </dd>
            </div>
            <div>
              <dt>Jours de retard</dt>
              <dd>{c.days_overdue}</dd>
            </div>
            <div>
              <dt>Montant impayé</dt>
              <dd>{formatMoney(c.overdue_amount)}</dd>
            </div>
            <div>
              <dt>Capital restant dû</dt>
              <dd>{formatMoney(c.outstanding_principal || "0")}</dd>
            </div>
            <div>
              <dt>Prochaine échéance</dt>
              <dd>{c.next_due_date || "—"}</dd>
            </div>
            <div>
              <dt>Agent</dt>
              <dd>
                {canWrite && canManageCase ? (
                  <div className="row-actions" style={{ gap: 8 }}>
                    <select
                      value={assignUserId}
                      onChange={(e) => setAssignUserId(e.target.value)}
                    >
                      <option value="">Non affecté</option>
                      {(agents.data?.results ?? []).map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.first_name || u.last_name
                            ? `${u.first_name} ${u.last_name}`.trim()
                            : u.username}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={
                        assignMutation.isPending ||
                        assignUserId === (c.assigned_to || "")
                      }
                      onClick={() =>
                        assignMutation.mutate(assignUserId || null)
                      }
                    >
                      Affecter
                    </button>
                  </div>
                ) : (
                  c.assigned_to_name || "Non affecté"
                )}
              </dd>
            </div>
            <div>
              <dt>Stade</dt>
              <dd>
                {canWrite && canManageCase ? (
                  <select
                    value={c.stage}
                    onChange={(e) =>
                      stageMutation.mutate(e.target.value as CollectionStage)
                    }
                    disabled={stageMutation.isPending}
                  >
                    {STAGES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Badge value={c.stage_display || c.stage} />
                )}
              </dd>
            </div>
            <div>
              <dt>Prochaine action</dt>
              <dd>
                {c.next_action_date
                  ? `${c.next_action_date}${
                      c.next_action_type_display
                        ? ` · ${c.next_action_type_display}`
                        : ""
                    }`
                  : "Non planifiée"}
                {c.next_action_note ? (
                  <div className="muted small">{c.next_action_note}</div>
                ) : null}
              </dd>
            </div>
          </dl>
        </Card>

        <Card title="Situation CBS">
          <p className="muted small">
            Les versements sont saisis dans le CBS. FinFlow relit l&apos;impayé
            : le retard diminue, ou le crédit passe soldé et le dossier se
            clôture.
          </p>
          {c.core_banking_reference ? (
            <p className="muted small">
              Référence prêt : {c.core_banking_reference}
            </p>
          ) : (
            <p className="form-error" style={{ marginTop: 8 }}>
              Aucune référence CBS sur ce prêt — le retard ne peut pas être
              relu.
            </p>
          )}
        </Card>
      </div>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        {canWrite && canManageCase && (
        <Card title="Planifier la prochaine action">
          <form
            className="inline-form"
            style={{ boxShadow: "none", border: 0, padding: 0 }}
            onSubmit={submitNextAction}
          >
            <div className="form-grid">
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={nextDate}
                  onChange={(e) => setNextDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Type</span>
                <select
                  value={nextType}
                  onChange={(e) =>
                    setNextType(e.target.value as CollectionActionType | "")
                  }
                >
                  <option value="">—</option>
                  {ACTION_TYPES.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Note</span>
                <input
                  value={nextNote}
                  onChange={(e) => setNextNote(e.target.value)}
                  placeholder="Ex. visite domicile"
                />
              </label>
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={nextActionMutation.isPending}
            >
              Enregistrer
            </button>
          </form>
        </Card>
        )}

        <Card title="Garanties, cautions et dations">
          {!c.guarantees?.length &&
          !c.surety_engagements?.length &&
          !c.dation_requests?.length ? (
            <p className="muted small">
              Aucune garantie, caution ni dation liée.
            </p>
          ) : null}
          {!!c.guarantees?.length && (
            <ul className="timeline-list" style={{ marginBottom: 12 }}>
              {c.guarantees.map((g) => (
                <li
                  key={g.id}
                  className="row-clickable"
                  onClick={() => navigate(`/garanties/${g.id}`)}
                >
                  <PermLink
                    user={user}
                    anyOf={PERM_GUARANTEES}
                    to={`/garanties/${g.id}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {g.guarantee_type_display}
                  </PermLink>
                  {" · "}
                  <Badge value={g.status_display} />
                  {g.description ? (
                    <span className="muted small"> — {g.description}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {!!c.surety_engagements?.length && (
            <ul className="timeline-list" style={{ marginBottom: 12 }}>
              {c.surety_engagements.map((e) => (
                <li
                  key={e.id}
                  className="row-clickable"
                  onClick={() => navigate(`/cautions/${e.surety}`)}
                >
                  <PermLink
                    user={user}
                    anyOf={PERM_SURETIES}
                    to={`/cautions/${e.surety}`}
                    onClick={(ev) => ev.stopPropagation()}
                  >
                    {e.surety_display}
                  </PermLink>
                  {" · "}
                  <Badge value={e.status_display || e.status} />
                  {e.engagement_type_display ? (
                    <span className="muted small">
                      {" "}
                      — {e.engagement_type_display}
                    </span>
                  ) : null}
                  {canWrite && canCallSurety && (
                    <div onClick={(ev) => ev.stopPropagation()}>
                      <SuretyEngagementActions
                        engagement={e}
                        canManage
                        canContracts={false}
                        invalidateKeys={[["collection-case", id]]}
                      />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {!!c.dation_requests?.length && (
            <ul className="timeline-list">
              {c.dation_requests.map((d) => (
                <li
                  key={d.id}
                  className="row-clickable"
                  onClick={() => navigate(`/dations/${d.id}`)}
                >
                  <PermLink
                    user={user}
                    anyOf={PERM_DATIONS}
                    to={`/dations/${d.id}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {d.reference ? `Dation ${d.reference}` : "Dation"}
                  </PermLink>
                  {" · "}
                  <Badge value={d.status_display} />
                  <span className="muted small">
                    {" "}
                    — {new Date(d.created_at).toLocaleDateString("fr-FR")}
                    {d.residual_balance && Number(d.residual_balance) > 0
                      ? ` · résiduel ${d.residual_balance}`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {c.application_id && (
            <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {canViewGuarantees && (
              <Link
                className="btn btn-ghost btn-sm"
                to={`/garanties?application=${c.application_id}`}
              >
                Voir garanties
              </Link>
              )}
              {canWrite && canInitiateDation && !openDation && (
                <Link
                  className="btn btn-ghost btn-sm"
                  to={`/dations/nouvelle?application=${c.application_id}`}
                >
                  Nouvelle dation
                </Link>
              )}
            </div>
          )}
        </Card>
      </div>

      <Card title="Échéancier" className="mt-card">
        {!c.installments?.length ? (
          <p className="muted">Aucune échéance.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>N°</th>
                <th>Échéance</th>
                <th className="num">Dû</th>
                <th className="num">Payé</th>
                <th className="num">Reste</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {c.installments.map((i) => (
                <tr key={i.id}>
                  <td>{i.number}</td>
                  <td>{i.due_date}</td>
                  <td className="num">{formatMoney(i.total_due)}</td>
                  <td className="num">{formatMoney(i.amount_paid)}</td>
                  <td className="num">{formatMoney(i.balance)}</td>
                  <td>
                    <Badge value={i.status_display} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        <Card title="Historique des actions">
          {canWrite && canAddAction && (
          <form
            className="inline-form"
            style={{
              boxShadow: "none",
              border: 0,
              padding: 0,
              marginBottom: 16,
            }}
            onSubmit={submitAction}
          >
            <div className="form-grid">
              <label className="field">
                <span>Type</span>
                <select
                  value={actionType}
                  onChange={(e) =>
                    setActionType(e.target.value as CollectionActionType)
                  }
                >
                  {ACTION_TYPES.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={actionDate}
                  onChange={(e) => setActionDate(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Résultat</span>
                <input
                  value={actionResult}
                  onChange={(e) => setActionResult(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Suivi prévu</span>
                <input
                  type="date"
                  value={actionFollowUp}
                  onChange={(e) => setActionFollowUp(e.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span>Commentaire</span>
              <textarea
                rows={2}
                value={actionComment}
                onChange={(e) => setActionComment(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Pièce jointe</span>
              <input
                type="file"
                onChange={(e) => setActionFile(e.target.files?.[0] || null)}
              />
            </label>
            <button
              className="btn btn-primary btn-sm"
              disabled={actionMutation.isPending}
            >
              Ajouter l&apos;action
            </button>
          </form>
          )}
          {!c.actions?.length ? (
            <p className="muted small">Aucune action.</p>
          ) : (
            <ul className="timeline-list">
              {c.actions.map((a) => (
                <li key={a.id}>
                  <strong>
                    {a.action_type_display} — {a.action_date}
                  </strong>
                  {a.result && <span> · {a.result}</span>}
                  {a.next_follow_up_date && (
                    <span className="muted small">
                      {" "}
                      · suivi {a.next_follow_up_date}
                    </span>
                  )}
                  {a.created_by_name && (
                    <span className="muted small">
                      {" "}
                      · {a.created_by_name}
                    </span>
                  )}
                  {a.comment && <p className="muted small">{a.comment}</p>}
                  {a.attachment_url && (
                    <p className="muted small">
                      <a href={a.attachment_url} target="_blank" rel="noreferrer">
                        Pièce jointe
                      </a>
                    </p>
                  )}
                  {a.can_edit && (
                    <div style={{ marginTop: 6 }}>
                      {editingActionId === a.id ? (
                        <form
                          onSubmit={(e) => {
                            e.preventDefault();
                            actionEditMutation.mutate(a.id);
                          }}
                        >
                          <input
                            value={editResult}
                            onChange={(e) => setEditResult(e.target.value)}
                            placeholder="Résultat"
                          />
                          <textarea
                            rows={2}
                            value={editComment}
                            onChange={(e) => setEditComment(e.target.value)}
                            placeholder="Commentaire"
                          />
                          <input
                            type="file"
                            onChange={(e) =>
                              setEditFile(e.target.files?.[0] || null)
                            }
                          />
                          <div className="row-actions" style={{ gap: 6 }}>
                            <button
                              type="submit"
                              className="btn btn-primary btn-sm"
                              disabled={actionEditMutation.isPending}
                            >
                              Enregistrer
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => setEditingActionId(null)}
                            >
                              Annuler
                            </button>
                          </div>
                        </form>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            setEditingActionId(a.id);
                            setEditResult(a.result || "");
                            setEditComment(a.comment || "");
                            setEditFile(null);
                          }}
                        >
                          Modifier
                        </button>
                      )}
                    </div>
                  )}
                  <DialogueComposer
                    messages={a.dialogue || []}
                    kind={actionDialogue[a.id]?.kind || "QUESTION"}
                    body={actionDialogue[a.id]?.body || ""}
                    onKind={(kind) =>
                      setActionDialogue((prev) => ({
                        ...prev,
                        [a.id]: {
                          kind,
                          body: prev[a.id]?.body || "",
                        },
                      }))
                    }
                    onBody={(body) =>
                      setActionDialogue((prev) => ({
                        ...prev,
                        [a.id]: {
                          kind: prev[a.id]?.kind || "QUESTION",
                          body,
                        },
                      }))
                    }
                    onSubmit={() => {
                      const draft = actionDialogue[a.id];
                      const text = (draft?.body || "").trim();
                      if (!text) {
                        setError("Saisissez un commentaire sur cette action.");
                        return;
                      }
                      setSuccess(null);
                      dialogueMutation.mutate({
                        kind: draft?.kind || "QUESTION",
                        body: text,
                        action: a.id,
                      });
                    }}
                    pending={dialogueMutation.isPending}
                    emptyLabel="Aucun commentaire sur cette action."
                  />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Promesses de paiement">
          {canWrite && canAddPromise && (
          <form
            className="inline-form"
            style={{
              boxShadow: "none",
              border: 0,
              padding: 0,
              marginBottom: 16,
            }}
            onSubmit={submitPromise}
          >
            <div className="form-grid">
              <label className="field">
                <span>Montant</span>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  value={promiseAmount}
                  onChange={(e) => setPromiseAmount(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Date promise</span>
                <input
                  type="date"
                  value={promiseDate}
                  onChange={(e) => setPromiseDate(e.target.value)}
                  required
                />
              </label>
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={promiseMutation.isPending}
            >
              Enregistrer la promesse
            </button>
          </form>
          )}
          {!c.promises?.length ? (
            <p className="muted small">Aucune promesse.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Montant</th>
                  <th>Statut</th>
                  <th>Saisi par</th>
                  {canWrite && <th></th>}
                </tr>
              </thead>
              <tbody>
                {c.promises.map((p) => (
                  <tr key={p.id}>
                    <td>{p.promised_date}</td>
                    <td className="num">{formatMoney(p.amount)}</td>
                    <td>
                      <Badge value={p.status_display} />
                    </td>
                    <td className="muted small">{p.created_by_name || "—"}</td>
                    {canWrite && (
                      <td>
                        {p.status === "PENDING" && p.can_edit && (
                          <div className="row-actions" style={{ gap: 4 }}>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              disabled={promiseStatusMutation.isPending}
                              onClick={() =>
                                promiseStatusMutation.mutate({
                                  promiseId: p.id,
                                  status: "KEPT",
                                })
                              }
                            >
                              Tenue
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              disabled={promiseStatusMutation.isPending}
                              onClick={() =>
                                promiseStatusMutation.mutate({
                                  promiseId: p.id,
                                  status: "BROKEN",
                                })
                              }
                            >
                              Rompue
                            </button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        {canWrite && canManageCase && (
        <Card title="Relances">
          <p className="muted small" style={{ marginBottom: 10 }}>
            Envoi immédiat (force les préférences filiale).
            {smsEnabled
              ? " SMS disponible si un provider est configuré."
              : " Canal SMS désactivé (FEATURE_SMS=0)."}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={reminderMutation.isPending || c.stage === "CLOSED"}
              onClick={() => reminderMutation.mutate("EMAIL")}
            >
              <Mail size={14} /> Relancer e-mail
            </button>
            {smsEnabled && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={reminderMutation.isPending || c.stage === "CLOSED"}
                onClick={() => reminderMutation.mutate("SMS")}
              >
                <MessageSquare size={14} /> Relancer SMS
              </button>
            )}
          </div>
        </Card>
        )}

        {(canCollect && canRestructure && c.loan_status === "ACTIVE" && c.stage !== "CLOSED") ||
        canDecideRestructure ||
        (c.restructures?.length ?? 0) > 0 ? (
          <Card title="Restructuration">
            <RestructureRequestPanel
              origin="COLLECTION"
              loanId={c.loan}
              caseId={c.id}
              currency=""
              outstanding={c.outstanding_principal}
              currentDuration={12}
              currentRate=""
              restructures={c.restructures || []}
              canPropose={canCollect && canRestructure && c.stage !== "CLOSED"}
              canDecide={canDecideRestructure}
              frozen={c.financial_ops_frozen}
              frozenReason={c.financial_ops_frozen_reason}
              loanActive={c.loan_status === "ACTIVE"}
              currentUserId={user?.id}
              onChanged={invalidate}
              onError={(msg) => setError(msg || null)}
              onSuccess={(msg) => {
                setSuccess(msg);
                setError(null);
              }}
            />
          </Card>
        ) : null}
      </div>

      {((canCollect && canWriteOff) ||
        canDecideWriteOff ||
        (c.write_offs?.length ?? 0) > 0 ||
        canLitigation ||
        c.litigations?.length) && (
        <div className="detail-grid" style={{ marginTop: 16 }}>
          {(canCollect && canWriteOff) ||
          canDecideWriteOff ||
          (c.write_offs?.length ?? 0) > 0 ? (
            <Card title="Passage en perte">
              <WriteOffRequestPanel
                caseId={c.id}
                currency=""
                writeOffs={c.write_offs || []}
                canPropose={canCollect && canWriteOff}
                canDecide={canDecideWriteOff}
                frozen={c.financial_ops_frozen}
                frozenReason={c.financial_ops_frozen_reason}
                loanActive={c.loan_status === "ACTIVE"}
                currentUserId={user?.id}
                onChanged={invalidate}
                onError={(msg) => setError(msg || null)}
                onSuccess={(msg) => {
                  setSuccess(msg);
                  setError(null);
                }}
              />
            </Card>
          ) : null}

          {canLitigation && (
            <Card title="Contentieux">
              <p className="muted small">
                Procédures judiciaires : cabinets, audiences, pièces, frais et
                saisies.
              </p>
              {canWrite && canLitigation && (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                style={{ marginBottom: 12 }}
                disabled={createLitigation.isPending}
                onClick={() => createLitigation.mutate()}
              >
                Nouvelle procédure
              </button>
              )}
              <ul className="timeline-list">
                {(c.litigations || (c.litigation ? [c.litigation] : [])).map(
                  (lit) => (
                    <li key={lit.id}>
                      <PermLink
                        user={user}
                        anyOf={PERM_LITIGATION}
                        to={`/recouvrement/${id}/contentieux/${lit.id}`}
                      >
                        <strong>
                          {lit.title || lit.case_reference || "Procédure"}
                        </strong>
                      </PermLink>
                      {" · "}
                      <Badge value={lit.status_display} />
                      {lit.hearing_date && (
                        <span className="muted small">
                          {" "}
                          · audience {lit.hearing_date}
                        </span>
                      )}
                      {lit.law_firm_detail?.name && (
                        <span className="muted small">
                          {" "}
                          · {lit.law_firm_detail.name}
                        </span>
                      )}
                    </li>
                  ),
                )}
                {!c.litigations?.length && !c.litigation && (
                  <li className="muted small">Aucune procédure.</li>
                )}
              </ul>
              {hasAnyPerm(user, PERM_LEGAL_PARTIES_MANAGE) && (
                <Link
                  className="btn btn-ghost btn-sm"
                  to="/admin/intervenants-juridiques"
                  style={{ marginTop: 8 }}
                >
                  Intervenants juridiques
                </Link>
              )}
            </Card>
          )}
        </div>
      )}

      <Card title="Dialogue du dossier" className="mt-card">
        <p className="muted small" style={{ marginBottom: 10 }}>
          Échanges généraux sur le dossier (hors action). Pour commenter une
          relance précise, utilisez le fil sous l&apos;action.
        </p>
        <DialogueComposer
          messages={c.dialogue || []}
          kind={dialogueKind}
          body={dialogueBody}
          onKind={setDialogueKind}
          onBody={setDialogueBody}
          onSubmit={() => {
            if (!dialogueBody.trim()) {
              setError("Saisissez un message.");
              return;
            }
            setSuccess(null);
            dialogueMutation.mutate({
              kind: dialogueKind,
              body: dialogueBody,
            });
          }}
          pending={dialogueMutation.isPending}
          emptyLabel="Aucun message sur le dossier."
        />
      </Card>

      <Card title="Historique des stades" className="mt-card">
        {!c.stage_history?.length ? (
          <p className="muted small">Aucun changement de stade.</p>
        ) : (
          <ul className="timeline-list">
            {c.stage_history.map((h) => (
              <li key={h.id}>
                <strong>
                  {h.from_stage_display} → {h.to_stage_display}
                </strong>
                <span className="muted small">
                  {" "}
                  — {new Date(h.created_at).toLocaleString("fr-FR")}
                  {h.automatic ? " · auto" : ""}
                  {h.changed_by_name ? ` · ${h.changed_by_name}` : ""}
                </span>
                {h.reason && <p className="muted small">{h.reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

    </div>
  );
}
