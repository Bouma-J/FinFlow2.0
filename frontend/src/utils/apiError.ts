/** Extrait un message lisible de l'enveloppe DRF `{ errors: { detail } }`. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })
    ?.response?.data;
  if (!data) return fallback;
  if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
  const errors = data.errors as Record<string, unknown> | undefined;
  if (errors) {
    const nested = errors.detail;
    if (typeof nested === "string" && nested.trim()) return nested;
    if (Array.isArray(nested) && nested[0] != null) {
      return String(nested[0]);
    }
    const first = Object.entries(errors)[0];
    if (first) {
      const val = first[1];
      if (typeof val === "string" && val.trim()) return val;
      if (Array.isArray(val) && val[0] != null) {
        return first[0] === "detail"
          ? String(val[0])
          : `${first[0]} : ${val[0]}`;
      }
    }
  }
  return fallback;
}
