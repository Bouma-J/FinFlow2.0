import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { GedDocument } from "@/api/types";
import { apiErrorMessage } from "@/utils/apiError";

export function DocumentVerification({ document, canVerify }: { document: GedDocument; canVerify: boolean }) {
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const change = useMutation({ mutationFn: (status: string) => api.post(`/documents/${document.id}/verify/`, { status, comment }),
    onSuccess: () => { setError(""); qc.invalidateQueries({ queryKey: ["ged-documents"] }); qc.invalidateQueries({ queryKey: ["setup-review"] }); },
    onError: (cause) => setError(apiErrorMessage(cause, "Vérification impossible.")) });
  return <div className="stack">
    <span>{({ VERIFIED: "Vérifié", REJECTED: "Rejeté", PENDING: "À vérifier" } as Record<string, string>)[document.verification_status || "PENDING"]}</span>
    {document.verification_comment && <span className="muted small">{document.verification_comment}</span>}
    {canVerify && <><input aria-label="Commentaire de vérification" placeholder="Contrôles / motif" value={comment} onChange={(event) => setComment(event.target.value)} />
      <div className="doc-row"><button type="button" className="btn btn-ghost btn-sm" disabled={change.isPending || !comment.trim()} onClick={() => change.mutate("VERIFIED")}>Vérifier</button><button type="button" className="btn btn-ghost btn-sm" disabled={change.isPending || !comment.trim()} onClick={() => change.mutate("REJECTED")}>Rejeter</button></div></>}
    {error && <span className="form-error">{error}</span>}
  </div>;
}
