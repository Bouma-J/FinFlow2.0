import type { ReactNode } from "react";

import { useAuth } from "@/auth/AuthContext";
import { isFinflowAdmin } from "@/auth/routePerms";
import { EmptyState } from "@/components/ui";

export function isAdmin(user: {
  is_superuser?: boolean;
  is_staff?: boolean;
  is_group_level?: boolean;
  roles?: string[];
} | null): boolean {
  return isFinflowAdmin(user);
}

export function AdminRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!isFinflowAdmin(user)) {
    return (
      <EmptyState message="Accès réservé aux administrateurs." />
    );
  }
  return <>{children}</>;
}
