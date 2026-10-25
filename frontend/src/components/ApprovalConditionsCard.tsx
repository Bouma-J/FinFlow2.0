import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, ClipboardCheck } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import type { ApprovalCondition } from "@/api/types";
import { WORKFLOW_LABELS } from "@/api/types";
import { Badge } from "@/components/ui";

export function ApprovalConditionsCard({
  conditions,
  appId,
}: {
  conditions: ApprovalCondition[];
  appId: string;
}) {
  const qc = useQueryClient();
  const [liftComment, setLiftComment] = useState<Record<string, string>>({});
  const [validateComment, setValidateComment] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const lift = useMutation({
    mutationFn: async ({ id, comment }: { id: string; comment: string }) =>
      (await api.post(`/approval-conditions/${id}/lift/`, { comment })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval-conditions", appId] });
      qc.invalidateQueries({ queryKey: ["credit-application", appId] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      setError(null);
    },
    onError: () => setError("Impossible de marquer la réserve comme levée."),
  });

  const validate = useMutation({
    mutationFn: async ({ id, comment }: { id: string; comment: string }) =>
      (await api.post(`/approval-conditions/${id}/validate/`, { comment })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval-conditions", appId] });
      qc.invalidateQueries({ queryKey: ["credit-application", appId] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      setError(null);
    },
    onError: () => setError("Impossible de valider la levée de la réserve."),
  });

  const returnLift = useMutation({
    mutationFn: async ({ id, comment }: { id: string; comment: string }) =>
      (await api.post(`/approval-conditions/${id}/return_lift/`, { comment }))
        .data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval-conditions", appId] });
      qc.invalidateQueries({ queryKey: ["credit-application", appId] });
      qc.invalidateQueries({ queryKey: ["workflow-instances"] });
      setError(null);
    },
    onError: () =>
      setError("Impossible de renvoyer la levée au chargé de dossier."),
  });

  if (conditions.length === 0) return null;

  const pending = conditions.filter((c) => c.status !== "VALIDATED").length;

  return (
    <div className="conditions-card">
      {pending > 0 && (
        <p className="conditions-alert">
          <ClipboardCheck size={16} />
          {pending} réserve{pending > 1 ? "s" : ""} en cours — le dossier reste en
          validation jusqu'à levée et confirmation par l'émetteur.
        </p>
      )}
      {error && <div className="form-error">{error}</div>}
      <ul className="conditions-list">
        {conditions.map((c) => (
          <li key={c.id} className={`condition-row status-${c.status.toLowerCase()}`}>
            <div className="condition-head">
              <strong>{c.description}</strong>
              <Badge
                value={c.status === "VALIDATED" ? "success" : "warning"}
                label={
                  WORKFLOW_LABELS.condition_status[c.status] || c.status
                }
              />
            </div>
            <p className="muted small">
              Étape : {c.step_name} · Émis par {c.issued_by_display} le{" "}
              {new Date(c.issued_at).toLocaleDateString("fr-FR")}
            </p>
            {c.lifted_by_display && (
              <p className="muted small">
                Levée par {c.lifted_by_display}
                {c.lift_comment && ` — « ${c.lift_comment} »`}
              </p>
            )}
            {c.validated_by_display && (
              <p className="muted small">
                <CheckCircle size={12} /> Validée par {c.validated_by_display}
                {c.validation_comment && ` — « ${c.validation_comment} »`}
              </p>
            )}
            {c.status === "PENDING" && !c.validated_by_display &&
              c.validation_comment && (
                <p className="muted small">
                  Retour de l'émetteur — « {c.validation_comment} »
                </p>
              )}
            {c.can_lift && (
              <div className="condition-action">
                <input
                  placeholder="Commentaire de levée…"
                  value={liftComment[c.id] ?? ""}
                  onChange={(e) =>
                    setLiftComment({ ...liftComment, [c.id]: e.target.value })
                  }
                />
                <button
                  className="btn btn-primary btn-sm"
                  disabled={lift.isPending}
                  onClick={() =>
                    lift.mutate({ id: c.id, comment: liftComment[c.id] ?? "" })
                  }
                >
                  Marquer comme levée
                </button>
              </div>
            )}
            {c.can_validate && (
              <div className="condition-action">
                <input
                  placeholder="Commentaire (validation ou demande de complément)…"
                  value={validateComment[c.id] ?? ""}
                  onChange={(e) =>
                    setValidateComment({ ...validateComment, [c.id]: e.target.value })
                  }
                />
                <button
                  className="btn btn-success btn-sm"
                  disabled={validate.isPending}
                  onClick={() =>
                    validate.mutate({
                      id: c.id,
                      comment: validateComment[c.id] ?? "",
                    })
                  }
                >
                  Confirmer la levée
                </button>
                <button
                  className="btn btn-warning btn-sm"
                  disabled={returnLift.isPending}
                  onClick={() =>
                    returnLift.mutate({
                      id: c.id,
                      comment: validateComment[c.id] ?? "",
                    })
                  }
                  title="Renvoyer au chargé de dossier pour complément"
                >
                  Renvoyer pour complément
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
