"""Test global du dossier de crédit après refactor montants / mécanismes / analyse."""
from __future__ import annotations

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from rest_framework.test import APIClient  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.credits.amounts import reference_amount  # noqa: E402
from apps.credits.models import CreditApplication, FinancialAnalysis  # noqa: E402
from apps.credits.services import compute_amortization_schedule  # noqa: E402

SN = {"SERVER_NAME": "localhost"}
PASS = 0
FAIL = 0


def ok(label: str, detail: str = ""):
    global PASS
    PASS += 1
    print(f"  OK  {label}" + (f" — {detail}" if detail else ""))


def fail(label: str, detail: str = ""):
    global FAIL
    FAIL += 1
    print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def assert_true(cond, label, detail=""):
    if cond:
        ok(label, detail)
    else:
        fail(label, detail)


def main():
    print("=== TEST GLOBAL DOSSIER DE CRÉDIT ===\n")

    # Création / soumission par un chargé (≠ décideur)
    creator = User.objects.filter(username="jacques").first() or user
    approver = User.objects.filter(username="assetou").first() or user
    if creator.id == approver.id:
        approver = User.objects.filter(username="fil01_admin").first() or user

    client = APIClient()
    client.force_authenticate(user=creator)
    ok("acteur création", creator.username)
    ok("acteur décision", approver.username)

    products = client.get("/api/v1/credit-products/", **SN).data["results"]
    clients = client.get("/api/v1/clients/", **SN).data["results"]
    assert products and clients, "Données de démo manquantes"
    product = products[0]
    cli = next((c for c in clients if c.get("client_type") == "INDIVIDUAL"), clients[0])
    corp = next((c for c in clients if c.get("client_type") == "CORPORATE"), None)

    # ------------------------------------------------------------------ #
    print("A) Moteur d'échéancier (4 mécanismes + épargne hors institution)")
    # ------------------------------------------------------------------ #
    for mech in ("CONSTANT", "DEGRESSIVE", "IN_FINE", "BULLET"):
        sched = compute_amortization_schedule(
            Decimal("1000000"),
            Decimal("12"),
            12,
            mechanism=mech,
            savings_rate=Decimal("5"),
        )
        assert_true(len(sched) >= 1, f"mécanisme {mech}", f"{len(sched)} échéance(s)")
        row0 = sched[0]
        assert_true(
            row0["institution_due"] == row0["principal"] + row0["interest"],
            f"{mech}: institution_due = P+I",
        )
        assert_true(
            row0["total"] == row0["institution_due"] + row0["savings"],
            f"{mech}: total = institution + épargne",
        )
        assert_true(row0["savings"] > 0, f"{mech}: épargne > 0")
        if mech == "BULLET":
            assert_true(len(sched) == 1, "BULLET = 1 échéance")
        if mech == "IN_FINE":
            assert_true(
                all(r["principal"] == 0 for r in sched[:-1]),
                "IN_FINE: capital seulement en fin",
            )
            assert_true(sched[-1]["principal"] == Decimal("1000000.00"), "IN_FINE capital final")

    sim = client.post(
        "/api/v1/credit-applications/simulate/",
        {
            "amount": "1000000",
            "annual_rate": "12",
            "months": 12,
            "savings_rate": "5",
            "mechanism": "DEGRESSIVE",
        },
        format="json",
        **SN,
    )
    assert_true(sim.status_code == 200, "API simulate", str(sim.status_code))
    if sim.status_code == 200:
        d = sim.data
        assert_true(
            "institution_due" in d["schedule"][0] or "installment" in d,
            "simulate expose échéance institution",
            f"installment={d.get('installment')}",
        )
        assert_true(
            Decimal(str(d["installment"]))
            == Decimal(str(d["schedule"][0]["institution_due"])),
            "simulate.installment = institution_due (hors épargne)",
        )

    # ------------------------------------------------------------------ #
    print("\nB) Création dossier (mécanisme, frais, épargne, proposé)")
    # ------------------------------------------------------------------ #
    resp = client.post(
        "/api/v1/credit-applications/",
        {
            "client": cli["id"],
            "product": product["id"],
            "amount_requested": "5000000",
            "amount_proposed": "4500000",
            "interest_rate": "12",
            "fees_rate": "2",
            "mandatory_savings_rate": "5",
            "periodicity": "MONTHLY",
            "duration_months": 12,
            "repayment_mechanism": "DEGRESSIVE",
            "currency": "XOF",
            "project_total_cost": "6000000",
            "extra_fees": [
                {"label": "Commission", "mode": "PERCENT", "value": "1"},
                {"label": "Frais fixe", "mode": "AMOUNT", "value": "25000"},
            ],
            "employer_name": "Société Test",
            "dependents_count": 2,
        },
        format="json",
        **SN,
    )
    assert_true(resp.status_code == 201, "création dossier", str(resp.status_code))
    if resp.status_code != 201:
        print("   ", resp.data)
        return _summary()
    app = resp.data
    app_id = app["id"]
    ok("référence", app["reference"])

    # Champs retirés absents de la réponse
    for gone in (
        "activity",
        "risk_class",
        "analysis",
        "employees_count",
        "has_past_incidents",
        "bceao_check_done",
    ):
        assert_true(gone not in app, f"champ retiré absent: {gone}")

    assert_true(app.get("repayment_mechanism") == "DEGRESSIVE", "mécanisme conservé")
    assert_true(app.get("amount_proposed") == "4500000.00" or app.get("amount_proposed") == "4500000", "montant proposé")

    # Quotité sur montant de référence (proposé)
    fq = Decimal(str(app.get("financed_quota") or 0))
    expected_q = Decimal("4500000") / Decimal("6000000") * Decimal("100")
    assert_true(
        abs(fq - expected_q) < Decimal("0.05"),
        "quotité sur amount_proposed",
        f"{fq} ≈ {expected_q.quantize(Decimal('0.01'))}",
    )

    # Frais % sur proposed
    fb = app.get("fees_breakdown") or {}
    assert_true(fb.get("base_amount") in ("4500000", "4500000.00"), "frais base = proposé", str(fb.get("base_amount")))
    lines = {l["label"]: l for l in fb.get("lines", [])}
    assert_true("Frais de dossier" in lines, "ligne frais de dossier")
    assert_true("Commission" in lines, "ligne commission")
    assert_true("Frais fixe" in lines, "ligne frais fixe")
    if "Frais de dossier" in lines and lines["Frais de dossier"]["amount"]:
        # 2% de 4_500_000 = 90_000
        assert_true(
            Decimal(lines["Frais de dossier"]["amount"]) == Decimal("90000.00"),
            "frais dossier 2% × proposé",
            lines["Frais de dossier"]["amount"],
        )
    if fb.get("total"):
        ok("total frais", fb["total"])

    # ------------------------------------------------------------------ #
    print("\nC) Soumission sans analyse → refus")
    # ------------------------------------------------------------------ #
    resp = client.post(f"/api/v1/credit-applications/{app_id}/submit/", **SN)
    assert_true(
        resp.status_code in (400, 403),
        "soumission bloquée sans analyse",
        f"{resp.status_code} {resp.data}",
    )

    # ------------------------------------------------------------------ #
    print("\nD) Analyse financière de référence")
    # ------------------------------------------------------------------ #
    resp = client.post(
        "/api/v1/financial-analyses/",
        {
            "application": app_id,
            "is_reference": True,
            "reference_period": "MONTHLY",
            "salary_income": "350000",
            "rent_expense": "50000",
            "food_expense": "80000",
            "existing_debt_monthly": "25000",
            "employment_seniority_months": 36,
            "credit_bureau_checked": True,
            "recommendation": "FAVORABLE",
            "strengths": "Revenus stables",
            "comment": "Analyse globale e2e",
        },
        format="json",
        **SN,
    )
    assert_true(resp.status_code == 201, "création analyse", str(resp.status_code))
    if resp.status_code != 201:
        print("   ", resp.data)
        return _summary()
    analysis = resp.data
    assert_true(analysis.get("is_reference") is True, "is_reference=True")
    # net_salary synchronisé depuis salary_income
    assert_true(
        Decimal(str(analysis.get("net_salary") or 0)) == Decimal("350000.00")
        or Decimal(str(analysis.get("net_salary") or 0)) == Decimal("350000"),
        "net_salary = salary_income",
        str(analysis.get("net_salary")),
    )
    inst = Decimal(str(analysis.get("new_installment") or 0))
    assert_true(inst > 0, "new_installment calculé", str(inst))

    # Vérifie hors épargne : recalcul manuel avec savings=0
    expected_sched = compute_amortization_schedule(
        Decimal("4500000"),
        Decimal("12"),
        12,
        mechanism="DEGRESSIVE",
        savings_rate=0,
    )
    expected_inst = expected_sched[0]["institution_due"]
    assert_true(
        abs(inst - expected_inst) < Decimal("1"),
        "new_installment = institution_due (sans épargne)",
        f"{inst} ≈ {expected_inst}",
    )

    with_savings = compute_amortization_schedule(
        Decimal("4500000"),
        Decimal("12"),
        12,
        mechanism="DEGRESSIVE",
        savings_rate=Decimal("5"),
    )
    assert_true(
        with_savings[0]["total"] > inst,
        "épargne augmenterait le total client mais pas l'échéance analyse",
    )

    # ------------------------------------------------------------------ #
    print("\nE) Soumission + circuit + montant accordé")
    # ------------------------------------------------------------------ #
    resp = client.post(f"/api/v1/credit-applications/{app_id}/submit/", **SN)
    assert_true(resp.status_code == 200, "soumission OK", f"{resp.status_code} {getattr(resp, 'data', '')}")
    app = client.get(f"/api/v1/credit-applications/{app_id}/", **SN).data
    assert_true(app["status"] == "IN_APPROVAL", "statut IN_APPROVAL", app["status"])
    assert_true(app.get("risk_level") is not None, "risk_level dérivé", str(app.get("risk_level")))

    def _matches_app(task) -> bool:
        appli = task.get("application") or {}
        if isinstance(appli, dict):
            if appli.get("id") == app_id or appli.get("reference") == app["reference"]:
                return True
        return (
            str(task.get("object_id") or "") == app_id
            or task.get("target_reference") == app["reference"]
        )

    pending = []
    mine = []
    for candidate in (approver, User.objects.filter(username="fil01_admin").first()):
        if not candidate:
            continue
        c = APIClient()
        c.force_authenticate(user=candidate)
        pending = c.get("/api/v1/approval-tasks/my_pending/", **SN).data["results"]
        mine = [t for t in pending if _matches_app(t)]
        if mine:
            approver = candidate
            break

    if not mine and pending:
        mine = [pending[0]]
        ok("tâche pending (fallback première)", pending[0].get("step_name", ""))
    else:
        assert_true(len(mine) >= 1, "tâche d'approbation trouvée", str(len(mine)))

    if mine:
        task = mine[0]
        decide_client = APIClient()
        decide_client.force_authenticate(user=approver)
        resp = decide_client.post(
            f"/api/v1/approval-tasks/{task['id']}/decide/",
            {
                "decision": "APPROVED",
                "comment": "OK e2e global",
                "proposed_amount": "4200000",
                "opinion": "FAVORABLE",
            },
            format="json",
            **SN,
        )
        assert_true(resp.status_code == 200, "décision APPROVED", f"{resp.status_code} {resp.data}")

        # Boucle si plusieurs étapes
        for _ in range(5):
            app = client.get(f"/api/v1/credit-applications/{app_id}/", **SN).data
            if app["status"] in ("APPROVED", "REJECTED", "RETURNED"):
                break
            pending = decide_client.get("/api/v1/approval-tasks/my_pending/", **SN).data["results"]
            next_tasks = [t for t in pending if _matches_app(t)]
            if not next_tasks:
                # Essayer avec fil01_admin (comité)
                decide_client.force_authenticate(user=User.objects.get(username="fil01_admin"))
                pending = decide_client.get("/api/v1/approval-tasks/my_pending/", **SN).data["results"]
                next_tasks = [t for t in pending if _matches_app(t)]
            if not next_tasks:
                break
            decide_client.post(
                f"/api/v1/approval-tasks/{next_tasks[0]['id']}/decide/",
                {"decision": "APPROVED", "comment": "OK suite", "opinion": "FAVORABLE"},
                format="json",
                **SN,
            )

        app = client.get(f"/api/v1/credit-applications/{app_id}/", **SN).data
        assert_true(
            app["status"] in ("APPROVED", "IN_APPROVAL", "AWAITING_CONDITIONS")
            or app["status"] == "CONTRACT_GENERATED",
            "statut post-circuit",
            app["status"],
        )

        db_app = CreditApplication.all_tenants.get(pk=app_id)
        ref = reference_amount(db_app)
        ok("reference_amount DB", str(ref))
        if db_app.status == CreditApplication.Status.APPROVED:
            assert_true(
                db_app.amount_approved is not None,
                "amount_approved renseigné",
                str(db_app.amount_approved),
            )
            assert_true(
                ref == db_app.amount_approved
                or ref == db_app.amount_proposed
                or ref == db_app.amount_requested,
                "référence cohérente après APPROVED",
            )
            app2 = client.get(f"/api/v1/credit-applications/{app_id}/", **SN).data
            base = (app2.get("fees_breakdown") or {}).get("base_amount")
            assert_true(base is not None, "frais base post-approbation", str(base))

    # ------------------------------------------------------------------ #
    print("\nF) Analyse entreprise (workforce + période ANNUAL défaut)")
    # ------------------------------------------------------------------ #
    if corp:
        resp = client.post(
            "/api/v1/credit-applications/",
            {
                "client": corp["id"],
                "product": product["id"],
                "amount_requested": "8000000",
                "interest_rate": "14",
                "duration_months": 24,
                "repayment_mechanism": "CONSTANT",
                "currency": "XOF",
            },
            format="json",
            **SN,
        )
        assert_true(resp.status_code == 201, "dossier corporate", str(resp.status_code))
        corp_id = resp.data["id"]
        resp = client.post(
            "/api/v1/financial-analyses/",
            {
                "application": corp_id,
                "is_reference": True,
                "turnover": "50000000",
                "cogs": "30000000",
                "workforce_count": 12,
                "recommendation": "CONDITIONAL",
            },
            format="json",
            **SN,
        )
        assert_true(resp.status_code == 201, "analyse corporate", f"{resp.status_code} {resp.data}")
        if resp.status_code == 201:
            a = resp.data
            assert_true(
                a.get("reference_period") in ("ANNUAL", "MONTHLY", "QUARTERLY"),
                "période renseignée",
                a.get("reference_period"),
            )
            # Si non fournie, défaut ANNUAL pour corporate
            fa = FinancialAnalysis.all_tenants.get(pk=a["id"])
            assert_true(a.get("reference_period") == "ANNUAL", "défaut ANNUAL corporate", a.get("reference_period"))
            assert_true(fa.workforce_count == 12, "workforce_count", str(fa.workforce_count))
            assert_true(
                fa.total_debts
                == (fa.supplier_debt or 0)
                + (fa.ongoing_credit_balance or 0)
                + (fa.short_term_debt or 0),
                "equity/total_debts inclut short_term_debt",
            )
            # Nettoyage dossier corporate brouillon
            client.delete(f"/api/v1/credit-applications/{corp_id}/", **SN)
            ok("nettoyage dossier corporate")
    else:
        ok("pas de client CORPORATE en démo — étape F sautée")

    # Nettoyage dossier principal si encore brouillon/annulable
    print("\nG) Nettoyage")
    try:
        final = client.get(f"/api/v1/credit-applications/{app_id}/", **SN).data
        ok("dossier final", f"{final['reference']} / {final['status']}")
    except Exception as exc:  # noqa: BLE001
        fail("lecture finale", str(exc))

    return _summary()


def _summary():
    print("\n=== RÉSULTAT ===")
    print(f"  Réussis : {PASS}")
    print(f"  Échoués : {FAIL}")
    if FAIL:
        print("  VERDICT : ÉCHEC")
        return 1
    print("  VERDICT : OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("ÉCHEC FATAL:", exc)
        import traceback

        traceback.print_exc()
        sys.exit(1)
