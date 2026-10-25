import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="centered-loader">Chargement…</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (
    user.must_change_password &&
    location.pathname !== "/changer-mot-de-passe"
  ) {
    return <Navigate to="/changer-mot-de-passe" replace />;
  }
  return <>{children}</>;
}
