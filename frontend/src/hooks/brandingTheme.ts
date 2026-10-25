import type { TenantBranding } from "@/api/types";

import defaultLogo from "@/assets/logo.jpg";

export const DEFAULT_THEME = {
  brand_primary: "#0f9488",
  brand_secondary: "#0d7a72",
  brand_accent: "#d4a017",
  brand_sidebar: "#084f4a",
  brand_sidebar_text: "#ffffff",
};

export const LOGIN_TENANT_CODE_KEY = "finflow.login-tenant-code";

type BrandColors = {
  brand_primary?: string | null;
  brand_secondary?: string | null;
  brand_accent?: string | null;
  brand_sidebar?: string | null;
  brand_sidebar_text?: string | null;
};

function hexToRgb(hex: string) {
  const h = hex.replace("#", "");
  if (h.length !== 6) return { r: 15, g: 148, b: 136 };
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function mixHex(hex: string, target: "black" | "white", amount: number) {
  const { r, g, b } = hexToRgb(hex);
  const t = target === "black" ? 0 : 255;
  const f = Math.min(1, Math.max(0, amount / 100));
  const nr = Math.round(r + (t - r) * f);
  const ng = Math.round(g + (t - g) * f);
  const nb = Math.round(b + (t - b) * f);
  return `rgb(${nr}, ${ng}, ${nb})`;
}

function rgba(hex: string, alpha: number) {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Applique la charte (couleurs CSS) au document — login inclus. */
export function applyTenantTheme(branding?: BrandColors | null) {
  const root = document.documentElement;
  const primary = branding?.brand_primary || DEFAULT_THEME.brand_primary;
  const secondary = branding?.brand_secondary || DEFAULT_THEME.brand_secondary;
  const accent = branding?.brand_accent || DEFAULT_THEME.brand_accent;
  const sidebar = branding?.brand_sidebar || DEFAULT_THEME.brand_sidebar;
  const sidebarText = branding?.brand_sidebar_text || DEFAULT_THEME.brand_sidebar_text;

  root.style.setProperty("--brand", primary);
  root.style.setProperty("--brand-dark", secondary);
  root.style.setProperty("--accent", accent);

  root.style.setProperty("--teal-50", mixHex(primary, "white", 92));
  root.style.setProperty("--teal-100", mixHex(primary, "white", 80));
  root.style.setProperty("--teal-400", mixHex(primary, "white", 22));
  root.style.setProperty("--teal-500", primary);
  root.style.setProperty("--teal-600", secondary);
  root.style.setProperty("--teal-700", mixHex(primary, "black", 28));
  root.style.setProperty("--gold-400", mixHex(accent, "white", 18));
  root.style.setProperty("--gold-500", accent);
  root.style.setProperty("--gold-600", mixHex(accent, "black", 12));
  root.style.setProperty("--info", primary);
  root.style.setProperty("--warning", mixHex(accent, "black", 8));
  root.style.setProperty("--shadow-brand", `0 8px 20px ${rgba(primary, 0.28)}`);

  root.style.setProperty("--brand-soft", mixHex(primary, "white", 92));
  root.style.setProperty("--brand-softer", mixHex(primary, "white", 96));
  root.style.setProperty("--brand-ink", mixHex(primary, "black", 38));
  root.style.setProperty("--brand-ring", rgba(primary, 0.22));
  root.style.setProperty("--accent-soft", mixHex(accent, "white", 88));
  root.style.setProperty("--accent-ink", mixHex(accent, "black", 35));
  root.style.setProperty("--surface-brand", mixHex(primary, "white", 97));
  root.style.setProperty(
    "--page-wash",
    `linear-gradient(180deg, ${mixHex(primary, "white", 95)} 0%, var(--bg) 220px)`,
  );
  root.style.setProperty("--brand-glow", rgba(primary, 0.14));
  root.style.setProperty("--accent-glow", rgba(accent, 0.22));
  root.style.setProperty(
    "--hero-gradient",
    `linear-gradient(135deg, ${mixHex(secondary, "black", 38)} 0%, ${mixHex(secondary, "black", 12)} 48%, ${secondary} 100%)`,
  );
  root.style.setProperty(
    "--login-gradient",
    `linear-gradient(160deg, ${mixHex(secondary, "black", 42)}, ${mixHex(secondary, "black", 58)})`,
  );

  root.style.setProperty("--sidebar-bg-start", sidebar);
  root.style.setProperty("--sidebar-bg-end", mixHex(sidebar, "black", 31));
  root.style.setProperty("--sidebar-text", sidebarText);
  root.style.setProperty("--sidebar-text-muted", sidebarText);
  root.style.setProperty("--sidebar-section", sidebarText);
  root.style.setProperty("--sidebar-hover-bg", rgba(sidebarText, 0.08));
  root.style.setProperty("--sidebar-active-bg", rgba(accent, 0.18));
  root.style.setProperty("--sidebar-active-bar", accent);
  root.style.setProperty("--sidebar-brand-accent", sidebarText);
  root.style.setProperty("--topbar-accent", rgba(primary, 0.12));
}

export function resolveLogoUrl(
  branding?: Pick<TenantBranding, "id" | "logo_url"> | null,
) {
  if (!branding?.logo_url) return defaultLogo;
  const sep = branding.logo_url.includes("?") ? "&" : "?";
  return `${branding.logo_url}${sep}v=${branding.id}`;
}

/** Identité de l'onglet, synchronisée avec la filiale affichée dans l'application. */
export function applyBrowserBranding(
  branding?: Pick<TenantBranding, "id" | "name" | "logo_url"> | null,
) {
  document.title = branding?.name?.trim() || "FIN_FLOW — Thuin Tech";
  let favicon = document.head.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!favicon) {
    favicon = document.createElement("link");
    favicon.rel = "icon";
    document.head.appendChild(favicon);
  }
  // Le logo d'une filiale peut être en PNG ou WebP, contrairement au JPEG par défaut.
  favicon.removeAttribute("type");
  const logoUrl = resolveLogoUrl(branding);
  if (favicon.getAttribute("href") !== logoUrl) favicon.href = logoUrl;
}

export function rememberLoginTenantCode(code: string | null | undefined) {
  const normalized = (code || "").trim().toUpperCase();
  if (!normalized) {
    localStorage.removeItem(LOGIN_TENANT_CODE_KEY);
    return;
  }
  localStorage.setItem(LOGIN_TENANT_CODE_KEY, normalized);
}

export function readRememberedLoginTenantCode(): string | null {
  return localStorage.getItem(LOGIN_TENANT_CODE_KEY);
}
