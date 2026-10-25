import { useQuery } from "@tanstack/react-query";
import { Check, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/client";
import type { Paginated, Surety } from "@/api/types";

export function SuretyAutocomplete({
  value,
  onChange,
  initialLabel = "",
}: {
  value: string;
  onChange: (id: string, label: string, surety?: Surety) => void;
  /** Libellé affiché si une caution est déjà sélectionnée (édition). */
  initialLabel?: string;
}) {
  const [query, setQuery] = useState(initialLabel || "");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(Boolean(value));
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (value && initialLabel) {
      setQuery(initialLabel);
      setSelected(true);
    }
  }, [value, initialLabel]);

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
    queryKey: ["sureties-search", debounced],
    queryFn: async () =>
      (
        await api.get<Paginated<Surety>>("/sureties/", {
          params: { search: debounced, page_size: 8 },
        })
      ).data,
    enabled: open && debounced.length >= 1 && !selected,
  });

  function pick(s: Surety) {
    setQuery(s.display_name);
    setSelected(true);
    setOpen(false);
    onChange(s.id, s.display_name, s);
  }

  function clear() {
    setQuery("");
    setSelected(false);
    onChange("", "");
  }

  return (
    <div className="client-ac" ref={ref}>
      <div className={`ac-input${selected ? " picked" : ""}`}>
        {selected ? <Check size={16} /> : <Search size={16} />}
        <input
          value={query}
          placeholder="Rechercher une caution existante…"
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(false);
            setOpen(true);
            if (value) onChange("", "");
          }}
          onFocus={() => !selected && setOpen(true)}
        />
        {query && (
          <button type="button" className="ac-clear" onClick={clear} aria-label="Effacer">
            <X size={15} />
          </button>
        )}
      </div>
      {open && !selected && debounced.length >= 1 && (
        <div className="ac-panel">
          {isFetching && <div className="ac-empty">Recherche…</div>}
          {!isFetching && (data?.results.length ?? 0) === 0 && (
            <div className="ac-empty">Aucune caution trouvée.</div>
          )}
          {data?.results.map((s) => (
            <button type="button" key={s.id} className="ac-item" onClick={() => pick(s)}>
              <span className="ac-name">{s.display_name}</span>
              <span className="ac-type">{s.activity || "Caution"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
