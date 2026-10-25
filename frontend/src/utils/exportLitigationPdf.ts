import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

import type { LitigationFile } from "@/api/types";
import {
  lastAutoTableY,
  PDF_BRAND_FILL,
  pdfMoney,
  pdfText,
} from "@/utils/pdfHelpers";

export function exportLitigationPdf(lit: LitigationFile): void {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const title = pdfText(lit.title || lit.case_reference || "Contentieux");
  doc.setFontSize(14);
  doc.text(title, 14, 16);
  doc.setFontSize(10);
  doc.text(
    pdfText(
      `${lit.court_name || "-"} · ${lit.status_display} · RG ${lit.case_reference || "-"}`,
    ),
    14,
    22,
  );
  doc.text(
    pdfText(
      `Cabinet: ${lit.law_firm_detail?.name || lit.lawyer || "-"} · Huissier: ${lit.bailiff_party_detail?.name || lit.bailiff || "-"}`,
    ),
    14,
    28,
  );
  doc.text(
    pdfText(
      `Prochaine audience: ${lit.hearing_date || "-"} ${lit.hearing_time || ""} · ${lit.hearing_location || ""}`,
    ),
    14,
    34,
  );
  doc.text(
    pdfText(
      `Total reclame: ${pdfMoney(lit.claimed_total)} · Jugement: ${lit.judgment_outcome_display || "-"} ${pdfMoney(lit.judgment_amount)}`,
    ),
    14,
    40,
  );

  autoTable(doc, {
    startY: 46,
    head: [["Date", "Type", "Lieu / resultat"]],
    body: (lit.events || []).map((e) => [
      e.event_date,
      pdfText(e.event_type_display),
      pdfText(e.location || e.outcome || e.comment || "-"),
    ]),
    styles: { fontSize: 8 },
    headStyles: { fillColor: PDF_BRAND_FILL },
  });

  const y = lastAutoTableY(doc, 50);
  autoTable(doc, {
    startY: y + 6,
    head: [["Date", "Frais", "Montant", "Paye"]],
    body: (lit.costs || []).map((c) => [
      c.cost_date,
      pdfText(c.cost_type_display),
      pdfMoney(c.amount),
      c.is_paid ? "Oui" : "Non",
    ]),
    styles: { fontSize: 8 },
    headStyles: { fillColor: PDF_BRAND_FILL },
  });

  const ref = (lit.case_reference || lit.id).replace(/[^\w-]+/g, "_");
  doc.save(`contentieux_${ref}.pdf`);
}
