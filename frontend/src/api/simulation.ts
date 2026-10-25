export interface SimulationConventions {
  engine: "LEGACY" | "CONFIGURED";
  day_count: "ACT365_FIXED" | "ACT360" | "30E360";
  amount_step: string;
  rounding: "HALF_UP" | "HALF_EVEN";
  due_adjustment: "NONE" | "FOLLOWING" | "MODIFIED_FOLLOWING" | "PRECEDING";
  interest_dates: "NOMINAL" | "ADJUSTED";
  calendar: string | null;
  calendar_snapshot?: { id: string; name: string; working_days: number[]; holidays: string[] };
  periods_per_year?: Record<string, number>;
}

export const DAY_COUNT_LABELS: Record<SimulationConventions["day_count"], string> = {
  ACT365_FIXED: "Jours réels / 365 fixe", ACT360: "Jours réels / 360", "30E360": "30E/360 (Eurobond)",
};
export const DUE_ADJUSTMENT_LABELS: Record<SimulationConventions["due_adjustment"], string> = {
  NONE: "Aucun ajustement", FOLLOWING: "Jour ouvré suivant", MODIFIED_FOLLOWING: "Suivant, ou précédent si changement de mois", PRECEDING: "Jour ouvré précédent",
};
