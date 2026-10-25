import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Search, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/api/client";
import type { Guarantee } from "@/api/types";
import { Badge, formatMoney } from "@/components/ui";

type Props = {
  applicationId: string;
  currency?: string;
  enabled?: boolean;
};

function dismissKey(applicationId: string) {
  return `finflow:renewal-dismissed:${applicationId}`;
}

function loadDismissed(applicationId: string): Set<string> {
  try {
    const raw = localStorage.getItem(dismissKey(applicationId));
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
  } catch {
    return new Set();
  }
}

function saveDismissed(applicationId: string, ids: Set<string>) {
  localStorage.setItem(
    dismissKey(applicationId),
    JSON.stringify([...ids]),
  );
}

/**
 * Proposition manuelle de reconduction (jamais automatique).
 * L’agent peut reconduire, reporter, puis revenir chercher plus tard.
 */
export function RenewGuaranteesPanel({
  applicationId,
  currency = "XAF",
  enabled = true,
}: Props) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [revaluatingId, setRevaluatingId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(() =>
    loadDismissed(applicationId),
  );
  /** Après un report, le panneau se replie ; « Rechercher » le rouvre. */
  const [panelOpen, setPanelOpen] = useState(true);
  const [valuation, setValuation] = useState({
    expertise_value: "",
    value_to_consider: "",
    expertise_date: "",
    expertise_firm: "",
    expert_name: "",
  });

  useEffect(() => {
    setDismissed(loadDismissed(applicationId));
    setPanelOpen(true);
    setRevaluatingId(null);
    setError(null);
  }, [applicationId]);

  const list = useQuery({
    queryKey: ["renewable-guarantees", applicationId],
    queryFn: async () =>
      (
        await api.get<{ results: Guarantee[] }>(
          `/credit-applications/${applicationId}/renewable-guarantees/`,
        )
      ).data,
    enabled: enabled && !!applicationId,
  });

  const renew = useMutation({
    mutationFn: async (payload: {
      source_guarantee: string;
      revaluate: boolean;
      valuation?: Record<string, string>;
    }) =>
      (
        await api.post(
          `/credit-applications/${applicationId}/renew-guarantee/`,
          payload,
        )
      ).data,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["guarantees", applicationId] });
      qc.invalidateQueries({
        queryKey: ["renewable-guarantees", applicationId],
      });
      setDismissed((prev) => {
        const next = new Set(prev);
        next.delete(vars.source_guarantee);
        saveDismissed(applicationId, next);
        return next;
      });
      setRevaluatingId(null);
      setError(null);
      setValuation({
        expertise_value: "",
        value_to_consider: "",
        expertise_date: "",
        expertise_firm: "",
        expert_name: "",
      });
    },
    onError: (err: unknown) => {
      const data = (err as { response?: { data?: unknown } })?.response?.data;
      const raw =
        data && typeof data === "object" && "errors" in data
          ? (data as { errors: unknown }).errors
          : data;
      setError(
        typeof raw === "string"
          ? raw
          : Array.isArray(raw)
            ? raw.map(String).join(" · ")
            : "Reconduction impossible.",
      );
    },
  });

  const dismissOne = useCallback(
    (guaranteeId: string) => {
      setDismissed((prev) => {
        const next = new Set(prev);
        next.add(guaranteeId);
        saveDismissed(applicationId, next);
        return next;
      });
      setRevaluatingId((cur) => (cur === guaranteeId ? null : cur));
      setError(null);
    },
    [applicationId],
  );

  const dismissAllVisible = useCallback(
    (ids: string[]) => {
      setDismissed((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.add(id));
        saveDismissed(applicationId, next);
        return next;
      });
      setRevaluatingId(null);
      setPanelOpen(false);
      setError(null);
    },
    [applicationId],
  );

  const reopenSearch = useCallback(() => {
    setDismissed(() => {
      const empty = new Set<string>();
      saveDismissed(applicationId, empty);
      return empty;
    });
    setPanelOpen(true);
    setError(null);
    void list.refetch();
  }, [applicationId, list]);

  const allItems = list.data?.results ?? [];
  const visibleItems = useMemo(
    () => allItems.filter((g) => !dismissed.has(g.id)),
    [allItems, dismissed],
  );
  const availableCount = allItems.length;
  const hasAvailable = availableCount > 0;

  if (!enabled) return null;

  if (list.isLoading) {
    return (
      <p className="muted small" style={{ marginBottom: 14 }}>
        Recherche de garanties reconductibles…
      </p>
    );
  }

  // Aucune garantie détectée : bouton pour relancer la recherche plus tard.
  if (!hasAvailable) {
    return (
      <div className="callout" style={{ marginBottom: 14 }}>
        <p className="muted small" style={{ margin: "0 0 8px" }}>
          Aucune garantie antérieure à reconduire pour ce client pour
          l’instant. La reconduction n’est jamais automatique.
        </p>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => void list.refetch()}
        >
          <Search size={14} />
          Rechercher des garanties à reconduire
        </button>
      </div>
    );
  }

  // Garanties disponibles mais reportées / panneau fermé.
  if (!panelOpen || visibleItems.length === 0) {
    return (
      <div className="callout" style={{ marginBottom: 14 }}>
        <p className="muted small" style={{ margin: "0 0 8px" }}>
          {availableCount} garantie{availableCount > 1 ? "s" : ""} encore
          disponible{availableCount > 1 ? "s" : ""} à reconduire si vous
          changez d’avis. Rien n’a été reconduit automatiquement.
        </p>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={reopenSearch}
        >
          <Search size={14} />
          Rechercher des garanties à reconduire
        </button>
      </div>
    );
  }

  return (
    <div className="callout callout-info" style={{ marginBottom: 14 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <RefreshCw size={16} />
          <strong>
            Garanties proposées à reconduire ({visibleItems.length})
          </strong>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={renew.isPending}
          onClick={() =>
            dismissAllVisible(visibleItems.map((g) => g.id))
          }
        >
          Ne pas reconduire pour l’instant
        </button>
      </div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Détection automatique uniquement : aucune garantie n’est
        reconduite sans votre action. Vous pouvez reconduire, reporter, ou
        revenir chercher plus tard.
      </p>
      {error && <div className="form-error">{error}</div>}
      <ul className="link-list">
        {visibleItems.map((g) => (
          <li
            key={g.id}
            style={{ flexDirection: "column", alignItems: "stretch" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                flexWrap: "wrap",
                width: "100%",
              }}
            >
              <span>
                <ShieldCheck size={14} /> {g.type_display}{" "}
                <code className="muted">
                  {g.reference || g.id.slice(0, 8)}
                </code>
                <span className="muted">
                  {" "}
                  · {formatMoney(g.current_value, currency)}
                </span>
              </span>
              <Badge value={g.status} />
            </div>
            <div className="row-actions" style={{ marginTop: 8 }}>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={renew.isPending}
                onClick={() =>
                  renew.mutate({
                    source_guarantee: g.id,
                    revaluate: false,
                  })
                }
              >
                Reconduire tel quel
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={renew.isPending}
                onClick={() => {
                  setRevaluatingId(
                    revaluatingId === g.id ? null : g.id,
                  );
                  setValuation({
                    expertise_value: g.expertise_value || "",
                    value_to_consider: g.value_to_consider || "",
                    expertise_date: g.expertise_date || "",
                    expertise_firm: g.expertise_firm || "",
                    expert_name: g.expert_name || "",
                  });
                }}
              >
                Reconduire avec réévaluation
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={renew.isPending}
                onClick={() => dismissOne(g.id)}
              >
                Ne pas reconduire
              </button>
            </div>
            {revaluatingId === g.id && (
              <div className="form-grid" style={{ marginTop: 10 }}>
                <label className="field">
                  <span>Valeur d’expertise</span>
                  <input
                    type="number"
                    value={valuation.expertise_value}
                    onChange={(e) =>
                      setValuation({
                        ...valuation,
                        expertise_value: e.target.value,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Valeur à considérer</span>
                  <input
                    type="number"
                    value={valuation.value_to_consider}
                    onChange={(e) =>
                      setValuation({
                        ...valuation,
                        value_to_consider: e.target.value,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Date d’expertise</span>
                  <input
                    type="date"
                    value={valuation.expertise_date || ""}
                    onChange={(e) =>
                      setValuation({
                        ...valuation,
                        expertise_date: e.target.value,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Cabinet</span>
                  <input
                    value={valuation.expertise_firm}
                    onChange={(e) =>
                      setValuation({
                        ...valuation,
                        expertise_firm: e.target.value,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Expert</span>
                  <input
                    value={valuation.expert_name}
                    onChange={(e) =>
                      setValuation({
                        ...valuation,
                        expert_name: e.target.value,
                      })
                    }
                  />
                </label>
                <div
                  className="row-actions"
                  style={{ gridColumn: "1 / -1" }}
                >
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={renew.isPending}
                    onClick={() =>
                      renew.mutate({
                        source_guarantee: g.id,
                        revaluate: true,
                        valuation,
                      })
                    }
                  >
                    Valider la reconduction
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={renew.isPending}
                    onClick={() => setRevaluatingId(null)}
                  >
                    Annuler
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
