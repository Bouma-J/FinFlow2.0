import type { MouseEvent, ReactNode } from "react";
import { Link, type To } from "react-router-dom";

import type { CurrentUser } from "@/api/types";
import { hasAnyPerm } from "@/auth/permissions";

/** Lien affiché seulement si l'utilisateur a au moins un des droits. */
export function PermLink({
  user,
  anyOf,
  to,
  children,
  fallback,
  className,
  onClick,
  state,
}: {
  user: CurrentUser | null | undefined;
  anyOf: readonly string[];
  to: To;
  children: ReactNode;
  fallback?: ReactNode;
  className?: string;
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
  state?: unknown;
}) {
  if (!hasAnyPerm(user, anyOf)) {
    if (fallback === null) return null;
    if (fallback !== undefined) return <>{fallback}</>;
    if (className) return <span className={className}>{children}</span>;
    return <>{children}</>;
  }
  return (
    <Link to={to} state={state} className={className} onClick={onClick}>
      {children}
    </Link>
  );
}
