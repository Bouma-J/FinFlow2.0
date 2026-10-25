import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

const ACCESS_KEY = "finflow_access";
const REFRESH_KEY = "finflow_refresh";
const TENANT_KEY = "finflow_tenant";

export const tokenStore = {
  getAccess: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  getTenant: () => localStorage.getItem(TENANT_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  setAccess: (access: string) => localStorage.setItem(ACCESS_KEY, access),
  setTenant: (tenantId: string | null) => {
    if (tenantId) localStorage.setItem(TENANT_KEY, tenantId);
    else localStorage.removeItem(TENANT_KEY);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(TENANT_KEY);
  },
};

export const api: AxiosInstance = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.getAccess();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const tenant = tokenStore.getTenant();
  // En-tête permettant à un utilisateur Groupe de cibler une filiale
  if (tenant) config.headers["X-Tenant-Id"] = tenant;
  return config;
});

let refreshing: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) throw new Error("Aucun jeton de rafraîchissement.");
  const { data } = await axios.post(`${BASE_URL}/auth/token/refresh/`, {
    refresh,
  });
  if (data.refresh) {
    tokenStore.set(data.access, data.refresh);
  } else {
    tokenStore.setAccess(data.access);
  }
  return data.access;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      tokenStore.getRefresh()
    ) {
      original._retry = true;
      try {
        refreshing = refreshing ?? refreshAccessToken();
        const newToken = await refreshing;
        refreshing = null;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch (e) {
        refreshing = null;
        tokenStore.clear();
        window.location.href = "/login";
        return Promise.reject(e);
      }
    }
    return Promise.reject(error);
  },
);
