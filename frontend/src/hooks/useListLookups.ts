import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Agency, CreditProduct, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";

export type OfficerOption = { id: string; display_name: string };

export function useOfficerOptions() {
  const { activeTenant, user } = useAuth();
  const scoped = Boolean(activeTenant || user?.tenant);
  return useQuery({
    queryKey: ["users-officers", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<{ results: OfficerOption[] }>("/users/officers/")
      ).data.results,
    enabled: scoped,
  });
}

export function useProductOptions() {
  const { activeTenant, user } = useAuth();
  const scoped = Boolean(activeTenant || user?.tenant);
  return useQuery({
    queryKey: ["credit-products-filter", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CreditProduct>>("/credit-products/", {
          params: { page_size: 200, is_active: true },
        })
      ).data.results,
    enabled: scoped,
  });
}

export function useAgencyOptions() {
  const { activeTenant, user } = useAuth();
  const scoped = Boolean(activeTenant || user?.tenant);
  return useQuery({
    queryKey: ["agencies-filter", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<Agency>>("/agencies/", {
          params: { page_size: 100, is_active: true },
        })
      ).data.results,
    enabled: scoped,
  });
}
