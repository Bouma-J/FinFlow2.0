import type { CurrentUser } from "@/api/types";

/** Vérifie un codename Django (`app.codename`) pour l'utilisateur courant. */
export function hasPerm(
  user: CurrentUser | null | undefined,
  codename: string,
): boolean {
  if (!user) return false;
  if (user.is_superuser) return true;
  return (user.permissions ?? []).includes(codename);
}

export function hasAnyPerm(
  user: CurrentUser | null | undefined,
  codenames: readonly string[],
): boolean {
  return codenames.some((c) => hasPerm(user, c));
}
