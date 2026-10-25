import { useMutation } from "@tanstack/react-query";
import { KeyRound, LogOut } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { homePath } from "@/auth/routePerms";
import { useTenantBranding } from "@/hooks/useTenantBranding";
import { apiErrorMessage } from "@/utils/apiError";

function extractError(err: unknown): string {
  const data =
    err && typeof err === "object" && "response" in err
      ? (err as { response?: { data?: Record<string, unknown> } }).response
          ?.data
      : undefined;
  const errors = (data?.errors as Record<string, unknown> | undefined) || data;
  if (errors) {
    for (const key of [
      "current_password",
      "new_password",
      "new_password_confirm",
      "detail",
      "non_field_errors",
    ]) {
      const val = errors[key];
      if (typeof val === "string" && val.trim()) return val;
      if (Array.isArray(val) && val.length) return val.map(String).join(" ");
    }
  }
  return apiErrorMessage(err, "Impossible de changer le mot de passe.");
}

export function ForceChangePasswordPage() {
  const { user, refreshUser, logout, markPasswordChanged } = useAuth();
  const { branding, logoUrl, tenantName, tenantCode } = useTenantBranding();
  const navigate = useNavigate();
  const [currentPassword, setCurrent] = useState("");
  const [newPassword, setNew] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<{
          detail: string;
          must_change_password: boolean;
        }>("/users/me/change-password/", {
          current_password: currentPassword,
          new_password: newPassword,
          new_password_confirm: confirm,
        })
      ).data,
    onSuccess: async () => {
      markPasswordChanged();
      try {
        await refreshUser();
      } catch {
        // Le drapeau local suffit pour sortir de l'écran forcé.
      }
      const nextUser = user
        ? { ...user, must_change_password: false }
        : user;
      navigate(homePath(nextUser), { replace: true });
    },
    onError: (err: unknown) => setError(extractError(err)),
  });

  if (!user) return <Navigate to="/login" replace />;
  if (!user.must_change_password) return <Navigate to={homePath(user)} replace />;

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword.length < 10) {
      setError("Le nouveau mot de passe doit contenir au moins 10 caractères.");
      return;
    }
    if (newPassword !== confirm) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    mutation.mutate();
  }

  return (
    <div className="page-shell login-screen">
      <div className="login-card force-password-card">
        <div className="login-brand">
          <img
            src={logoUrl}
            alt={branding ? tenantName : "Thuin Tech"}
            className={branding?.logo_url ? "has-tenant-logo" : undefined}
          />
          <h1>FIN_FLOW</h1>
          <p>
            {tenantCode
              ? `${tenantCode} — Changement de mot de passe`
              : "Changement de mot de passe obligatoire"}
          </p>
        </div>
        <div className="force-password-intro">
          <KeyRound size={18} />
          <span>
            Pour des raisons de sécurité, définissez un nouveau mot de passe
            avant de continuer.
          </span>
        </div>
        <form onSubmit={submit} className="login-form">
          <label className="field">
            <span>Mot de passe temporaire (reçu par e-mail) *</span>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrent(e.target.value)}
              required
              autoComplete="current-password"
              autoFocus
            />
          </label>
          <label className="field">
            <span>Nouveau mot de passe * (≥ 10 car.)</span>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNew(e.target.value)}
              required
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            <span>Confirmer le nouveau mot de passe *</span>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
            />
          </label>
          <p className="field-hint">
            Évitez un mot de passe uniquement numérique, trop courant, ou trop
            proche de votre identifiant / e-mail.
          </p>
          {error && <div className="form-error">{error}</div>}
          <button
            className="btn btn-primary btn-block"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Enregistrement…" : "Enregistrer et continuer"}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-block"
            onClick={() => logout()}
          >
            <LogOut size={16} />
            Se déconnecter
          </button>
        </form>
      </div>
    </div>
  );
}
