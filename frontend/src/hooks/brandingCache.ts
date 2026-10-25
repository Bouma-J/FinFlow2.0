import type { TenantBranding } from "@/api/types";

// Le script synchrone de index.html lit ce même format avant le premier affichage.
const CACHE_PREFIX = "finflow.branding.v1.";
const COLOR_FIELDS = [
  "brand_primary", "brand_secondary", "brand_accent", "brand_sidebar", "brand_sidebar_text",
] as const;

export function readCachedBranding(kind: "id" | "code", value: string | null): TenantBranding | null {
  if (!value) return null;
  try {
    const cached = JSON.parse(localStorage.getItem(`${CACHE_PREFIX}${kind}.${value}`) || "null");
    const branding = cached?.branding;
    if (
      cached?.version !== 1 || !branding || branding[kind] !== value ||
      typeof branding.id !== "string" || typeof branding.code !== "string" ||
      typeof branding.name !== "string" ||
      !(branding.logo_url === null || typeof branding.logo_url === "string") ||
      !COLOR_FIELDS.every((field) => typeof branding[field] === "string" && /^#[0-9a-f]{6}$/i.test(branding[field]))
    ) return null;
    return branding as TenantBranding;
  } catch {
    return null;
  }
}

/** Cache de présentation publique uniquement : aucune donnée métier ni habilitation. */
export function rememberBranding(branding: TenantBranding) {
  const publicBranding: TenantBranding = {
    id: branding.id,
    code: branding.code.trim().toUpperCase(),
    name: branding.name,
    logo_url: branding.logo_url,
    brand_primary: branding.brand_primary,
    brand_secondary: branding.brand_secondary,
    brand_accent: branding.brand_accent,
    brand_sidebar: branding.brand_sidebar,
    brand_sidebar_text: branding.brand_sidebar_text,
  };
  const variables: Record<string, string> = {};
  const style = document.documentElement.style;
  for (let index = 0; index < style.length; index += 1) {
    const property = style.item(index);
    if (property.startsWith("--")) variables[property] = style.getPropertyValue(property);
  }
  try {
    const snapshot = JSON.stringify({ version: 1, branding: publicBranding, variables });
    localStorage.setItem(`${CACHE_PREFIX}id.${publicBranding.id}`, snapshot);
    localStorage.setItem(`${CACHE_PREFIX}code.${publicBranding.code}`, snapshot);
  } catch {
    // Le refus du stockage ou un quota plein ne doit pas empêcher la navigation.
  }
}
