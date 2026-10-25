import { useQuery } from "@tanstack/react-query";
import { useLayoutEffect, useMemo } from "react";

import { api } from "@/api/client";
import type { Tenant, TenantBranding } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { readCachedBranding, rememberBranding } from "@/hooks/brandingCache";
import {
  applyBrowserBranding,
  applyTenantTheme,
  resolveLogoUrl,
} from "@/hooks/brandingTheme";

export {
  applyTenantTheme,
  DEFAULT_THEME,
  LOGIN_TENANT_CODE_KEY,
  readRememberedLoginTenantCode,
  rememberLoginTenantCode,
  resolveLogoUrl,
} from "@/hooks/brandingTheme";

/** Charte publique avant authentification (écran login). */
export function usePublicTenantBranding(code: string | null | undefined) {
  const normalized = (code || "").trim().toUpperCase();
  const cached = useMemo(() => readCachedBranding("code", normalized), [normalized]);

  const query = useQuery({
    queryKey: ["public-tenant-branding", normalized],
    queryFn: async () =>
      (
        await api.get<TenantBranding>("/tenants/branding/", {
          params: { code: normalized },
        })
      ).data,
    enabled: normalized.length > 0,
    staleTime: 60_000,
    retry: false,
  });

  const branding = query.data ?? (query.isError ? null : cached);
  useLayoutEffect(() => {
    applyTenantTheme(branding);
    applyBrowserBranding(branding);
    if (branding) rememberBranding(branding);
  }, [branding]);

  const logoUrl = resolveLogoUrl(branding);

  return {
    branding,
    logoUrl,
    tenantName: branding?.name ?? "FIN_FLOW",
    tenantCode: branding?.code ?? null,
    isLoading: query.isFetching,
    isError: query.isError,
    notFound: Boolean(normalized) && query.isError,
  };
}

/** Applique le logo et les couleurs de la filiale active (y compris la barre de menu). */
export function useTenantBranding() {
  const { user, activeTenant } = useAuth();
  const tenantId = user?.is_group_level ? activeTenant : user?.tenant ?? null;
  const cached = useMemo(() => readCachedBranding("id", tenantId), [tenantId]);

  const { data: tenant, isPending } = useQuery({
    queryKey: ["tenant-branding", tenantId],
    queryFn: async () =>
      tenantId
        ? (await api.get<Tenant>(`/tenants/${tenantId}/`)).data
        : null,
    enabled: !!tenantId,
    staleTime: 60_000,
  });

  const profileBranding = user?.tenant_branding?.id === tenantId ? user.tenant_branding : null;
  const branding = tenant?.id === tenantId ? tenant : cached ?? profileBranding;

  useLayoutEffect(() => {
    applyTenantTheme(branding);
    applyBrowserBranding(branding);
    if (branding) rememberBranding(branding);
  }, [branding]);

  const logoUrl = resolveLogoUrl(branding);

  return {
    branding,
    logoUrl,
    tenantName: branding?.name ?? "FIN_FLOW",
    tenantCode: branding?.code ?? null,
    isLoading: Boolean(tenantId) && !branding && isPending,
  };
}
