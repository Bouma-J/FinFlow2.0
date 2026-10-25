from apps.notifications.services import (
    _alert_subject,
    _client_nom_prenom,
    _subject_tail,
)


def test_client_nom_prenom_is_last_then_first():
    client = type("C", (), {"last_name": "Dupont", "first_name": "Jean"})()
    assert _client_nom_prenom(client) == "Dupont Jean"


def test_credit_subject_tail_is_name_dash_amount():
    meta = {
        "kind": "CREDIT",
        "client_nom_prenom": "Dupont Jean",
        "amount_label": "5 000 000 XOF",
        "reference": "DOS-2026-0001",
    }
    assert _subject_tail(meta) == "Dupont Jean - 5 000 000 XOF"
    assert _alert_subject("[FIN_FLOW] Dossier en attente", meta) == (
        "[FIN_FLOW] Dossier en attente — Dupont Jean - 5 000 000 XOF"
    )


def test_main_levee_subject_is_label_and_client():
    meta = {
        "kind": "MAIN_LEVEE",
        "client_nom_prenom": "Dupont Jean",
        "reference": "ML-12",
    }
    assert _subject_tail(meta) == "Dossier de main levée - Dupont Jean"
    assert _alert_subject("[FIN_FLOW] Dossier en attente", meta) == (
        "[FIN_FLOW] Dossier de main levée - Dupont Jean"
    )


def test_dation_subject_is_label_and_client():
    meta = {
        "kind": "DATION",
        "client_nom_prenom": "Koné Awa",
        "reference": "DAT-3",
    }
    assert _subject_tail(meta) == "Dossier de dation - Koné Awa"
    assert _alert_subject("[FIN_FLOW] Dossier en attente", meta) == (
        "[FIN_FLOW] Dossier de dation - Koné Awa"
    )
