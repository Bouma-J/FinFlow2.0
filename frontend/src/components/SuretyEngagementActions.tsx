import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSignature, FileUp, PhoneCall, Unlock } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import type { ContractTemplate, SuretyEngagement } from "@/api/types";
import { Badge, formatDate, formatMoney } from "@/components/ui";

function errMsg(err: unknown, fallback: string) {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    const parts = Object.values(data as Record<string, unknown>)
      .flatMap((v) => (Array.isArray(v) ? v : [v]))
      .map(String)
      .filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  return fallback;
}

export function SuretyEngagementActions({
  engagement,
  canManage,
  canContracts,
  currency,
  invalidateKeys = [],
}: {
  engagement: SuretyEngagement;
  canManage: boolean;
  canContracts: boolean;
  currency?: string;
  invalidateKeys?: unknown[][];
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [signedFile, setSignedFile] = useState<File | null>(null);
  const [templateId, setTemplateId] = useState("");

  function invalidate() {
    for (const key of invalidateKeys) {
      qc.invalidateQueries({ queryKey: key });
    }
    qc.invalidateQueries({ queryKey: ["surety"] });
    qc.invalidateQueries({ queryKey: ["surety-engagements"] });
    qc.invalidateQueries({ queryKey: ["sureties"] });
    qc.invalidateQueries({ queryKey: ["credit-readiness"] });
    qc.invalidateQueries({ queryKey: ["generated-contracts"] });
  }

  const templates = useQuery({
    queryKey: ["surety-engagement-templates", engagement.id],
    queryFn: async () =>
      (
        await api.get<ContractTemplate[]>(
          `/surety-engagements/${engagement.id}/contract_templates/`,
        )
      ).data,
    enabled: canContracts && !engagement.contract_id,
  });

  const releaseMut = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/surety-engagements/${engagement.id}/release/`, {
          comment: "Libération",
        })
      ).data,
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e) => setError(errMsg(e, "Libération impossible.")),
  });

  const callMut = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/surety-engagements/${engagement.id}/call/`, {
          comment: "Appel en garantie",
        })
      ).data,
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e) => setError(errMsg(e, "Appel impossible.")),
  });

  const generateMut = useMutation({
    mutationFn: async () => {
      const res = await api.post(
        `/surety-engagements/${engagement.id}/generate_contract/`,
        templateId ? { template: templateId } : {},
        { validateStatus: (s) => s === 200 || s === 201 || s === 202 },
      );
      return { status: res.status, data: res.data as Record<string, unknown> };
    },
    onSuccess: async (payload) => {
      setError(null);
      invalidate();
      const taskId =
        typeof payload.data?.task_id === "string"
          ? payload.data.task_id
          : null;
      if (
        (payload.status === 202 || payload.data?.status === "queued") &&
        taskId
      ) {
        try {
          const { pollAsyncTask } = await import("@/utils/pollAsyncTask");
          await pollAsyncTask(taskId, { onTick: invalidate, maxAttempts: 30 });
          invalidate();
        } catch (e) {
          setError(
            e instanceof Error
              ? e.message
              : "Génération du contrat impossible.",
          );
        }
      }
    },
    onError: (e) =>
      setError(errMsg(e, "Génération du contrat impossible.")),
  });

  const uploadMut = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (signedFile) fd.append("signed_file", signedFile);
      return (
        await api.post(
          `/surety-engagements/${engagement.id}/upload_signed/`,
          fd,
          { headers: { "Content-Type": "multipart/form-data" } },
        )
      ).data;
    },
    onSuccess: () => {
      setSignedFile(null);
      setError(null);
      invalidate();
    },
    onError: (e) => setError(errMsg(e, "Dépôt du scan impossible.")),
  });

  const active = engagement.status === "ACTIVE";
  const called = engagement.status === "CALLED";

  return (
    <div className="surety-engagement-actions">
      <div className="row-actions" style={{ flexWrap: "wrap", gap: 8 }}>
        {engagement.engagement_type_display && (
          <Badge
            value={engagement.engagement_type || "SOLIDAIRE"}
            label={engagement.engagement_type_display}
          />
        )}
        <Badge
          value={engagement.status}
          label={engagement.status_display || engagement.status}
        />
        <span className="num">{formatMoney(engagement.amount, currency)}</span>
        {engagement.signed_date && (
          <span className="muted small">
            Signé le {formatDate(engagement.signed_date)}
          </span>
        )}
      </div>

      {(engagement.contract_id || canContracts) && (
        <div style={{ marginTop: 10 }}>
          <p className="muted small" style={{ marginBottom: 6 }}>
            Contrat de cautionnement
            {engagement.contract_template_name
              ? ` — ${engagement.contract_template_name}`
              : ""}
            {engagement.contract_status_display
              ? ` · ${engagement.contract_status_display}`
              : ""}
          </p>
          <div className="row-actions" style={{ flexWrap: "wrap", gap: 8 }}>
            {engagement.contract_file_url && (
              <a
                className="btn btn-ghost btn-sm"
                href={engagement.contract_file_url}
                target="_blank"
                rel="noreferrer"
              >
                <FileSignature size={14} />
                Télécharger
              </a>
            )}
            {engagement.contract_signed_file_url && (
              <a
                className="btn btn-ghost btn-sm"
                href={engagement.contract_signed_file_url}
                target="_blank"
                rel="noreferrer"
              >
                Scan signé
              </a>
            )}
            {canContracts && !engagement.contract_id && (
              <>
                {(templates.data?.length ?? 0) > 1 && (
                  <select
                    value={templateId}
                    onChange={(e) => setTemplateId(e.target.value)}
                  >
                    <option value="">Modèle par défaut</option>
                    {templates.data?.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={generateMut.isPending}
                  onClick={() => generateMut.mutate()}
                >
                  <FileSignature size={14} />
                  Générer le contrat
                </button>
              </>
            )}
            {canContracts && engagement.contract_id && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={generateMut.isPending}
                onClick={() => generateMut.mutate()}
              >
                Régénérer
              </button>
            )}
          </div>
          {canContracts &&
            engagement.contract_id &&
            engagement.contract_status !== "SIGNED" && (
              <div className="form-grid" style={{ marginTop: 10 }}>
                <label className="field">
                  <span>Scan signé</span>
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={(e) =>
                      setSignedFile(e.target.files?.[0] ?? null)
                    }
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!signedFile || uploadMut.isPending}
                  onClick={() => uploadMut.mutate()}
                >
                  <FileUp size={14} />
                  Déposer le signé
                </button>
              </div>
            )}
        </div>
      )}

      {canManage && (active || called) && (
        <div className="row-actions" style={{ marginTop: 10, gap: 8 }}>
          {active && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={callMut.isPending}
              onClick={() => {
                if (
                  !window.confirm(
                    "Marquer cet engagement comme appelé en garantie ?",
                  )
                ) {
                  return;
                }
                callMut.mutate();
              }}
            >
              <PhoneCall size={14} />
              Appeler
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={releaseMut.isPending}
            onClick={() => {
              if (
                !window.confirm(
                  "Libérer cet engagement ? Le plafond disponible sera recalculé.",
                )
              ) {
                return;
              }
              releaseMut.mutate();
            }}
          >
            <Unlock size={14} />
            Libérer
          </button>
        </div>
      )}

      {error && (
        <div className="form-error" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}
    </div>
  );
}
