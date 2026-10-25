import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { Delegation, DelegationColleague } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Badge, Card, PageHeader } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function plusDaysISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const qc = useQueryClient();
  const [profile, setProfile] = useState({
    first_name: user?.first_name ?? "",
    last_name: user?.last_name ?? "",
    email: user?.email ?? "",
    phone: "",
  });
  const [pwd, setPwd] = useState({
    current_password: "",
    new_password: "",
    new_password_confirm: "",
  });
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [pwdMsg, setPwdMsg] = useState<string | null>(null);
  const [pwdError, setPwdError] = useState<string | null>(null);

  const [delegateId, setDelegateId] = useState("");
  const [startDate, setStartDate] = useState(todayISO);
  const [endDate, setEndDate] = useState(() => plusDaysISO(7));
  const [reason, setReason] = useState("");
  const [delMsg, setDelMsg] = useState<string | null>(null);
  const [delError, setDelError] = useState<string | null>(null);

  const mine = useQuery({
    queryKey: ["my-delegations"],
    queryFn: async () =>
      (await api.get<Delegation[]>("/delegations/mine/")).data,
  });

  const colleagues = useQuery({
    queryKey: ["delegation-colleagues"],
    queryFn: async () =>
      (await api.get<DelegationColleague[]>("/delegations/colleagues/")).data,
  });

  const saveProfile = useMutation({
    mutationFn: async () =>
      (
        await api.patch("/users/me/", {
          first_name: profile.first_name,
          last_name: profile.last_name,
          email: profile.email,
        })
      ).data,
    onSuccess: async () => {
      await refreshUser();
      setProfileMsg("Profil mis à jour.");
    },
    onError: () => setProfileMsg("Impossible d'enregistrer le profil."),
  });

  const changePwd = useMutation({
    mutationFn: async () =>
      (await api.post("/users/me/change-password/", pwd)).data,
    onSuccess: async () => {
      setPwd({
        current_password: "",
        new_password: "",
        new_password_confirm: "",
      });
      setPwdError(null);
      setPwdMsg("Mot de passe mis à jour.");
      await refreshUser();
    },
    onError: (err: unknown) => {
      setPwdMsg(null);
      setPwdError(
        apiErrorMessage(err, "Échec du changement de mot de passe."),
      );
    },
  });

  const give = useMutation({
    mutationFn: async () =>
      (
        await api.post<Delegation>("/delegations/give/", {
          delegate: delegateId,
          start_date: startDate,
          end_date: endDate,
          reason,
        })
      ).data,
    onSuccess: () => {
      setDelError(null);
      setDelMsg("Délégation créée. Le délégataire verra vos tâches en attente.");
      setReason("");
      qc.invalidateQueries({ queryKey: ["my-delegations"] });
    },
    onError: (err: unknown) => {
      setDelMsg(null);
      setDelError(apiErrorMessage(err, "Création impossible."));
    },
  });

  const revoke = useMutation({
    mutationFn: async (id: string) =>
      (await api.post(`/delegations/${id}/revoke/`)).data,
    onSuccess: () => {
      setDelMsg("Délégation révoquée.");
      qc.invalidateQueries({ queryKey: ["my-delegations"] });
    },
  });

  if (!user) return null;

  function onProfile(e: FormEvent) {
    e.preventDefault();
    setProfileMsg(null);
    saveProfile.mutate();
  }

  function onPassword(e: FormEvent) {
    e.preventDefault();
    setPwdError(null);
    setPwdMsg(null);
    if (pwd.new_password.length < 10) {
      setPwdError("Le nouveau mot de passe doit contenir au moins 10 caractères.");
      return;
    }
    if (pwd.new_password !== pwd.new_password_confirm) {
      setPwdError("Les mots de passe ne correspondent pas.");
      return;
    }
    changePwd.mutate();
  }

  function onGive(e: FormEvent) {
    e.preventDefault();
    setDelError(null);
    setDelMsg(null);
    if (!delegateId) {
      setDelError("Choisissez un délégataire.");
      return;
    }
    give.mutate();
  }

  const given = (mine.data ?? []).filter((d) => d.delegator === user.id);
  const received = (mine.data ?? []).filter((d) => d.delegate === user.id);

  return (
    <div className="page-shell">
      <PageHeader
        icon={UserRound}
        title="Mon profil"
        subtitle={`${user.username} — informations personnelles et sécurité`}
      />

      <Card title="Informations">
        <form className="inline-form" onSubmit={onProfile}>
          <div className="form-grid">
            <label className="field">
              <span>Identifiant</span>
              <input value={user.username} readOnly />
            </label>
            <label className="field">
              <span>Prénom</span>
              <input
                value={profile.first_name}
                onChange={(e) =>
                  setProfile({ ...profile, first_name: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Nom</span>
              <input
                value={profile.last_name}
                onChange={(e) =>
                  setProfile({ ...profile, last_name: e.target.value })
                }
              />
            </label>
            <label className="field">
              <span>E-mail *</span>
              <input
                type="email"
                value={profile.email}
                onChange={(e) =>
                  setProfile({ ...profile, email: e.target.value })
                }
                required
              />
            </label>
          </div>
          {profileMsg && <p className="muted small">{profileMsg}</p>}
          <button className="btn btn-primary" disabled={saveProfile.isPending}>
            Enregistrer le profil
          </button>
        </form>
      </Card>

      <Card title="Délégations de pouvoirs">
        <p className="muted small" style={{ marginBottom: 12 }}>
          Pendant votre absence, le délégataire pourra traiter vos tâches de
          circuit (approbations).
        </p>
        <form className="stack" onSubmit={onGive}>
          <div className="form-grid two-col">
            <label className="field">
              <span>Délégataire *</span>
              <select
                value={delegateId}
                onChange={(e) => setDelegateId(e.target.value)}
                required
              >
                <option value="">— choisir un collègue —</option>
                {(colleagues.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Motif</span>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Congé, mission…"
              />
            </label>
            <label className="field">
              <span>Début *</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Fin *</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                required
              />
            </label>
          </div>
          {delError && <div className="form-error">{delError}</div>}
          {delMsg && <p className="muted small">{delMsg}</p>}
          <button className="btn btn-primary btn-sm" disabled={give.isPending}>
            Déléguer mes pouvoirs
          </button>
        </form>

        <h4 style={{ marginTop: 20, marginBottom: 8 }}>Données</h4>
        {given.length === 0 ? (
          <p className="muted small">Aucune délégation donnée.</p>
        ) : (
          <ul className="stack" style={{ gap: 8 }}>
            {given.map((d) => (
              <li key={d.id} className="row-actions" style={{ gap: 8 }}>
                <span>
                  → {d.delegate_display} ({d.start_date} → {d.end_date})
                </span>
                <Badge
                  value={d.is_currently_valid ? "success" : "info"}
                  label={
                    d.is_currently_valid
                      ? "En cours"
                      : d.is_active
                        ? "Inactive"
                        : "Révoquée"
                  }
                />
                {d.is_active && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate(d.id)}
                  >
                    Révoquer
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        <h4 style={{ marginTop: 20, marginBottom: 8 }}>Reçues</h4>
        {received.length === 0 ? (
          <p className="muted small">Aucune délégation reçue.</p>
        ) : (
          <ul className="stack" style={{ gap: 8 }}>
            {received.map((d) => (
              <li key={d.id} className="row-actions" style={{ gap: 8 }}>
                <span>
                  ← {d.delegator_display} ({d.start_date} → {d.end_date})
                </span>
                <Badge
                  value={d.is_currently_valid ? "success" : "info"}
                  label={d.is_currently_valid ? "En cours" : "Inactive"}
                />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Changer mon mot de passe">
        <form className="inline-form" onSubmit={onPassword}>
          <div className="form-grid">
            <label className="field">
              <span>Mot de passe actuel *</span>
              <input
                type="password"
                value={pwd.current_password}
                onChange={(e) =>
                  setPwd({ ...pwd, current_password: e.target.value })
                }
                required
                autoComplete="current-password"
              />
            </label>
            <label className="field">
              <span>Nouveau mot de passe * (≥ 10 car.)</span>
              <input
                type="password"
                value={pwd.new_password}
                onChange={(e) =>
                  setPwd({ ...pwd, new_password: e.target.value })
                }
                required
                autoComplete="new-password"
              />
            </label>
            <label className="field">
              <span>Confirmation *</span>
              <input
                type="password"
                value={pwd.new_password_confirm}
                onChange={(e) =>
                  setPwd({ ...pwd, new_password_confirm: e.target.value })
                }
                required
                autoComplete="new-password"
              />
            </label>
          </div>
          {pwdError && <div className="form-error">{pwdError}</div>}
          {pwdMsg && <p className="muted small">{pwdMsg}</p>}
          <button className="btn btn-primary" disabled={changePwd.isPending}>
            Mettre à jour le mot de passe
          </button>
        </form>
      </Card>
    </div>
  );
}
