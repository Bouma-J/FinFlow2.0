import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import type {
  LoanRestructure,
  LoanRestructurePreview,
  WriteOff,
} from "@/api/types";
import { Badge, formatMoney } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const CBS_NOTE =
  "Perfect n'a pas d'API de restructuration. La décision est interne à FinFlow : l'échéancier CBS reste inchangé tant qu'il n'est pas saisi manuellement dans le core banking.";

function statusBadge(status: string, label?: string) {
  const tone =
    status === "PENDING"
      ? "warning"
      : status === "APPROVED" || status === "APPLIED"
        ? "success"
        : status === "REJECTED"
          ? "danger"
          : "muted";
  return <Badge value={status} label={label || status} tone={tone} />;
}

function SchedulePreview({
  preview,
  currency,
}: {
  preview: LoanRestructurePreview | Record<string, unknown> | undefined;
  currency: string;
}) {
  const rows = (preview as LoanRestructurePreview | undefined)?.rows;
  if (!rows?.length) return null;
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Masquer l'échéancier proposé" : "Voir l'échéancier proposé"}
      </button>
      {open && (
        <div className="table-scroll" style={{ marginTop: 8 }}>
          <table className="table">
            <thead>
              <tr>
                <th>N°</th>
                <th>Date</th>
                <th className="num">Capital</th>
                <th className="num">Intérêt</th>
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 24).map((row) => (
                <tr key={row.number}>
                  <td>{row.number}</td>
                  <td>{row.due_date}</td>
                  <td className="num">{formatMoney(row.principal, currency)}</td>
                  <td className="num">{formatMoney(row.interest, currency)}</td>
                  <td className="num">{formatMoney(row.total, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 24 && (
            <p className="muted small">… {rows.length - 24} échéances suivantes</p>
          )}
        </div>
      )}
    </div>
  );
}

export function RestructureRequestPanel({
  origin,
  loanId,
  caseId,
  currency,
  outstanding,
  currentDuration,
  currentRate,
  restructures,
  canPropose,
  canDecide,
  frozen,
  frozenReason,
  loanActive,
  currentUserId,
  onChanged,
  onError,
  onSuccess,
}: {
  origin: "LOAN" | "COLLECTION";
  loanId: string;
  caseId?: string | null;
  currency: string;
  outstanding?: string;
  currentDuration: number;
  currentRate: string;
  restructures: LoanRestructure[];
  canPropose: boolean;
  canDecide: boolean;
  frozen?: boolean;
  frozenReason?: string;
  loanActive: boolean;
  currentUserId?: string | null;
  onChanged: () => void;
  onError: (msg: string) => void;
  onSuccess: (msg: string) => void;
}) {
  const [months, setMonths] = useState(String(Math.max(currentDuration, 1)));
  const [rate, setRate] = useState("");
  const [reason, setReason] = useState("");
  const [kind, setKind] = useState(origin === "LOAN" ? "CLIENT" : "INTERNAL");
  const [preview, setPreview] = useState<LoanRestructurePreview | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState("");

  const proposeUrl =
    origin === "COLLECTION" && caseId
      ? `/collection-cases/${caseId}/restructure/`
      : `/loans/${loanId}/restructure/`;
  const previewUrl =
    origin === "COLLECTION" && caseId
      ? `/collection-cases/${caseId}/preview-restructure/`
      : `/loans/${loanId}/preview-restructure/`;

  const pending = restructures.find((r) => r.status === "PENDING");
  const showForm =
    canPropose && loanActive && !frozen && !pending;

  const previewMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<LoanRestructurePreview>(previewUrl, {
          new_duration_months: Number(months),
          ...(rate ? { new_rate: rate } : {}),
          reason: reason || "Prévisualisation",
        })
      ).data,
    onSuccess: (data) => {
      setPreview(data);
      onError("");
    },
    onError: (e) =>
      onError(apiErrorMessage(e, "Impossible de simuler l'échéancier.")),
  });

  const proposeMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post(proposeUrl, {
          new_duration_months: Number(months),
          ...(rate ? { new_rate: rate } : {}),
          reason,
          request_kind: kind,
        })
      ).data,
    onSuccess: () => {
      setReason("");
      setPreview(null);
      onSuccess("Demande de restructuration enregistrée — en attente de second regard.");
      onChanged();
    },
    onError: (e) =>
      onError(apiErrorMessage(e, "Impossible d'enregistrer la demande.")),
  });

  const decideMutation = useMutation({
    mutationFn: async ({
      id,
      action,
      comment,
    }: {
      id: string;
      action: "approve" | "reject" | "cancel";
      comment?: string;
    }) =>
      (
        await api.post(`/loan-restructures/${id}/${action}/`, {
          ...(comment ? { comment } : {}),
        })
      ).data,
    onSuccess: (_data, vars) => {
      setRejectId(null);
      setRejectComment("");
      const msg =
        vars.action === "approve"
          ? "Restructuration approuvée (à saisir dans Perfect)."
          : vars.action === "reject"
            ? "Demande rejetée."
            : "Demande annulée.";
      onSuccess(msg);
      onChanged();
    },
    onError: (e) =>
      onError(apiErrorMessage(e, "La décision n'a pas pu être enregistrée.")),
  });

  return (
    <div className="stack" style={{ gap: 12 }}>
      <p className="muted small">{CBS_NOTE}</p>
      {frozen && frozenReason && (
        <p className="muted small">{frozenReason}</p>
      )}

      {showForm && (
        <form
          className="inline-form"
          style={{ boxShadow: "none", border: 0, padding: 0 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (!reason.trim()) {
              onError("Le motif est obligatoire.");
              return;
            }
            onError("");
            proposeMutation.mutate();
          }}
        >
          <div className="form-grid">
            <label className="field">
              <span>Nature</span>
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="CLIENT">Demande client</option>
                <option value="INTERNAL">Initiative interne</option>
              </select>
            </label>
            <label className="field">
              <span>Nouvelle durée (mois)</span>
              <input
                type="number"
                min={1}
                value={months}
                onChange={(e) => setMonths(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Nouveau taux % (optionnel)</span>
              <input
                type="number"
                step="0.001"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder={currentRate}
              />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>Motif</span>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Ex. mensualités trop lourdes après 6 échéances"
                required
              />
            </label>
          </div>
          {outstanding && (
            <p className="muted small">
              Capital restant dû (FinFlow) : {formatMoney(outstanding, currency)}
            </p>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={previewMutation.isPending}
              onClick={() => previewMutation.mutate()}
            >
              Prévisualiser
            </button>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={proposeMutation.isPending}
            >
              Soumettre la demande
            </button>
          </div>
          {preview && (
            <SchedulePreview preview={preview} currency={currency} />
          )}
        </form>
      )}

      {pending && (
        <div className="notice-info">
          <p>
            <strong>En attente de second regard</strong>
            {pending.requested_by_name ? ` — ${pending.requested_by_name}` : ""}
          </p>
          <p className="muted small">
            {(pending.request_kind_display || pending.request_kind || "") +
              " · "}
            {pending.new_duration_months} mois · taux {pending.new_rate}% ·{" "}
            {pending.reason}
          </p>
          <SchedulePreview
            preview={pending.proposed_schedule}
            currency={currency}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {canDecide && pending.requested_by !== currentUserId && (
              <>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={decideMutation.isPending}
                  onClick={() =>
                    decideMutation.mutate({ id: pending.id, action: "approve" })
                  }
                >
                  Approuver
                </button>
                {rejectId === pending.id ? (
                  <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <input
                      value={rejectComment}
                      onChange={(e) => setRejectComment(e.target.value)}
                      placeholder="Motif du rejet"
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={decideMutation.isPending || !rejectComment.trim()}
                      onClick={() =>
                        decideMutation.mutate({
                          id: pending.id,
                          action: "reject",
                          comment: rejectComment,
                        })
                      }
                    >
                      Confirmer le rejet
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setRejectId(pending.id)}
                  >
                    Rejeter
                  </button>
                )}
              </>
            )}
            {canPropose && pending.requested_by === currentUserId && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={decideMutation.isPending}
                onClick={() =>
                  decideMutation.mutate({ id: pending.id, action: "cancel" })
                }
              >
                Annuler la demande
              </button>
            )}
          </div>
        </div>
      )}

      {!!restructures.length && (
        <ul className="timeline-list">
          {restructures.map((r) => (
            <li key={r.id}>
              {statusBadge(r.status, r.status_display)}{" "}
              <strong>{r.effective_date}</strong>
              <span className="muted small">
                {" "}
                · {r.request_kind_display || r.request_kind} ·{" "}
                {r.new_duration_months} mois ·{" "}
                {formatMoney(r.outstanding_principal, currency)}
                {r.requested_by_name ? ` · ${r.requested_by_name}` : ""}
              </span>
              {r.reason && <p className="muted small">{r.reason}</p>}
              {r.decision_comment && (
                <p className="muted small">{r.decision_comment}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function WriteOffRequestPanel({
  caseId,
  currency,
  writeOffs,
  canPropose,
  canDecide,
  frozen,
  frozenReason,
  loanActive,
  currentUserId,
  onChanged,
  onError,
  onSuccess,
}: {
  caseId: string;
  currency: string;
  writeOffs: WriteOff[];
  canPropose: boolean;
  canDecide: boolean;
  frozen?: boolean;
  frozenReason?: string;
  loanActive: boolean;
  currentUserId?: string | null;
  onChanged: () => void;
  onError: (msg: string) => void;
  onSuccess: (msg: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const pending = writeOffs.find((w) => w.status === "PENDING");
  const showForm = canPropose && loanActive && !frozen && !pending;

  const proposeMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/collection-cases/${caseId}/write-off/`, { reason })
      ).data,
    onSuccess: () => {
      setReason("");
      onSuccess("Demande de passage en perte enregistrée — en attente de second regard.");
      onChanged();
    },
    onError: (e) =>
      onError(apiErrorMessage(e, "Impossible d'enregistrer la demande.")),
  });

  const decideMutation = useMutation({
    mutationFn: async ({
      id,
      action,
      comment,
    }: {
      id: string;
      action: "approve" | "reject" | "cancel";
      comment?: string;
    }) =>
      (
        await api.post(`/write-offs/${id}/${action}/`, {
          ...(comment ? { comment } : {}),
        })
      ).data,
    onSuccess: (_data, vars) => {
      setRejectId(null);
      setRejectComment("");
      onSuccess(
        vars.action === "approve"
          ? "Prêt passé en perte — dossier clôturé."
          : vars.action === "reject"
            ? "Demande rejetée."
            : "Demande annulée.",
      );
      onChanged();
    },
    onError: (e) =>
      onError(apiErrorMessage(e, "La décision n'a pas pu être enregistrée.")),
  });

  return (
    <div className="stack" style={{ gap: 12 }}>
      <p className="muted small">
        Le passage en perte clôture le dossier FinFlow (prêt en défaut). Le CBS
        n'est pas notifié : saisissez l'abandon dans Perfect si besoin.
      </p>
      {frozen && frozenReason && (
        <p className="muted small">{frozenReason}</p>
      )}

      {showForm && (
        <>
          <label className="field">
            <span>Motif</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Irrécouvrable / décision comité…"
              required
            />
          </label>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ marginTop: 8 }}
            disabled={proposeMutation.isPending || !reason.trim()}
            onClick={() => {
              onError("");
              proposeMutation.mutate();
            }}
          >
            Demander le passage en perte
          </button>
        </>
      )}

      {pending && (
        <div className="notice-info">
          <p>
            <strong>En attente de second regard</strong>
            {pending.requested_by_name ? ` — ${pending.requested_by_name}` : ""}
          </p>
          <p className="muted small">
            {formatMoney(pending.amount, currency)} — {pending.reason}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {canDecide && pending.requested_by !== currentUserId && (
              <>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={decideMutation.isPending}
                  onClick={() =>
                    decideMutation.mutate({ id: pending.id, action: "approve" })
                  }
                >
                  Approuver
                </button>
                {rejectId === pending.id ? (
                  <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <input
                      value={rejectComment}
                      onChange={(e) => setRejectComment(e.target.value)}
                      placeholder="Motif du rejet"
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={decideMutation.isPending || !rejectComment.trim()}
                      onClick={() =>
                        decideMutation.mutate({
                          id: pending.id,
                          action: "reject",
                          comment: rejectComment,
                        })
                      }
                    >
                      Confirmer le rejet
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setRejectId(pending.id)}
                  >
                    Rejeter
                  </button>
                )}
              </>
            )}
            {canPropose && pending.requested_by === currentUserId && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={decideMutation.isPending}
                onClick={() =>
                  decideMutation.mutate({ id: pending.id, action: "cancel" })
                }
              >
                Annuler la demande
              </button>
            )}
          </div>
        </div>
      )}

      {!!writeOffs.length && (
        <ul className="timeline-list">
          {writeOffs.map((w) => (
            <li key={w.id}>
              {statusBadge(w.status || "APPLIED", w.status_display)}{" "}
              <strong>
                {w.write_off_date} — {formatMoney(w.amount, currency)}
              </strong>
              {w.reason && <p className="muted small">{w.reason}</p>}
              {(w.requested_by_name || w.approved_by_name) && (
                <p className="muted small">
                  {[w.requested_by_name, w.approved_by_name]
                    .filter(Boolean)
                    .join(" → ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
