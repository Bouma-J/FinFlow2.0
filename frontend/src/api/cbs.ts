import { api } from "@/api/client";
import type { Paginated } from "@/api/types";

/** Les sélecteurs doivent inclure toutes les pages du référentiel. */
export async function allCbsReferences<T>(
  endpoint: string,
  params: Record<string, string | number | boolean> = {},
): Promise<T[]> {
  const rows: T[] = [];
  let page = 1;
  while (true) {
    const { data } = await api.get<Paginated<T>>(endpoint, {
      params: { ...params, page, page_size: 100 },
    });
    rows.push(...data.results);
    if (!data.next) return rows;
    page += 1;
  }
}
