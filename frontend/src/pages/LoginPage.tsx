import { Building2, KeyRound, Lock, LogIn, User } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  MfaInvalidError,
  MfaRequiredError,
  useAuth,
} from "@/auth/AuthContext";
import { homePath } from "@/auth/routePerms";
import {
  applyTenantTheme,
  readRememberedLoginTenantCode,
  rememberLoginTenantCode,
  usePublicTenantBranding,
} from "@/hooks/useTenantBranding";

function initialTenantCode(
  routeCode?: string,
  queryCode?: string | null,
): string {
  return (
    (routeCode || "").trim() ||
    (queryCode || "").trim() ||
    readRememberedLoginTenantCode() ||
    ""
  ).toUpperCase();
}

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const { tenantCode: routeCode } = useParams<{ tenantCode?: string }>();
  const [searchParams] = useSearchParams();
  const [tenantCode, setTenantCode] = useState(() =>
    initialTenantCode(routeCode, searchParams.get("filiale")),
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [mfaStep, setMfaStep] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const {
    branding,
    logoUrl,
    tenantName,
    tenantCode: resolvedCode,
    notFound,
  } = usePublicTenantBranding(tenantCode);

  useEffect(() => {
    if (!tenantCode.trim()) {
      applyTenantTheme(null);
    }
  }, [tenantCode]);

  useEffect(() => {
    if (routeCode && routeCode.trim().toUpperCase() !== tenantCode) {
      setTenantCode(routeCode.trim().toUpperCase());
    }
  }, [routeCode]); // eslint-disable-line react-hooks/exhaustive-deps

  if (user) {
    return (
      <Navigate
        to={user.must_change_password ? "/changer-mot-de-passe" : homePath(user)}
        replace
      />
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (resolvedCode) {
        rememberLoginTenantCode(resolvedCode);
      } else if (tenantCode.trim()) {
        rememberLoginTenantCode(tenantCode);
      }
      const result = await login(
        username,
        password,
        mfaStep ? otp : undefined,
      );
      navigate(
        result.mustChangePassword
          ? "/changer-mot-de-passe"
          : homePath(result.user),
        { replace: true },
      );
    } catch (err) {
      if (err instanceof MfaRequiredError) {
        setMfaStep(true);
        setError(null);
      } else if (err instanceof MfaInvalidError) {
        setError("Code MFA invalide.");
      } else {
        setError(
          err instanceof Error ? err.message : "Identifiants invalides.",
        );
        setMfaStep(false);
        setOtp("");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const subtitle = branding
    ? `Connexion — ${tenantName}`
    : "Gestion des dossiers de crédit — Thuin Tech";

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <img
            src={logoUrl}
            alt={branding ? tenantName : "Thuin Tech"}
            className={branding?.logo_url ? "has-tenant-logo" : undefined}
          />
          <h1>FIN_FLOW</h1>
          <p>{subtitle}</p>
          {resolvedCode && (
            <span className="login-tenant-chip">{resolvedCode}</span>
          )}
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          {!mfaStep ? (
            <>
              <label className="field">
                <span>Code filiale</span>
                <div className="input-icon">
                  <Building2 />
                  <input
                    value={tenantCode}
                    onChange={(e) =>
                      setTenantCode(e.target.value.toUpperCase())
                    }
                    onBlur={() => {
                      const code = tenantCode.trim().toUpperCase();
                      setTenantCode(code);
                      if (code) rememberLoginTenantCode(code);
                    }}
                    placeholder="ex. FIL01"
                    autoComplete="organization"
                  />
                </div>
                <span className="field-hint">
                  Adapte le logo et les couleurs à votre filiale. Laissez vide
                  pour la charte Groupe / Thuin Tech.
                </span>
                {notFound && tenantCode.trim() && (
                  <span className="field-hint login-branding-warn">
                    Filiale introuvable ou inactive — charte par défaut affichée.
                  </span>
                )}
              </label>
              <label className="field">
                <span>Identifiant</span>
                <div className="input-icon">
                  <User />
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="votre identifiant"
                    autoFocus={!tenantCode}
                    required
                  />
                </div>
              </label>
              <label className="field">
                <span>Mot de passe</span>
                <div className="input-icon">
                  <Lock />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                  />
                </div>
              </label>
            </>
          ) : (
            <label className="field">
              <span>Code MFA (application d’authentification)</span>
              <div className="input-icon">
                <KeyRound />
                <input
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  placeholder="123456"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                />
              </div>
            </label>
          )}
          {error && <div className="form-error">{error}</div>}
          <button className="btn btn-primary btn-block" disabled={submitting}>
            <LogIn />
            {submitting
              ? "Connexion…"
              : mfaStep
                ? "Valider le code"
                : "Se connecter"}
          </button>
          {mfaStep && (
            <button
              type="button"
              className="btn btn-ghost btn-block"
              onClick={() => {
                setMfaStep(false);
                setOtp("");
                setError(null);
              }}
            >
              Retour
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
