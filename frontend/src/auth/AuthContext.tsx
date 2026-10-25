import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import axios from "axios";

import { api, tokenStore } from "@/api/client";
import type { CurrentUser } from "@/api/types";
import { rememberLoginTenantCode } from "@/hooks/brandingTheme";

export class MfaRequiredError extends Error {
  code = "mfa_required" as const;
  constructor(message = "Code MFA requis.") {
    super(message);
    this.name = "MfaRequiredError";
  }
}

export class MfaInvalidError extends Error {
  code = "mfa_invalid" as const;
  constructor(message = "Code MFA invalide.") {
    super(message);
    this.name = "MfaInvalidError";
  }
}

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (
    username: string,
    password: string,
    otp?: string,
  ) => Promise<{ mustChangePassword: boolean; user: CurrentUser | null }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  markPasswordChanged: () => void;
  activeTenant: string | null;
  setActiveTenant: (tenantId: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function raiseAuthError(err: unknown): never {
  if (axios.isAxiosError(err)) {
    // L'API enveloppe les erreurs sous { success, errors: … }.
    const payload = err.response?.data as
      | { detail?: unknown; code?: string; errors?: { detail?: unknown; code?: string } }
      | undefined;
    const nested = payload?.errors;
    const detail = nested?.detail ?? payload?.detail;
    const code =
      (typeof detail === "object" && detail && "code" in detail
        ? (detail as { code?: string }).code
        : undefined) ||
      nested?.code ||
      payload?.code;
    if (code === "mfa_required" || err.response?.status === 401) {
      if (
        code === "mfa_required" ||
        (typeof detail === "object" &&
          detail &&
          (detail as { code?: string }).code === "mfa_required")
      ) {
        throw new MfaRequiredError(
          typeof detail === "object" && detail && "detail" in detail
            ? String((detail as { detail: string }).detail)
            : "Code MFA requis.",
        );
      }
      if (code === "mfa_invalid") {
        throw new MfaInvalidError();
      }
    }
    if (code === "mfa_invalid") throw new MfaInvalidError();
    const status = err.response?.status;
    if (status && status >= 500) {
      throw new Error(
        "Le serveur d'authentification a échoué. Réessayez dans un instant.",
      );
    }
    if (status === 429) {
      throw new Error("Trop de tentatives. Patientez une minute puis réessayez.");
    }
    if (status === 401) {
      throw new Error("Identifiants invalides.");
    }
  }
  throw err instanceof Error ? err : new Error("Identifiants invalides.");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTenant, setActiveTenantState] = useState<string | null>(
    tokenStore.getTenant(),
  );

  const applyUserTenant = useCallback((data: CurrentUser) => {
    // Filiale : la filiale de l'utilisateur est le scope unique — l'envoyer
    // systématiquement en X-Tenant-Id (même si le middleware JWT ne l'a pas vu).
    if (!data.is_group_level && data.tenant) {
      tokenStore.setTenant(data.tenant);
      setActiveTenantState(data.tenant);
      if (data.tenant_branding?.code) {
        rememberLoginTenantCode(data.tenant_branding.code);
      }
    }
  }, []);

  const loadProfile = useCallback(async (): Promise<CurrentUser | null> => {
    try {
      const { data } = await api.get<CurrentUser>("/users/me/");
      setUser(data);
      applyUserTenant(data);
      return data;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [applyUserTenant]);

  const refreshUser = useCallback(async () => {
    try {
      const { data } = await api.get<CurrentUser>("/users/me/");
      setUser(data);
      applyUserTenant(data);
    } catch {
      setUser(null);
    }
  }, [applyUserTenant]);

  const markPasswordChanged = useCallback(() => {
    setUser((prev) =>
      prev ? { ...prev, must_change_password: false } : prev,
    );
  }, []);

  useEffect(() => {
    if (tokenStore.getAccess()) {
      loadProfile();
    } else {
      setLoading(false);
    }
  }, [loadProfile]);

  const login = useCallback(
    async (username: string, password: string, otp?: string) => {
      try {
        const body: Record<string, string> = { username, password };
        if (otp) body.otp = otp;
        const { data } = await api.post<{
          access: string;
          refresh: string;
          must_change_password?: boolean;
        }>("/auth/token/", body);
        tokenStore.set(data.access, data.refresh);
        const profile = await loadProfile();
        return {
          mustChangePassword: Boolean(
            data.must_change_password ?? profile?.must_change_password,
          ),
          user: profile,
        };
      } catch (err) {
        return raiseAuthError(err);
      }
    },
    [loadProfile],
  );

  const logout = useCallback(async () => {
    const refresh = tokenStore.getRefresh();
    try {
      if (refresh && tokenStore.getAccess()) {
        await api.post("/auth/logout/", { refresh });
      }
    } catch {
      // ignore — on nettoie localement dans tous les cas
    }
    tokenStore.clear();
    setUser(null);
    setActiveTenantState(null);
  }, []);

  const setActiveTenant = useCallback((tenantId: string | null) => {
    tokenStore.setTenant(tenantId);
    setActiveTenantState(tenantId);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      refreshUser,
      markPasswordChanged,
      activeTenant,
      setActiveTenant,
    }),
    [
      user,
      loading,
      login,
      logout,
      refreshUser,
      markPasswordChanged,
      activeTenant,
      setActiveTenant,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans un AuthProvider.");
  return ctx;
}
