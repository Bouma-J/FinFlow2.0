import type { jsPDF } from "jspdf";

/** Couleur d'en-tête des tableaux PDF Fin Flow. */
export const PDF_BRAND_FILL: [number, number, number] = [15, 148, 136];

/** Normalise le texte pour jsPDF (accents / espaces fins). */
export function pdfText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\x20-\x7E\xA0-\xFF]/g, "")
    .replace(/[\u00A0\u202F\u2009]/g, " ");
}

/** Montant arrondi avec séparateur d'espace milliers. */
export function pdfMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return "-";
  return Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

export function lastAutoTableY(doc: jsPDF, fallback = 50): number {
  return (
    (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable
      ?.finalY || fallback
  );
}
