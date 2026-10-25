"""End-to-end de création des 3 types de garanties (client de test Django)."""
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

    resp = client.post("/api/v1/credit-applications/", {
        "client": cli["id"],
        "product": product["id"],
        "amount_requested": "10000000",
        "amount_proposed": "8000000",
        "duration_months": 24,
        "currency": "XOF",
    }, format="json", **SN)
    assert resp.status_code == 201, resp.data
    app = resp.data
    print("Dossier:", app["reference"], "montant proposé:", app["amount_proposed"])

    created = []

    # 1) Hypothèque avec LTV auto (valeur 12M / prêt 8M => 1.5)
    resp = client.post("/api/v1/guarantees/", {
        "guarantee_type": "MORTGAGE",
        "client": cli["id"],
        "application": app["id"],
        "document_type": "LAND_TITLE",
        "document_number": "TF-1234",
        "owner_last_name": "Kouassi",
        "owner_first_name": "Ama",
        "owner_marital_status": "MARRIED",
        "matrimonial_regime": "COMMUNITY",
        "address": "Cocody, Abidjan",
        "expertise_value": "13000000",
        "value_to_consider": "12000000",
        "occupancy_status": "FREE",
        "is_insured": "true",
    }, format="multipart", **SN)
    assert resp.status_code == 201, resp.data
    g = resp.data
    print("1) Hypothèque:", g["type_display"],
          "| valeur actualisée:", g["current_value"],
          "| LTV:", g["ltv_ratio"])
    assert str(g["current_value"]) == "12000000.00", g["current_value"]
    assert str(g["ltv_ratio"]) == "1.5000", g["ltv_ratio"]
    created.append(g["id"])

    # 2) Gage — moyen roulant
    resp = client.post("/api/v1/guarantees/", {
        "guarantee_type": "PLEDGE",
        "pledge_category": "VEHICLE",
        "client": cli["id"],
        "application": app["id"],
        "brand": "Toyota",
        "model_name": "Hilux",
        "registration": "1234-AB-01",
        "chassis_number": "CHS-999",
        "resale_value": "6000000",
    }, format="multipart", **SN)
    assert resp.status_code == 201, resp.data
    g = resp.data
    print("2) Gage véhicule:", g["pledge_category"], "| valeur actualisée:", g["current_value"])
    assert str(g["current_value"]) == "6000000.00", g["current_value"]
    created.append(g["id"])

    # 3) Garantie financière (DAT)
    resp = client.post("/api/v1/guarantees/", {
        "guarantee_type": "FINANCIAL",
        "client": cli["id"],
        "application": app["id"],
        "financial_type": "DAT",
        "account_number": "CI-000123",
        "balance": "4500000",
        "remuneration_rate": "3.5",
        "deposit_maturity_date": "2027-01-01",
    }, format="multipart", **SN)
    assert resp.status_code == 201, resp.data
    g = resp.data
    print("3) Garantie financière:", g["financial_type"], "| valeur actualisée:", g["current_value"])
    assert str(g["current_value"]) == "4500000.00", g["current_value"]
    created.append(g["id"])

    # Nettoyage
    for gid in created:
        client.delete(f"/api/v1/guarantees/{gid}/", **SN)
    client.delete(f"/api/v1/credit-applications/{app['id']}/", **SN)
    print("\nOK: les 3 types de garanties fonctionnent (LTV et valeurs auto validées).")


if __name__ == "__main__":
    main()
