import type { CurrentUser } from "@/api/types";

/** Canal SMS : désactivé tant que FEATURE_SMS=0 côté serveur / provider absent. */
export function isSmsEnabled(user: CurrentUser | null | undefined): boolean {
  return Boolean(user?.features?.sms);
}
