"""Test de fumée de l'API FIN_FLOW (à lancer serveur démarré)."""
import sys

import requests

BASE = "http://127.0.0.1:8000/api/v1"


def login(username, password):
    r = requests.post(f"{BASE}/auth/token/", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access"]


def main():
    # --- Utilisateur filiale ---
    fil_token = login("fil01_admin", "FinFlow2026!")
    fil_headers = {"Authorization": f"Bearer {fil_token}"}

    me = requests.get(f"{BASE}/users/me/", headers=fil_headers).json()
    print("Profil filiale:", me["username"], "| tenant:", me["tenant"], "| rôles:", me["roles"])

    products = requests.get(f"{BASE}/credit-products/", headers=fil_headers).json()
    print("Produits visibles (filiale):", products["count"])

    clients = requests.get(f"{BASE}/clients/", headers=fil_headers).json()
    print("Clients visibles (filiale):", clients["count"])

    # Simulation d'un crédit
    sim = requests.post(
        f"{BASE}/credit-applications/simulate/",
        headers=fil_headers,
        json={"amount": "1000000", "annual_rate": "12.5", "months": 12},
    ).json()
    print("Simulation -> mensualité:", sim["monthly_payment"], "| total:", sim["total_repayment"])

    # Dashboard opérationnel filiale
    dash = requests.get(f"{BASE}/reporting/dashboard/", headers=fil_headers).json()
    print("Dashboard filiale -> scope:", dash["scope"], "| dossiers:", dash["credits"]["summary"]["total"])

    # --- Utilisateur Groupe : consolidation ---
    grp_token = login("group_admin", "FinFlow2026!")
    grp_headers = {"Authorization": f"Bearer {grp_token}"}

    conso = requests.get(f"{BASE}/reporting/group-consolidation/", headers=grp_headers).json()
    print("Consolidation Groupe -> scope:", conso["scope"])

    breakdown = requests.get(
        f"{BASE}/reporting/group-breakdown/?dimension=country", headers=grp_headers
    ).json()
    print("Décomposition Groupe par pays:", breakdown["rows"])

    tenants = requests.get(f"{BASE}/tenants/", headers=grp_headers).json()
    print("Filiales visibles (Groupe):", tenants["count"])

    # Un utilisateur filiale ne doit PAS accéder à la gestion des filiales
    forbidden = requests.get(f"{BASE}/tenants/", headers=fil_headers)
    print("Accès /tenants/ par filiale (attendu 403):", forbidden.status_code)

    print("\nOK: test de fumée réussi.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print("ÉCHEC:", exc)
        sys.exit(1)
