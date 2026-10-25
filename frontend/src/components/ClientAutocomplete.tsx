import { useQuery } from "@tanstack/react-query";
import { Check, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/client";
import type { Client, Paginated } from "@/api/types";

/** Libellé d'affichage : matricule CBS + nom (ou référence si pas de CBS). */
export function clientOptionLabel(c: Pick<
  Client,
  | "cbs_client_id"
  | "reference"
  | "display_name"
  | "client_type"
  | "company_name"
  | "first_name"
  | "last_name"
>): string {
  const matricule = (c.cbs_client_id || "").trim() || (c.reference || "").trim() || "—";
  const name =
    (c.display_name || "").trim() ||
    (c.client_type === "CORPORATE" || c.client_type === "PROFESSIONAL"
      ? (c.company_name || "").trim()
      : `${c.last_name || ""} ${c.first_name || ""}`.trim()) ||
    "Client";
  return `${matricule} — ${name}`;
}

/**
 * Champ de saisie avec suggestions de clients.
 * Affiche « matricule CBS + nom » (particulier) ou
 * « matricule CBS + dénomination » (entreprise / groupement).
 */
export function ClientAutocomplete({
  value,
  onChange,
  initialLabel,
  required,
}: {
  value: string;
  onChange: (id: string, label: string, client?: Client | null) => void;
  initialLabel?: string;
  required?: boolean;
}) {
  const [query, setQuery] = useState(initialLabel ?? "");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<boolean>(Boolean(value));
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (initialLabel) {
      setQuery(initialLabel);
      setSelected(Boolean(value));
    }
  }, [initialLabel, value]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const { data, isFetching } = useQuery({
    queryKey: ["clients-search", debounced],
    queryFn: async () =>
      (
        await api.get<Paginated<Client>>("/clients/", {
          params: { search: debounced, page_size: 8 },
        })
      ).data,
    enabled: open && debounced.length >= 1 && !selected,
  });

  function pick(c: Client) {
    const label = clientOptionLabel(c);
    setQuery(label);
    setSelected(true);
    setOpen(false);
    onChange(c.id, label, c);
  }

  function clear() {
    setQuery("");
    setSelected(false);
    onChange("", "", null);
  }

  return (
    <div className="client-ac" ref={ref}>
      <div className={`ac-input${selected ? " picked" : ""}`}>
        {selected ? <Check size={16} /> : <Search size={16} />}
        <input
          value={query}
          required={required && !value}
          aria-required={required || undefined}
          placeholder="Matricule Core Banking, nom, dénomination ou référence…"
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(false);
            setOpen(true);
            if (value) onChange("", "", null);
          }}
          onFocus={() => !selected && setOpen(true)}
          autoComplete="off"
        />
        {query && (
          <button
            type="button"
            className="ac-clear"
            onClick={clear}
            aria-label="Effacer"
          >
            <X size={15} />
          </button>
        )}
      </div>
      {open && !selected && debounced.length >= 1 && (
        <div className="ac-panel">
          {isFetching && <div className="ac-empty">Recherche…</div>}
          {!isFetching && (data?.results.length ?? 0) === 0 && (
            <div className="ac-empty">Aucun client trouvé.</div>
          )}
          {data?.results.map((c) => (
            <button
              type="button"
              key={c.id}
              className="ac-item"
              onClick={() => pick(c)}
            >
              <span className="ac-ref">
                {(c.cbs_client_id || "").trim() || "Sans matricule CBS"}
              </span>
              <span className="ac-name">
                {(c.display_name || "").trim() ||
                  (c.client_type === "CORPORATE" ||
                  c.client_type === "PROFESSIONAL"
                    ? c.company_name
                    : `${c.last_name || ""} ${c.first_name || ""}`.trim()) ||
                  c.reference ||
                  "—"}
              </span>
              <span className="ac-type">
                {c.client_type === "CORPORATE"
                  ? "Entreprise"
                  : c.client_type === "PROFESSIONAL"
                    ? "Groupement"
                    : "Particulier"}
                {c.reference ? ` · ${c.reference}` : ""}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
