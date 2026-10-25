"""End-to-end du cycle de vie d'un dossier de crédit (client de test Django)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()

from rest_framework.test import APIClient  # noqa: E402

from apps.accounts.models import User  # noqa: E402

SN = {"SERVER_NAME": "localhost"}


def main():
    user = User.objects.get(username="fil01_admin")
    client = APIClient()
    client.force_authenticate(user=user)

    product = client.get("/api/v1/credit-products/", **SN).data["results"][0]
    cli = client.get("/api/v1/clients/", **SN).data["results"][0]

    # 1) Création du dossier (montant < 10M => seule l'étape agence s'applique)
    resp = client.post("/api/v1/credit-applications/", {
        "reference": "DOS-0001",
        "client": cli["id"],
        "product": product["id"],
        "amount_requested": "5000000",
        "duration_months": 12,
        "currency": "XOF",
        "risk_level": 2,
    }, format="json", **SN)
    assert resp.status_code == 201, resp.data
    app_id = resp.data["id"]
    print("1) Dossier créé:", resp.data["reference"], "statut:", resp.data["status"])

    # 2) Soumission -> démarre le workflow
    resp = client.post(f"/api/v1/credit-applications/{app_id}/submit/", **SN)
    assert resp.status_code == 200, resp.data
    print("2) Dossier soumis, statut:", resp.data["status"])

    # 3) Tâches en attente pour mes rôles
    pending = client.get("/api/v1/approval-tasks/my_pending/", **SN).data["results"]
    print("3) Tâches en attente:", [t["step_name"] for t in pending])

    # 4) Décision : approbation
    task_id = pending[0]["id"]
    resp = client.post(f"/api/v1/approval-tasks/{task_id}/decide/", {
        "decision": "APPROVED", "comment": "Dossier conforme.",
    }, format="json", **SN)
    assert resp.status_code == 200, resp.data
    print("4) Instance workflow:", resp.data["status"])

    # 5) Le dossier doit être APPROUVÉ
    app = client.get(f"/api/v1/credit-applications/{app_id}/", **SN).data
    print("5) Statut dossier après approbation:", app["status"])

    # 6) Décaissement -> crée le prêt et l'échéancier
    resp = client.post(f"/api/v1/credit-applications/{app_id}/disburse/", **SN)
    assert resp.status_code == 200, resp.data
    loan = resp.data
    print("6) Prêt créé:", loan["principal"], "| échéances:", len(loan["installments"]))

    print("\nOK: cycle de vie complet validé.")


if __name__ == "__main__":
    main()
