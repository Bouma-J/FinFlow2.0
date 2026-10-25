import { ExternalLink, FileText, Plus, Trash2 } from "lucide-react";

export interface ExistingFreeDocument {
  id: string;
  title: string;
  file: string | null;
}

export interface FreeDocumentDraft {
  title: string;
  file: File | null;
}

/** Lignes dynamiques intitulé + scan, avec suppression des documents existants. */
export function FreeDocumentsEditor({
  existing,
  drafts,
  onDraftsChange,
  deletedIds,
  onDeletedIdsChange,
}: {
  existing?: ExistingFreeDocument[];
  drafts: FreeDocumentDraft[];
  onDraftsChange: (next: FreeDocumentDraft[]) => void;
  deletedIds: string[];
  onDeletedIdsChange: (next: string[]) => void;
}) {
  const visibleExisting = (existing ?? []).filter(
    (d) => !deletedIds.includes(d.id),
  );

  function updateDraft(idx: number, patch: Partial<FreeDocumentDraft>) {
    onDraftsChange(
      drafts.map((row, i) => (i === idx ? { ...row, ...patch } : row)),
    );
  }

  function removeDraft(idx: number) {
    onDraftsChange(drafts.filter((_, i) => i !== idx));
  }

  function addDraft() {
    onDraftsChange([...drafts, { title: "", file: null }]);
  }

  function markDeleted(id: string) {
    onDeletedIdsChange([...deletedIds, id]);
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      {visibleExisting.length > 0 && (
        <ul className="link-list" style={{ margin: 0 }}>
          {visibleExisting.map((doc) => (
            <li key={doc.id} style={{ alignItems: "center" }}>
              <span>
                <FileText size={14} /> {doc.title || "Document"}
                {doc.file && (
                  <>
                    {" "}
                    <a
                      href={doc.file}
                      target="_blank"
                      rel="noreferrer"
                      className="muted small"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink size={12} style={{ verticalAlign: "-1px" }} />{" "}
                      Voir
                    </a>
                  </>
                )}
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => markDeleted(doc.id)}
                title="Supprimer ce document"
                aria-label="Supprimer ce document"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {drafts.map((row, idx) => (
        <div key={idx} className="jewelry-item-row">
          <label className="field">
            <span>Intitulé</span>
            <input
              value={row.title}
              onChange={(e) => updateDraft(idx, { title: e.target.value })}
              placeholder="ex. Attestation notariale"
            />
          </label>
          <label className="field">
            <span>Scan du document</span>
            <input
              type="file"
              accept="image/*,application/pdf"
              onChange={(e) =>
                updateDraft(idx, { file: e.target.files?.[0] ?? null })
              }
            />
            {row.file && (
              <em className="muted small">{row.file.name}</em>
            )}
          </label>
          <button
            type="button"
            className="btn btn-ghost btn-sm jewelry-item-remove"
            onClick={() => removeDraft(idx)}
            title="Retirer"
            aria-label="Retirer"
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}

      <button type="button" className="btn btn-ghost btn-sm" onClick={addDraft}>
        <Plus size={14} />
        Ajouter un document
      </button>
    </div>
  );
}

/** Append document drafts + deletions to a multipart FormData payload. */
export function appendFreeDocuments(
  fd: FormData,
  drafts: FreeDocumentDraft[],
  deletedIds: string[],
) {
  const withFile = drafts.filter((d) => d.file);
  for (const d of withFile) {
    fd.append("document_titles", d.title.trim() || d.file!.name);
    fd.append("documents", d.file!);
  }
  if (deletedIds.length) {
    fd.append("delete_document_ids", JSON.stringify(deletedIds));
  }
}
