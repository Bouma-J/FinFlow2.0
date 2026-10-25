import type { ReactNode } from "react";

import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm } from "@/auth/permissions";
import { EmptyState } from "@/components/ui";

/** Bloque l'accès à une page si l'utilisateur n'a aucune des permissions listées. */
export function PermissionRoute({
  anyOf,
  children,
  message = "Vous n'avez pas les droits pour accéder à cette page.",
}: {
  anyOf: readonly string[];
  children: ReactNode;
  message?: string;
}) {
  const { user } = useAuth();
  if (!hasAnyPerm(user, anyOf)) {
    return <EmptyState message={message} />;
  }
  return <>{children}</>;
}
