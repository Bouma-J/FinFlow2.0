import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Undo2, X } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import type { ApprovalTask, Paginated, RejectReason } from "@/api/types";
import { WORKFLOW_LABELS } from "@/api/types";
import { formatMoney } from "@/components/ui";
import { useAuth } from "@/auth/AuthContext";

type Decision = "APPROVED" | "REJECTED" | "RETURNED";
type Opinion = "FAVORABLE" | "FAVORABLE_SOUS_RESERVE" | "DEFAVORABLE";

const CREDIT_OPINIONS: { value: Opinion; label: string }[] = [
  { value: "FAVORABLE", label: WORKFLOW_LABELS.opinion.FAVORABLE },
  {
    value: "FAVORABLE_SOUS_RESERVE",
    label: WORKFLOW_LABELS.opinion.FAVORABLE_SOUS_RESERVE,
  },
  { value: "DEFAVORABLE", label: WORKFLOW_LABELS.opinion.DEFAVORABLE },
];

const PROCESS_OPINIONS: { value: Opinion; label: string }[] = [
  { value: "FAVORABLE", label: WORKFLOW_LABELS.opinion.FAVORABLE },
  { value: "DEFAVORABLE", label: WORKFLOW_LABELS.opinion.DEFAVORABLE },
];

/**
 * Panneau de décision : avis structuré, réserves, montant proposé,
 * motif de rejet et actions (valider / renvoyer / rejeter).
 */
export function DecisionPanel({
  task,
  onDone,
}: {
  task: ApprovalTask;
  onDone?: () => void;
}) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [participants, setParticipants] = useState<{ user: string; vote: string; conflict: boolean }[]>([]);
  const colleagues = useQuery({ queryKey: ["committee-participants", task.id], enabled: Boolean(task.is_committee), queryFn: async () => (await api.get<{ id: string; display_name: string }[]>(`/approval-tasks/${task.id}/committee_participants/`)).data });
  const [comment, setComment] = useState("");
  const [amount, setAmount] = useState("");
  const [opinion, setOpinion] = useState<Opinion | "">("");
  const [reservesText, setReservesText] = useState("");
  const [rejectReasonId, setRejectReasonId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isDecisional = task.step_kind === "DECISIONAL";
  const isCredit =
    task.target_meta?.kind === "CREDIT" || Boolean(task.application);
  const opinions = isCredit ? CREDIT_OPINIONS : PROCESS_OPINIONS;

  const { data: rejectReasons } = useQuery({
    queryKey: ["reject-reasons"],
    queryFn: async () =>
      (await api.get<Paginated<RejectReason>>("/reject-reasons/")).data,
  });

  const appli = isCredit ? task.application : undefined;
  const cur = appli?.currency ?? "XOF";
  const currentProposed = appli?.amount_proposed ?? appli?.amount_requested ?? "";

  const decide = useMutation({
    mutationFn: async ({
      decision,
      returnToSubmitter = false,
    }: {
      decision: Decision;
      returnToSubmitter?: boolean;
    }) => {
      const payload: Record<string, unknown> = { decision, comment };
      if (task.is_committee && participants.length) payload.committee_record = { participants };
      if (opinion) payload.opinion = opinion;
      if (isCredit && decision === "APPROVED" && amount) {
        payload.proposed_amount = amount;
      }
      if (decision === "REJECTED" && rejectReasonId) {
        payload.reject_reason = rejectReasonId;
      }
      if (decision === "RETURNED" && returnToSubmitter) {
        payload.return_to_submitter = true;
      }
      if (isCredit && opinion === "FAVORABLE_SOUS_RESERVE") {
        payload.reserves = reservesText
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean);
      }
      return (await api.post(`/approval-tasks/${task.id}/decide/`, payload)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-pending-tasks"] });
      qc.invalidateQueries({ queryKey: ["my-dossiers"] });
      qc.invalidateQueries({ queryKey: ["credit-applications"] });
      qc.invalidateQueries({ queryKey: ["credit-application"] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      qc.invalidateQueries({ queryKey: ["approval-conditions"] });
      qc.invalidateQueries({ queryKey: ["guarantee-releases"] });
      qc.invalidateQueries({ queryKey: ["guarantee-release"] });
      qc.invalidateQueries({ queryKey: ["dation-requests"] });
      qc.invalidateQueries({ queryKey: ["dation-request"] });
      qc.invalidateQueries({ queryKey: ["guarantees"] });
      onDone?.();
    },
    onError: (e: unknown) => {
      const data = (e as { response?: { data?: unknown } })?.response?.data;
      const raw =
        data && typeof data === "object" && "errors" in data
          ? (data as { errors: unknown }).errors
          : data;
      let msg = "Décision impossible. Réessayez.";
      if (typeof raw === "string") msg = raw;
      else if (Array.isArray(raw)) msg = raw.map(String).join(" · ");
      else if (raw && typeof raw === "object") {
        msg = Object.values(raw as Record<string, unknown>)
          .map((v) => (Array.isArray(v) ? v.join(", ") : String(v)))
          .join(" · ");
      }
      setError(msg);
    },
  });

  function act(decision: Decision, returnToSubmitter = false) {
    setError(null);
    if (task.is_committee && decision !== "RETURNED" && task.committee_record_required && !participants.length) {
      setError("Renseignez les participants et les votes du comité.");
      return;
    }

    if (decision === "APPROVED") {
      if (!opinion) {
        setError("Veuillez sélectionner un avis.");
        return;
      }
      if (
        isCredit &&
        opinion === "FAVORABLE_SOUS_RESERVE" &&
        !reservesText.trim()
      ) {
        setError("Les réserves sont obligatoires pour un avis favorable sous réserve.");
        return;
      }
      if (opinion === "DEFAVORABLE" && isDecisional) {
        setError(
          "Un avis défavorable à une étape décisionnelle doit conduire à un rejet ou un renvoi."
        );
        return;
      }
    }

    if (decision === "REJECTED") {
      if (!comment.trim()) {
        setError("Un commentaire détaillé est requis pour rejeter le dossier.");
        return;
      }
      if (!rejectReasonId) {
        setError("Veuillez sélectionner un motif de rejet.");
        return;
      }
    }

    if (decision === "RETURNED" && !comment.trim()) {
      setError("Merci d'indiquer un commentaire expliquant le retour.");
      return;
    }

    decide.mutate({ decision, returnToSubmitter });
  }

  return (
    <div className="decision-panel">
      {task.is_committee && <div className="stack">
        <p className="subsection-label">Comité : quorum {task.committee_quorum ?? 1} hors conflits d'intérêts</p>
        <p className="muted small">Retranscrire les présences et votes du comité.{isCredit && task.committee_pv_required !== false ? " Le PV doit être déposé au dossier avant validation." : ""}</p>
        <p className="muted small">{task.committee_majority === "QUALIFIED" ? `Majorité qualifiée : au moins ${task.committee_majority_numerator}/${task.committee_majority_denominator}` : task.committee_majority === "UNANIMOUS" ? "Unanimité" : "Majorité stricte : plus de la moitié"} · Abstentions {task.committee_abstentions === "EXCLUDE" ? "exclues" : "incluses"} dans la base de calcul. Les personnes en conflit ne comptent ni dans le quorum ni dans la majorité.</p>
        {participants.map((participant, index) => <div className="form-grid two-col" key={index}>
          <label className="field"><span>Participant</span><select value={participant.user} onChange={(event) => setParticipants(participants.map((row, i) => i === index ? { ...row, user: event.target.value } : row))}><option value="">Choisir</option>{colleagues.data?.map((person) => <option key={person.id} value={person.id}>{person.display_name}{person.id === user?.id ? " (vous)" : ""}</option>)}</select></label>
          <label className="field"><span>Vote</span><select value={participant.vote} onChange={(event) => setParticipants(participants.map((row, i) => i === index ? { ...row, vote: event.target.value } : row))}><option value="FOR">Pour</option><option value="AGAINST">Contre</option><option value="ABSTAIN">Abstention</option></select></label>
          <label className="checkbox"><input type="checkbox" checked={participant.conflict} onChange={(event) => setParticipants(participants.map((row, i) => i === index ? { ...row, conflict: event.target.checked, vote: event.target.checked ? "ABSTAIN" : row.vote } : row))} /><span>Conflit d'intérêts déclaré</span></label>
          <button type="button" className="btn btn-ghost" onClick={() => setParticipants(participants.filter((_, i) => i !== index))}>Retirer</button>
        </div>)}
        <button type="button" className="btn btn-ghost" onClick={() => setParticipants([...participants, { user: "", vote: "FOR", conflict: false }])}>Ajouter un participant</button>
        {colleagues.isError && <p className="form-error">Chargement des participants habilités impossible. <button type="button" className="btn btn-ghost btn-sm" onClick={() => colleagues.refetch()}>Réessayer</button></p>}
      </div>}
      {appli && (
        <div className="task-amounts">
          <span>
            Demandé : <strong>{formatMoney(appli.amount_requested, cur)}</strong>
          </span>
          <span>
            Proposé (étape préc.) :{" "}
            <strong>
              {appli.amount_proposed
                ? formatMoney(appli.amount_proposed, cur)
                : "—"}
            </strong>
          </span>
        </div>
      )}

      <fieldset className="opinion-fieldset">
        <legend>Avis *</legend>
        <div className="opinion-radios">
          {opinions.map((o) => (
            <label key={o.value} className="opinion-radio">
              <input
                type="radio"
                name={`opinion-${task.id}`}
                value={o.value}
                checked={opinion === o.value}
                onChange={() => setOpinion(o.value)}
              />
              <span>{o.label}</span>
            </label>
          ))}
        </div>
        {opinion === "DEFAVORABLE" && !isDecisional && (
          <p className="muted small">
            Étape consultative : vous pouvez transmettre malgré un avis défavorable.
          </p>
        )}
        {opinion === "DEFAVORABLE" && isDecisional && (
          <p className="form-error small">
            Étape décisionnelle : utilisez « Rejeter » ou « Renvoyer », pas « Valider ».
          </p>
        )}
      </fieldset>

      {isCredit && opinion === "FAVORABLE_SOUS_RESERVE" && (
        <label className="field">
          <span>Réserves / conditions * (une par ligne)</span>
          <textarea
            rows={3}
            placeholder="Ex. Fournir garantie complémentaire&#10;Domicilier le salaire"
            value={reservesText}
            onChange={(e) => setReservesText(e.target.value)}
          />
        </label>
      )}

      <div className="form-grid two-col">
        {isCredit ? (
          <label className="field">
            <span>Montant proposé (en cas de validation)</span>
            <input
              type="number"
              min={0}
              placeholder={String(currentProposed)}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
        ) : (
          <div />
        )}
        <label className="field">
          <span>Motif de rejet (si rejet)</span>
          <select
            value={rejectReasonId}
            onChange={(e) => setRejectReasonId(e.target.value)}
          >
            <option value="">— choisir —</option>
            {rejectReasons?.results.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <textarea
        className="task-comment"
        placeholder="Commentaire (motivation de la décision)…"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />

      {error && <div className="form-error">{error}</div>}

      <div className="task-actions">
        <button
          className="btn btn-success btn-sm"
          disabled={decide.isPending || (opinion === "DEFAVORABLE" && isDecisional)}
          onClick={() => act("APPROVED")}
        >
          <Check />
          Valider et transmettre
        </button>
        {task.allow_return && (
          <button
            className="btn btn-warning btn-sm"
            disabled={decide.isPending}
            onClick={() => act("RETURNED")}
          >
            <Undo2 />
            Retourner à l'étape précédente
          </button>
        )}
        {task.allow_return && (
          <button
            className="btn btn-warning btn-sm"
            disabled={decide.isPending}
            onClick={() => act("RETURNED", true)}
            title="Renvoyer directement au soumissionnaire pour correction"
          >
            <Undo2 />
            Renvoyer au soumissionnaire
          </button>
        )}
        <button
          className="btn btn-danger btn-sm"
          disabled={decide.isPending}
          onClick={() => act("REJECTED")}
        >
          <X />
          Rejeter
        </button>
      </div>
    </div>
  );
}
