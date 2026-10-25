"""
Services d'intégration Core Banking.

L'envoi réel dépend du protocole/filiale ; cette couche fournit
l'orchestration commune : idempotence, journalisation, gestion des
tentatives. Les adaptateurs concrets (REST/SOAP/SFTP/BATCH) doivent
implémenter `send` et les opérations métier normalisées.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import CoreBankingConnector, IntegrationLog
from .perfect_defaults import (
    DEFAULT_AUTH_SCOPE,
    PERFECT_ENDPOINTS,
)

logger = logging.getLogger("finflow")


class CoreBankingError(Exception):
    """Erreur métier d'accès au Core Banking (blocage strict)."""


# Messages exposés à l'utilisateur (jamais de détail technique / HTTP / stack).
USER_MSG_CBS_UNAVAILABLE = (
    "Le système bancaire est temporairement inaccessible. "
    "Veuillez réessayer dans quelques instants."
)
USER_MSG_CBS_AUTH = (
    "La connexion au système bancaire a échoué. "
    "Contactez l'administrateur si le problème persiste."
)
USER_MSG_CBS_NOT_CONFIGURED = (
    "La consultation n'est pas disponible pour votre filiale. "
    "Contactez l'administrateur."
)
USER_MSG_CBS_GENERIC = (
    "Impossible de consulter la situation du crédit pour le moment. "
    "Veuillez réessayer ultérieurement. Si le problème persiste, "
    "contactez le support."
)

_CBS_TECHNICAL_MARKERS = (
    "http ",
    "traceback",
    "exception",
    "stack",
    "sslerror",
    "connectionerror",
    "timeout",
    "timed out",
    "status_code",
    "requests.",
    "urllib",
    "socket",
    "errno",
    "json.decode",
    "at 0x",
    "/gateway",
    "/api/",
    "crd/",
    "adh/",
    "bearer",
    "oauth",
    "client_secret",
    "bad credentials",
    "max retries",
    "connection refused",
    "name or service not known",
    "temporary failure",
)


def _cbs_message_looks_technical(message: str) -> bool:
    low = (message or "").strip().lower()
    if not low:
        return True
    if any(marker in low for marker in _CBS_TECHNICAL_MARKERS):
        return True
    if "://" in low:
        return True
    # Codes HTTP explicites (ex. « HTTP 502 », « (HTTP 500) »)
    compact = low.replace(" ", "")
    for code in ("http400", "http401", "http403", "http404", "http500", "http502", "http503", "http504"):
        if code in compact:
            return True
    return False


def user_message_for_cbs_error(exc: BaseException | str | None) -> str:
    """
    Traduit une erreur CBS en message sûr pour l'UI.

    Les détails techniques restent dans les logs applicatifs et
    ``IntegrationLog`` ; ne jamais renvoyer ``str(exc)`` tel quel.
    """
    raw = str(exc or "").strip()
    low = raw.lower()

    connectivity = (
        "joindre",
        "timeout",
        "timed out",
        "connection",
        "connect refused",
        "unreachable",
        "name or service",
        "max retries",
        "network",
        "ssl",
        "gateway",
        "temporairement",
        "indisponible",
    )
    if any(m in low for m in connectivity) or any(
        code in low.replace(" ", "")
        for code in ("http502", "http503", "http504")
    ):
        return USER_MSG_CBS_UNAVAILABLE

    auth = (
        "authentif",
        "token",
        "credentials",
        "unauthorized",
        "jeton",
        "bad credentials",
        "401",
        "403",
    )
    if any(m in low for m in auth):
        return USER_MSG_CBS_AUTH

    config = (
        "aucun connecteur",
        "aucune filiale",
        "configurez",
        "connecteur core banking",
    )
    if any(m in low for m in config):
        return USER_MSG_CBS_NOT_CONFIGURED

    # Court message métier CBS déjà lisible (ex. « Adhérent introuvable ! »)
    if raw and len(raw) <= 160 and not _cbs_message_looks_technical(raw):
        return raw

    return USER_MSG_CBS_GENERIC


# Opérations normalisées
OP_PING = "PING"
OP_GET_LOAN_STATUS = "GET_LOAN_STATUS"
OP_GET_CLIENT_OUTSTANDING = "GET_CLIENT_OUTSTANDING"
OP_GET_CLIENT_SITUATION = "GET_CLIENT_SITUATION"
OP_SUBMIT_CREDIT = "SUBMIT_CREDIT"
OP_LIST_OVERDUE_CREDITS = "LIST_OVERDUE_CREDITS"

# Chemins Perfect API (modifiables via mapping_rules.endpoints).
DEFAULT_AUTH_PATH = PERFECT_ENDPOINTS["authentification"]
DEFAULT_ADH_SITUATION_PATH = PERFECT_ENDPOINTS["adh_situation"]
DEFAULT_CRD_SIMPLE_PATH = PERFECT_ENDPOINTS["crd_simple"]
DEFAULT_CRD_SITUATION_PATH = PERFECT_ENDPOINTS["crd_situation"]
DEFAULT_CRD_IMPAYES_PATH = PERFECT_ENDPOINTS["crd_impayes"]


class BaseAdapter:
    """Interface d'un adaptateur de connecteur Core Banking."""

    def __init__(self, connector: CoreBankingConnector):
        self.connector = connector

    def send(self, operation: str, payload: dict) -> dict:
        raise NotImplementedError


class SimulatedAdapter(BaseAdapter):
    """Adaptateur de démonstration (à remplacer par les intégrations réelles).

    Comportement pilotable via `connector.mapping_rules.simulate` :
    - loan_unsettled_refs : liste de refs considérées non soldées
    - loan_settled_default : bool (défaut True)
    - client_outstanding_default : montant (défaut "0")
    - client_outstanding_by_id : {cbs_client_id: montant}
    """

    def send(self, operation: str, payload: dict) -> dict:
        logger.info("Envoi simulé vers %s : %s", self.connector, operation)
        simulate = (self.connector.mapping_rules or {}).get("simulate", {})

        if operation == OP_PING:
            return {
                "status": "ACK",
                "external_reference": f"CBS-PING-{self.connector.id}",
            }

        if operation == OP_GET_LOAN_STATUS:
            loan_ref = str(payload.get("loan_ref") or "").strip()
            by_ref = simulate.get("loan_situation_by_ref") or {}
            if loan_ref and loan_ref in by_ref:
                raw = dict(by_ref[loan_ref])
                raw.setdefault("responseCode", 200)
                raw.setdefault("refDemande", loan_ref)
                raw.setdefault("simulated", True)
                settled, outstanding = _normalize_credit_schedule(raw)
                overdue = compute_cbs_overdue(raw)
                return {
                    "status": "ACK",
                    "settled": overdue["settled"],
                    "outstanding": str(overdue["outstanding"] or outstanding),
                    "days_overdue": overdue["days_overdue"],
                    "overdue_amount": str(overdue["overdue_amount"]),
                    "currency": payload.get("currency") or "XOF",
                    "external_reference": f"CBS-LOAN-{loan_ref or 'NA'}",
                    "schedule": raw.get("datas") or [],
                    "raw": raw,
                }
            portfolio_row = _sim_portfolio_row_for_ref(simulate, loan_ref)
            if portfolio_row is not None:
                raw = _situation_from_portfolio_row(portfolio_row, loan_ref)
                overdue = compute_cbs_overdue(raw)
                return {
                    "status": "ACK",
                    "settled": overdue["settled"],
                    "outstanding": str(overdue["outstanding"]),
                    "days_overdue": overdue["days_overdue"],
                    "overdue_amount": str(overdue["overdue_amount"]),
                    "currency": payload.get("currency") or "XOF",
                    "external_reference": f"CBS-LOAN-{loan_ref or 'NA'}",
                    "num_demande": str(portfolio_row.get("numDemande") or ""),
                    "ref_demande": str(
                        portfolio_row.get("refDemande") or loan_ref
                    ),
                    "num_contrat": str(portfolio_row.get("numContrat") or ""),
                    "schedule": raw.get("datas") or [],
                    "raw": raw,
                }
            unsettled = {
                str(x).strip() for x in (simulate.get("loan_unsettled_refs") or [])
            }
            default_settled = bool(simulate.get("loan_settled_default", True))
            # Convention recette : préfixe UNSOLDE- / UNSETTLED-
            force_open = loan_ref.upper().startswith(("UNSOLDE-", "UNSETTLED-"))
            settled = (
                False
                if (force_open or loan_ref in unsettled)
                else default_settled
            )
            outstanding = Decimal("0") if settled else Decimal(
                str(simulate.get("loan_outstanding_default", "100000"))
            )
            overdue_days = int(simulate.get("loan_overdue_days_default") or 40)
            due = date.today() - timedelta(days=overdue_days)
            datas = (
                []
                if settled
                else [
                    {
                        "echeance": 1,
                        "date": due.isoformat(),
                        "montantCapital": float(outstanding),
                        "montantInteret": 0,
                        "montantTotal": float(outstanding),
                        "statut": "En attente",
                    }
                ]
            )
            raw = {
                "simulated": True,
                "loan_ref": loan_ref,
                "responseCode": 200,
                "refDemande": loan_ref,
                "datas": datas,
                "context": "CREDIT SITUATION",
            }
            overdue = compute_cbs_overdue(raw)
            return {
                "status": "ACK",
                "settled": overdue["settled"] if not settled else True,
                "outstanding": str(outstanding),
                "days_overdue": 0 if settled else overdue["days_overdue"],
                "overdue_amount": "0" if settled else str(overdue["overdue_amount"]),
                "currency": payload.get("currency") or "XOF",
                "external_reference": f"CBS-LOAN-{loan_ref or 'NA'}",
                "schedule": datas,
                "raw": raw,
            }

        if operation == OP_LIST_OVERDUE_CREDITS:
            rows = _sim_portfolio_rows(simulate)
            overdue_only = payload.get("overdue_only", True)
            credits = []
            for row in rows:
                snap = credit_snapshot_from_cbs_row(row)
                if not snap.get("loan_ref"):
                    continue
                if overdue_only and int(snap.get("days_overdue") or 0) <= 0:
                    continue
                credits.append({**row, **snap})
            return {
                "status": "ACK",
                "credits": credits,
                "datas": credits,
                "external_reference": f"CBS-PORTFOLIO-{self.connector.id}",
                "raw": {"simulated": True, "credits": credits},
            }

        if operation == OP_GET_CLIENT_OUTSTANDING:
            client_id = str(payload.get("cbs_client_id") or "").strip()
            by_id = simulate.get("client_outstanding_by_id") or {}
            if client_id and client_id in by_id:
                total = Decimal(str(by_id[client_id]))
            else:
                total = Decimal(
                    str(simulate.get("client_outstanding_default", "1000000"))
                )
            return {
                "status": "ACK",
                "total_outstanding": str(total),
                "currency": payload.get("currency") or "XOF",
                "breakdown": [],
                "external_reference": f"CBS-CLIENT-{client_id or 'NA'}",
                "raw": {"simulated": True, "cbs_client_id": client_id},
            }

        if operation == OP_GET_CLIENT_SITUATION:
            return self._simulate_client_situation(payload, simulate)

        if operation == OP_SUBMIT_CREDIT:
            return self._simulate_submit_credit(payload, simulate)

        return {
            "status": "ACK",
            "external_reference": f"CBS-{payload.get('reference', '')}",
        }

    def _simulate_submit_credit(self, payload: dict, simulate: dict) -> dict:
        external_id = str(payload.get("externalId") or "EXT").strip()
        failures = {
            str(x).strip() for x in (simulate.get("credit_fail_external_ids") or [])
        }
        if external_id in failures or simulate.get("credit_submit_fail"):
            raise CoreBankingError(
                str(
                    simulate.get("credit_fail_message")
                    or "Limite de crédit insuffisante !"
                )
            )
        amount = payload.get("montantDemande") or 0
        currency = payload.get("codeDevise") or "XOF"
        num_contrat = f"CONTRAT-SIM-{external_id}"
        raw = {
            "responseCode": 200,
            "message": "Opération effectuée avec succès ! (simulé)",
            "externalId": external_id,
            "numDemande": f"DEM-{external_id[-6:]}",
            "refDemande": f"REF-{external_id}",
            "numContrat": num_contrat,
            "limitCredit": float(
                simulate.get("credit_limit_default", max(float(amount) * 1.5, 1))
            ),
            "montant": float(amount),
            "codeDevise": currency,
            "dateOperation": str(simulate.get("credit_date") or "2026-01-15"),
            "context": "CREDIT DE LA DEMANDE JUSQU'AU DEBLOQUAGE",
            "simulated": True,
        }
        return {
            "status": "ACK",
            "external_reference": num_contrat,
            "num_demande": raw["numDemande"],
            "ref_demande": raw["refDemande"],
            "num_contrat": num_contrat,
            "limit_credit": raw["limitCredit"],
            "montant": raw["montant"],
            "raw": raw,
        }

    def _simulate_client_situation(self, payload: dict, simulate: dict) -> dict:
        code = str(payload.get("codeAdherent") or "").strip()
        num_manuel = str(payload.get("numManuel") or "").strip()
        num_piece = str(payload.get("numPieceIdentite") or "").strip()
        id_nat = str(payload.get("identificationNationale") or "").strip()
        num_carte = str(
            payload.get("numCarteOperateurEconomique") or ""
        ).strip()
        client_type = str(
            payload.get("clientType") or payload.get("client_type") or ""
        ).strip().upper()
        by_id = simulate.get("client_situation_by_id") or {}
        raw = None
        for key in (code, num_manuel, num_piece, id_nat, num_carte):
            if key and key in by_id:
                raw = dict(by_id[key])
                break
        if raw is None:
            if not (code or num_manuel or num_piece or id_nat or num_carte):
                raise CoreBankingError(
                    "Au moins un identifiant CBS est requis "
                    "(codeAdherent, numManuel, numPieceIdentite, "
                    "identificationNationale ou numCarteOperateurEconomique)."
                )
            if simulate.get("client_situation_not_found"):
                raise CoreBankingError("Adhérent introuvable !")
            is_corporate = client_type == "CORPORATE" or bool(id_nat or num_carte)
            raw = {
                "responseCode": 200,
                "message": "Opération effectuée avec succès ! (simulé)",
                "codeAdherent": code or ("E00999" if is_corporate else "A0012345"),
                "numManuel": num_manuel or "M00987",
                "limitCredit": float(
                    simulate.get("client_limit_credit_default", 500000)
                ),
                "estValide": bool(simulate.get("client_est_valide_default", True)),
                "idPointService": "PS01",
                "nomPointService": "Agence Principale",
                "telephone": "+2250700000000",
                "email": (
                    "contact@demo.ci"
                    if is_corporate
                    else "awa.kone@example.com"
                ),
                "boitePostale": "N/A",
                "ville": "Abidjan",
                "adresse": "Cocody, Angré 8e tranche",
                "dateInscription": "2020-01-15",
                "context": "ADHERENT SITUATION",
            }
            if is_corporate:
                corp_name = simulate.get(
                    "client_raison_sociale_default", "SODECI Démo"
                )
                raw.update(
                    {
                        "nom": corp_name,
                        "nomAdherent": corp_name,
                        "sigle": "SDC",
                        "identificationNationale": id_nat or "IFU-CI-001",
                        "numCarteOperateurEconomique": num_carte or "RCCM-CI-001",
                        "numOrdre": "ORD-001",
                        "dateCreation": "2015-06-01",
                        "siegeSocial": "Plateau, Abidjan",
                        "idSecteurActivite": "COMMERCE",
                        "idTypeClient": "ENT",
                        "nbreSignature": 2,
                    }
                )
            else:
                default_name = simulate.get("client_nom_default", "Koné Awa Démo")
                parts = str(default_name).split(None, 1)
                raw.update(
                    {
                        "nom": parts[0] if parts else default_name,
                        "prenoms": parts[1] if len(parts) > 1 else "",
                        "nomAdherent": default_name,
                        "numPieceIdentite": num_piece or "CI1234567890",
                        "dateNaissance": "1990-03-12",
                        "lieuNaissance": "Bouaké",
                        "civilite": "Mme",
                        "statutMatrimonial": "Célibataire",
                        "nomConjoint": "N/A",
                        "dateEtablissementPiece": "2018-01-10",
                        "dateExpirationPiece": "2028-01-10",
                        "idProfession": "COMMERCANT",
                        "idNationalite": "IVOIRIENNE",
                    }
                )
        code_http = int(raw.get("responseCode") or 200)
        if code_http >= 400:
            raise CoreBankingError(
                str(raw.get("message") or "Adhérent introuvable !")
            )
        return {
            "status": "ACK",
            "external_reference": f"CBS-SIT-{raw.get('codeAdherent') or 'NA'}",
            "raw": {**raw, "simulated": True},
        }


class RestAdapter(BaseAdapter):
    """Adaptateur REST (API Perfect / gateway).

    Auth Perfect (prioritaire) :
    - jeton statique ``auth_config.access_token`` / ``accessToken`` / ``token``, ou
    - ``POST …/gateway-perfect/authentification`` (form-urlencoded :
      ``username``, ``password``, ``scope=perfect``) → ``accessToken``.

    Compat OAuth legacy : ``token_url`` + ``grant_type`` (client_credentials).

    Endpoints configurables dans ``mapping_rules.endpoints`` :
    - ``authentification`` (défaut ``gateway-perfect/authentification``)
    - ``adh_situation`` (défaut ``gateway-perfect/adh/situation``)
    - ``crd_simple`` (défaut ``gateway-perfect/crd/simple``)
    - ``crd_situation`` (défaut ``gateway-perfect/crd/situation``)
    - ``crd_impayes`` (défaut ``gateway-perfect/crd/impayes``)
    """

    def send(self, operation: str, payload: dict) -> dict:
        if operation == OP_PING:
            # Ping réel : obtient un jeton (prouve URL + auth + SSL).
            token = self._resolve_bearer_token()
            return {
                "status": "ACK",
                "external_reference": f"CBS-PING-{self.connector.id}",
                "auth": "ok",
                "token_len": len(token),
            }
        if operation == OP_GET_CLIENT_SITUATION:
            return self._adh_situation(payload)
        if operation == OP_SUBMIT_CREDIT:
            return self._crd_simple(payload)
        if operation == OP_GET_LOAN_STATUS:
            return self._crd_situation(payload)
        if operation == OP_LIST_OVERDUE_CREDITS:
            return self._crd_impayes(payload)
        # Autres ops REST : non encore branchées → simulation locale.
        return SimulatedAdapter(self.connector).send(operation, payload)

    def _ssl_verify(self) -> bool:
        """Vérification TLS (défaut True). Désactivable via mapping_rules.verify_ssl."""
        rules = self.connector.mapping_rules or {}
        if "verify_ssl" in rules:
            return bool(rules.get("verify_ssl"))
        return True

    def _http_post(self, url: str, *, timeout: int, headers: dict, json=None, data=None, auth=None):
        import requests

        kwargs = {
            "url": url,
            "headers": headers,
            "timeout": timeout,
            "verify": self._ssl_verify(),
        }
        if json is not None:
            kwargs["json"] = json
        if data is not None:
            kwargs["data"] = data
        if auth is not None:
            kwargs["auth"] = auth
        return requests.post(**kwargs)

    def _http_get(self, url: str, *, timeout: int, headers: dict):
        import requests

        return requests.get(
            url,
            headers=headers,
            timeout=timeout,
            verify=self._ssl_verify(),
        )

    def fetch_ref_list(self, endpoint_key: str, *, default_path: str = "") -> list[dict]:
        """GET Perfect ``ref/*`` → liste ``[{id, code, libelle}, …]``."""
        import requests

        path = self._endpoint(endpoint_key, default_path or endpoint_key)
        url = self._build_url(path)
        token = self._resolve_bearer_token()
        timeout = self.connector.timeout_seconds or 30
        try:
            resp = self._http_get(
                url,
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        except requests.RequestException as exc:
            raise CoreBankingError(
                f"Impossible de joindre le référentiel CBS ({endpoint_key}) ({exc})."
            ) from exc

        payload: dict = {}
        if resp.content:
            try:
                parsed = resp.json()
                if isinstance(parsed, dict):
                    payload = parsed
            except ValueError as exc:
                raise CoreBankingError(
                    f"Réponse référentiel CBS non JSON ({endpoint_key}, "
                    f"HTTP {resp.status_code})."
                ) from exc

        if resp.status_code >= 400:
            raise CoreBankingError(
                str(
                    payload.get("message")
                    or payload.get("error")
                    or f"Échec référentiel CBS {endpoint_key} (HTTP {resp.status_code})."
                )
            )

        datas = payload.get("datas")
        if datas is None and isinstance(payload.get("data"), list):
            datas = payload.get("data")
        # Vision renvoie parfois datas: null (liste vide côté CBS)
        if datas is None:
            datas = []
        if not isinstance(datas, list):
            raise CoreBankingError(
                f"Référentiel CBS {endpoint_key} : champ datas manquant ou invalide."
            )

        rows: list[dict] = []
        for item in datas:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("id") or "").strip()
            code = str(item.get("code") or "").strip()
            label = str(
                item.get("libelle") or item.get("label") or item.get("name") or ""
            ).strip()
            if not rid and not code:
                continue
            rows.append({"id": rid or code, "code": code or rid, "libelle": label})
        return rows

    def _crd_situation(self, payload: dict) -> dict:
        """POST Perfect ``crd/situation`` → solde / échéancier crédit."""
        import requests

        ref = str(
            payload.get("refDemande")
            or payload.get("loan_ref")
            or payload.get("ref_demande")
            or ""
        ).strip()
        if not ref:
            raise CoreBankingError(
                "Référence demande crédit CBS (refDemande) manquante."
            )

        body = {"refDemande": ref}
        for src, dest in (
            ("codeAdherent", "codeAdherent"),
            ("cbs_client_id", "codeAdherent"),
            ("numManuel", "numManuel"),
            ("numPieceIdentite", "numPieceIdentite"),
        ):
            value = str(payload.get(src) or "").strip()
            if value and dest not in body:
                body[dest] = value

        url = self._build_url(
            self._endpoint("crd_situation", DEFAULT_CRD_SITUATION_PATH)
        )
        token = self._resolve_bearer_token()
        timeout = self.connector.timeout_seconds or 30
        try:
            import requests

            resp = self._http_post(
                url,
                timeout=timeout,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        except requests.RequestException as exc:
            raise CoreBankingError(
                f"Impossible de joindre le CBS (situation crédit) ({exc})."
            ) from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError as exc:
            raise CoreBankingError(
                f"Réponse CBS non JSON (HTTP {resp.status_code})."
            ) from exc

        if not isinstance(data, dict):
            raise CoreBankingError("Réponse CBS situation crédit invalide.")

        code_http = int(data.get("responseCode") or resp.status_code or 0)
        if resp.status_code >= 400 or code_http >= 400:
            raise CoreBankingError(
                str(
                    data.get("message")
                    or f"Échec situation crédit CBS (HTTP {resp.status_code})."
                )
            )

        settled, outstanding = _normalize_credit_schedule(data)
        currency = (
            str(data.get("codeDevise") or payload.get("currency") or "XOF")
            .strip()
            .upper()
        )
        external = str(
            data.get("numContrat")
            or data.get("refDemande")
            or data.get("numDemande")
            or ref
        ).strip()
        return {
            "status": "ACK",
            "settled": settled,
            "outstanding": str(outstanding),
            "currency": currency,
            "external_reference": external,
            "num_demande": str(data.get("numDemande") or ""),
            "ref_demande": str(data.get("refDemande") or ref),
            "num_contrat": str(data.get("numContrat") or ""),
            "montant": data.get("montant"),
            "schedule": data.get("datas") or [],
            "raw": data,
        }

    def _crd_impayes(self, payload: dict) -> dict:
        """POST Perfect ``crd/impayes`` → liste des crédits / impayés."""
        import requests

        body = {}
        if payload.get("overdue_only", True):
            body["impayes"] = True
            body["uniquementImpayes"] = True
        for src, dest in (
            ("idPointService", "idPointService"),
            ("codeAdherent", "codeAdherent"),
        ):
            value = str(payload.get(src) or "").strip()
            if value:
                body[dest] = value

        url = self._build_url(
            self._endpoint("crd_impayes", DEFAULT_CRD_IMPAYES_PATH)
        )
        token = self._resolve_bearer_token()
        timeout = self.connector.timeout_seconds or 30
        try:
            import requests

            resp = self._http_post(
                url,
                timeout=timeout,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        except requests.RequestException as exc:
            raise CoreBankingError(
                f"Impossible de joindre le CBS (liste des crédits) ({exc})."
            ) from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError as exc:
            raise CoreBankingError(
                f"Réponse CBS non JSON (HTTP {resp.status_code})."
            ) from exc

        if resp.status_code >= 400:
            message = ""
            if isinstance(data, dict):
                message = str(data.get("message") or "")
            raise CoreBankingError(
                message
                or (
                    "Échec liste des crédits CBS "
                    f"(HTTP {resp.status_code}). Vérifiez l'endpoint "
                    "crd_impayes du connecteur."
                )
            )

        if isinstance(data, list):
            data = {"datas": data, "responseCode": resp.status_code}
        if not isinstance(data, dict):
            raise CoreBankingError("Réponse CBS liste des crédits invalide.")

        code_http = int(data.get("responseCode") or resp.status_code or 0)
        if code_http >= 400:
            raise CoreBankingError(
                str(
                    data.get("message")
                    or f"Échec liste des crédits CBS (HTTP {code_http})."
                )
            )

        credits = normalize_cbs_credit_rows(data)
        return {
            "status": "ACK",
            "credits": credits,
            "datas": data.get("datas") or credits,
            "external_reference": f"CBS-PORTFOLIO-{self.connector.id}",
            "raw": data,
        }

    def _crd_simple(self, payload: dict) -> dict:
        import requests

        required = [
            "externalId",
            "callbackUrl",
            "idPointService",
            "idPeriodicite",
            "taux",
            "nombreEcheance",
            "idObjetFinancement",
            "idGestionnaire",
            "idProduitCrd",
            "idProduitRemb",
            "montantDemande",
            "codeDevise",
        ]
        missing = [k for k in required if payload.get(k) in (None, "")]
        if missing:
            raise CoreBankingError(
                "Payload mise en place CBS incomplet : " + ", ".join(missing)
            )
        if not (
            payload.get("codeAdherent")
            or payload.get("numManuel")
            or payload.get("numPieceIdentite")
        ):
            raise CoreBankingError(
                "Au moins un identifiant adhérent est requis "
                "(codeAdherent, numManuel ou numPieceIdentite)."
            )

        url = self._build_url(
            self._endpoint("crd_simple", DEFAULT_CRD_SIMPLE_PATH)
        )
        token = self._resolve_bearer_token()
        timeout = self.connector.timeout_seconds or 30
        try:
            import requests

            resp = self._http_post(
                url,
                timeout=timeout,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        except requests.RequestException as exc:
            raise CoreBankingError(
                f"Impossible de joindre le CBS pour la mise en place ({exc})."
            ) from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError as exc:
            raise CoreBankingError(
                f"Réponse CBS non JSON (HTTP {resp.status_code})."
            ) from exc

        if not isinstance(data, dict):
            raise CoreBankingError("Réponse CBS mise en place invalide.")

        code_http = int(data.get("responseCode") or resp.status_code or 0)
        if resp.status_code >= 400 or code_http >= 400:
            raise CoreBankingError(
                str(
                    data.get("message")
                    or f"Échec mise en place CBS (HTTP {resp.status_code})."
                )
            )

        num_contrat = str(data.get("numContrat") or "").strip()
        return {
            "status": "ACK",
            "external_reference": num_contrat
            or str(data.get("refDemande") or payload.get("externalId") or ""),
            "num_demande": str(data.get("numDemande") or ""),
            "ref_demande": str(data.get("refDemande") or ""),
            "num_contrat": num_contrat,
            "limit_credit": data.get("limitCredit"),
            "montant": data.get("montant"),
            "raw": data,
        }

    def _adh_situation(self, payload: dict) -> dict:
        import requests

        code = str(payload.get("codeAdherent") or "").strip()
        num_manuel = str(payload.get("numManuel") or "").strip()
        num_piece = str(payload.get("numPieceIdentite") or "").strip()
        id_nat = str(payload.get("identificationNationale") or "").strip()
        num_carte = str(
            payload.get("numCarteOperateurEconomique") or ""
        ).strip()
        if not (code or num_manuel or num_piece or id_nat or num_carte):
            raise CoreBankingError(
                "Au moins un identifiant CBS est requis "
                "(codeAdherent, numManuel, numPieceIdentite, "
                "identificationNationale ou numCarteOperateurEconomique)."
            )

        body = {}
        if code:
            body["codeAdherent"] = code
        if num_manuel:
            body["numManuel"] = num_manuel
        if num_piece:
            body["numPieceIdentite"] = num_piece
        if id_nat:
            body["identificationNationale"] = id_nat
        if num_carte:
            body["numCarteOperateurEconomique"] = num_carte

        url = self._build_url(
            self._endpoint("adh_situation", DEFAULT_ADH_SITUATION_PATH)
        )
        token = self._resolve_bearer_token()
        timeout = self.connector.timeout_seconds or 30
        try:
            import requests

            resp = self._http_post(
                url,
                timeout=timeout,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        except requests.RequestException as exc:
            raise CoreBankingError(
                f"Impossible de joindre le CBS ({exc})."
            ) from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError as exc:
            raise CoreBankingError(
                f"Réponse CBS non JSON (HTTP {resp.status_code})."
            ) from exc

        if not isinstance(data, dict):
            raise CoreBankingError("Réponse CBS invalide.")

        code_http = int(data.get("responseCode") or resp.status_code or 0)
        if resp.status_code >= 400 or code_http >= 400:
            raise CoreBankingError(
                str(data.get("message") or f"Échec CBS (HTTP {resp.status_code}).")
            )

        return {
            "status": "ACK",
            "external_reference": f"CBS-SIT-{data.get('codeAdherent') or 'NA'}",
            "raw": data,
        }

    def _endpoint(self, key: str, default: str) -> str:
        endpoints = (self.connector.mapping_rules or {}).get("endpoints") or {}
        path = str(endpoints.get(key) or default).strip()
        return path.lstrip("/")

    def _build_url(self, path: str) -> str:
        base = (self.connector.base_url or "").rstrip("/")
        if not base:
            raise CoreBankingError(
                "URL de base du connecteur CBS manquante. "
                "Renseignez-la dans Administration → Connecteurs CBS."
            )
        return f"{base}/{path}"

    def _resolve_bearer_token(self) -> str:
        auth = self.connector.get_auth_config_decrypted()
        for key in ("access_token", "accessToken", "token", "bearer_token"):
            value = str(auth.get(key) or "").strip()
            if value:
                return value

        username = str(auth.get("username") or "").strip()
        password = str(auth.get("password") or "")
        # Flux Perfect documenté : username + password + scope=perfect.
        if username and password:
            return self._fetch_perfect_access_token(username, password)

        token_url = str(auth.get("token_url") or "").strip()
        if token_url:
            return self._fetch_oauth_access_token(token_url)

        raise CoreBankingError(
            "Authentification CBS manquante : renseignez username/password "
            "(Perfect POST …/authentification), ou un access_token / token_url."
        )

    def _auth_url(self) -> str:
        """URL d'authentification Perfect (token_url override ou endpoint défaut)."""
        auth = self.connector.get_auth_config_decrypted()
        explicit = str(auth.get("token_url") or "").strip()
        if explicit:
            return explicit
        return self._build_url(
            self._endpoint("authentification", DEFAULT_AUTH_PATH)
        )

    def _fetch_perfect_access_token(self, username: str, password: str) -> str:
        """POST form-urlencoded → accessToken (doc Perfect authentification)."""
        import requests

        auth = self.connector.get_auth_config_decrypted()
        scope = str(auth.get("scope") or DEFAULT_AUTH_SCOPE).strip() or DEFAULT_AUTH_SCOPE
        url = self._auth_url()
        timeout = self.connector.timeout_seconds or 30
        try:
            resp = self._http_post(
                url,
                timeout=timeout,
                data={
                    "username": username,
                    "password": password,
                    "scope": scope,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except requests.RequestException as exc:
            raise CoreBankingError(
                f"Échec d'authentification Perfect ({exc})."
            ) from exc

        payload: dict = {}
        if resp.content:
            try:
                parsed = resp.json()
                if isinstance(parsed, dict):
                    payload = parsed
            except ValueError:
                payload = {}

        token = str(
            payload.get("accessToken")
            or payload.get("access_token")
            or payload.get("token")
            or ""
        ).strip()
        if resp.status_code >= 400 or not token:
            detail = (
                payload.get("error_description")
                or payload.get("error")
                or payload.get("message")
                or ""
            )
            if not detail:
                detail = (
                    f"HTTP {resp.status_code} sur {url}"
                    if resp.status_code >= 400
                    else "Impossible d'obtenir un jeton Perfect (Bad credentials ?)."
                )
            raise CoreBankingError(str(detail))
        return token

    def _fetch_oauth_access_token(self, token_url: str) -> str:
        """Compat OAuth2 client_credentials / password (hors flux Perfect)."""
        import requests

        auth = self.connector.get_auth_config_decrypted()
        timeout = self.connector.timeout_seconds or 30
        grant = str(auth.get("grant_type") or "client_credentials").strip()
        data = {"grant_type": grant}
        if grant == "password":
            data["username"] = auth.get("username") or ""
            data["password"] = auth.get("password") or ""
        client_id = auth.get("client_id")
        client_secret = auth.get("client_secret")
        try:
            if client_id and client_secret:
                resp = self._http_post(
                    token_url,
                    timeout=timeout,
                    data=data,
                    headers={},
                    auth=(str(client_id), str(client_secret)),
                )
            else:
                if auth.get("username"):
                    data.setdefault("username", auth["username"])
                if auth.get("password"):
                    data.setdefault("password", auth["password"])
                if client_id:
                    data["client_id"] = client_id
                if client_secret:
                    data["client_secret"] = client_secret
                resp = self._http_post(
                    token_url,
                    timeout=timeout,
                    data=data,
                    headers={},
                )
            payload = resp.json() if resp.content else {}
        except (requests.RequestException, ValueError) as exc:
            raise CoreBankingError(
                f"Échec d'obtention du token CBS ({exc})."
            ) from exc

        token = str(
            payload.get("access_token")
            or payload.get("accessToken")
            or payload.get("token")
            or ""
        ).strip()
        if resp.status_code >= 400 or not token:
            raise CoreBankingError(
                str(
                    payload.get("error_description")
                    or payload.get("message")
                    or "Impossible d'obtenir un jeton CBS."
                )
            )
        return token


def get_adapter(connector: CoreBankingConnector) -> BaseAdapter:
    """Choisit l'adaptateur selon le protocole / la config."""
    rules = connector.mapping_rules or {}
    if rules.get("force_simulate"):
        return SimulatedAdapter(connector)
    if connector.protocol == CoreBankingConnector.Protocol.REST:
        # Sans URL : reste en simulation (dev / démo).
        if (connector.base_url or "").strip():
            return RestAdapter(connector)
    return SimulatedAdapter(connector)


def resolve_active_connector(tenant_id) -> CoreBankingConnector:
    """Renvoie le connecteur actif de la filiale, ou lève CoreBankingError."""
    if not tenant_id:
        raise CoreBankingError(
            "Aucune filiale active : impossible d'interroger le Core Banking."
        )
    connector = (
        CoreBankingConnector.all_tenants.filter(
            tenant_id=tenant_id, is_active=True
        )
        .order_by("-updated_at")
        .first()
    )
    if connector is None:
        raise CoreBankingError(
            "Aucun connecteur Core Banking actif pour cette filiale. "
            "Configurez-en un dans Administration → Connecteurs CBS."
        )
    return connector


def _to_decimal(value, field_name="montant") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CoreBankingError(
            f"Réponse CBS invalide : {field_name} non numérique."
        ) from exc


@transaction.atomic
def send_operation(connector, operation, payload, idempotency_key="", *, authorized_application=None):
    """
    Envoie une opération au Core Banking de manière idempotente et journalisée.

    Si une opération avec la même clé d'idempotence a déjà réussi, elle est
    renvoyée sans nouvel envoi (évite les doublons, ex. doubla mise en place).

    Les lignes RETRY / FAILED / PENDING existantes sont **réutilisées** (pas de
    second INSERT) pour respecter ``unique_idempotency_per_connector``.
    """
    if operation == OP_SUBMIT_CREDIT:
        from .disbursement import disbursement_mode, build_credit_disbursement_payload
        from apps.catalog.cbs_mapping import cbs_mapping_snapshot, lock_application_cbs_mapping

        if disbursement_mode(connector) == "CBS":
            if authorized_application is None:
                raise CoreBankingError("La création d'un crédit doit passer par le dossier et son autorisation de mise en place ; le rejeu générique est interdit.")
            app = authorized_application.__class__.all_tenants.get(pk=authorized_application.pk)
            lock_application_cbs_mapping(app)
            authorization = app.setup_authorization or {}
            if (app.tenant_id != connector.tenant_id or idempotency_key != f"disburse:{app.pk}"
                    or authorization.get("status") != "AUTHORIZED"
                    or authorization.get("cbs_mapping") != cbs_mapping_snapshot(app)
                    or payload != build_credit_disbursement_payload(app, connector=connector)):
                raise CoreBankingError("La requête CBS ne correspond pas au dossier et aux références autorisés. Reprenez le contrôle final du dossier.")
    log = None
    if idempotency_key:
        existing = (
            IntegrationLog.objects.select_for_update()
            .filter(connector=connector, idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            if existing.status == IntegrationLog.Status.SUCCESS:
                return existing
            log = existing
            log.operation = operation
            log.direction = IntegrationLog.Direction.OUTBOUND
            log.request_payload = payload
            log.status = IntegrationLog.Status.PENDING
            log.error_message = ""
            log.response_payload = {}
            log.external_reference = ""

    if log is None:
        log = IntegrationLog.objects.create(
            connector=connector,
            operation=operation,
            direction=IntegrationLog.Direction.OUTBOUND,
            idempotency_key=idempotency_key,
            request_payload=payload,
            status=IntegrationLog.Status.PENDING,
        )

    adapter = get_adapter(connector)
    try:
        log.attempts += 1
        response = adapter.send(operation, payload)
        log.response_payload = response if isinstance(response, dict) else {}
        log.external_reference = (log.response_payload or {}).get(
            "external_reference", ""
        )
        log.status = IntegrationLog.Status.SUCCESS
    except Exception as exc:  # noqa: BLE001
        log.status = (
            IntegrationLog.Status.RETRY
            if log.attempts < connector.max_retries
            else IntegrationLog.Status.FAILED
        )
        log.error_message = str(exc)
        logger.exception("Échec d'intégration Core Banking")
    log.save()
    return log


def _require_success(log: IntegrationLog, operation: str) -> dict:
    if log.status != IntegrationLog.Status.SUCCESS:
        raise CoreBankingError(
            log.error_message
            or f"Échec de l'opération CBS « {operation} ». Processus bloqué."
        )
    return log.response_payload or {}


_PAID_STATUSES = {
    "payee",
    "payée",
    "payé",
    "paye",
    "soldee",
    "soldée",
    "soldé",
    "solde",
    "reglee",
    "réglée",
    "réglé",
    "regle",
    "paid",
    "settled",
}


def _normalize_status_token(value: str) -> str:
    import unicodedata

    raw = unicodedata.normalize("NFKD", (value or "").strip().lower())
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def _is_paid_schedule_status(statut: str) -> bool:
    token = _normalize_status_token(statut)
    if not token:
        return False
    if token in _PAID_STATUSES:
        return True
    return any(p in token for p in ("paye", "solde", "regle", "paid", "settled"))


def _datas_looks_like_schedule(rows: list) -> bool:
    if not rows or not isinstance(rows[0], dict):
        return False
    row = rows[0]
    return any(k in row for k in ("echeance", "statut", "montantTotal", "montantCapital"))


def _datas_looks_like_loans(rows: list) -> bool:
    if not rows or not isinstance(rows[0], dict):
        return False
    row = rows[0]
    return any(
        k in row
        for k in ("encours", "numeroPret", "numeroDemande", "montantPret", "impaye")
    )


def _normalize_credit_schedule(data: dict) -> tuple[bool, Decimal]:
    """
    Déduit soldé / encours depuis la réponse Perfect ``crd/situation``.

    Formats supportés :
    - échéancier doc Perfect : ``statut`` / ``montantTotal`` / capital+intérêt
    - liste de prêts Vision : somme des ``encours``
    """
    rows = data.get("datas")
    if not isinstance(rows, list) or not rows:
        # Sans échéancier : considérer non soldé sauf montant nul.
        try:
            montant = Decimal(str(data.get("montant") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            montant = Decimal("0")
        return False, montant

    if _datas_looks_like_loans(rows) and not _datas_looks_like_schedule(rows):
        outstanding = Decimal("0")
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                outstanding += Decimal(
                    str(
                        row.get("encours")
                        if row.get("encours") not in (None, "")
                        else row.get("montantPret")
                        or "0"
                    )
                )
            except (InvalidOperation, TypeError, ValueError):
                continue
        return outstanding <= 0, outstanding

    outstanding = Decimal("0")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _is_paid_schedule_status(str(row.get("statut") or "")):
            continue
        try:
            if row.get("montantTotal") not in (None, ""):
                outstanding += Decimal(str(row["montantTotal"]))
            else:
                outstanding += Decimal(str(row.get("montantCapital") or "0"))
                outstanding += Decimal(str(row.get("montantInteret") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return outstanding <= 0, outstanding


def _parse_schedule_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    text = text[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def compute_cbs_overdue(data: dict, as_of=None) -> dict:
    """
    Calcule le retard à partir de l'échéancier CBS (``crd/situation``).

    Jours de retard = aujourd'hui − date de la plus ancienne échéance
    impayée et échue. Le montant = somme de ces échéances.
    """
    as_of = as_of or date.today()
    raw = data or {}
    rows = raw.get("datas")
    if not isinstance(rows, list):
        rows = raw.get("schedule")
    if not isinstance(rows, list):
        rows = []

    overdue_amount = Decimal("0")
    oldest = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _is_paid_schedule_status(str(row.get("statut") or row.get("status") or "")):
            continue
        due = _parse_schedule_date(
            row.get("date")
            or row.get("dateEcheance")
            or row.get("dueDate")
            or row.get("date_echeance")
        )
        if due is None or due >= as_of:
            continue
        try:
            if row.get("montantTotal") not in (None, ""):
                amount = Decimal(str(row["montantTotal"]))
            else:
                amount = Decimal(str(row.get("montantCapital") or "0"))
                amount += Decimal(str(row.get("montantInteret") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal("0")
        overdue_amount += amount
        if oldest is None or due < oldest:
            oldest = due

    settled, outstanding = _normalize_credit_schedule(
        raw if isinstance(raw.get("datas"), list) else {**raw, "datas": rows}
    )
    if settled or (outstanding <= 0 and overdue_amount <= 0):
        return {
            "settled": True,
            "days_overdue": 0,
            "overdue_amount": Decimal("0"),
            "outstanding": Decimal("0"),
            "oldest_due": None,
        }
    days = (as_of - oldest).days if oldest else (1 if outstanding > 0 else 0)
    amount = overdue_amount if overdue_amount > 0 else outstanding
    return {
        "settled": False,
        "days_overdue": max(days, 0),
        "overdue_amount": amount,
        "outstanding": outstanding,
        "oldest_due": oldest,
    }


def _first_text(*values) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def default_simulated_overdue_portfolio() -> list[dict]:
    """Portefeuille démo : un crédit par tranche de recouvrement."""
    today = date.today()
    specs = (
        ("CBS-IMP-GEST-001", "CTR-GEST-001", "A100001", "Koné Awa", 15, "25000", "200000"),
        ("CBS-IMP-REC-002", "CTR-REC-002", "A100002", "Traoré Ibrahim", 45, "80000", "500000"),
        ("CBS-IMP-JUR-003", "CTR-JUR-003", "A100003", "SODECI Démo", 110, "150000", "800000"),
    )
    rows = []
    for ref, contrat, code, name, days, impaye, principal in specs:
        due = today - timedelta(days=days)
        rows.append(
            {
                "refDemande": ref,
                "numDemande": ref.replace("CBS-", "DEM-"),
                "numContrat": contrat,
                "codeAdherent": code,
                "nomAdherent": name,
                "montant": float(principal),
                "montantImpaye": float(impaye),
                "encours": float(impaye),
                "joursRetard": days,
                "datas": [
                    {
                        "echeance": 1,
                        "date": due.isoformat(),
                        "montantTotal": float(impaye),
                        "statut": "En attente",
                    }
                ],
            }
        )
    return rows


def _sim_portfolio_rows(simulate: dict) -> list[dict]:
    if "overdue_portfolio" in (simulate or {}):
        rows = simulate.get("overdue_portfolio") or []
        return [row for row in rows if isinstance(row, dict)]
    return default_simulated_overdue_portfolio()


def _sim_portfolio_row_for_ref(simulate: dict, loan_ref: str) -> dict | None:
    ref = (loan_ref or "").strip()
    if not ref:
        return None
    for row in _sim_portfolio_rows(simulate):
        snap = credit_snapshot_from_cbs_row(row)
        if ref in {
            snap.get("loan_ref"),
            snap.get("ref_demande"),
            snap.get("num_contrat"),
            snap.get("num_demande"),
        }:
            return row
    return None


def _situation_from_portfolio_row(row: dict, loan_ref: str) -> dict:
    snap = credit_snapshot_from_cbs_row(row)
    days = int(snap.get("days_overdue") or 0)
    amount = snap.get("overdue_amount") or snap.get("principal") or Decimal("0")
    due = date.today() - timedelta(days=max(days, 1))
    datas = row.get("datas") if isinstance(row.get("datas"), list) else None
    if not datas:
        datas = [
            {
                "echeance": 1,
                "date": due.isoformat(),
                "montantTotal": float(amount),
                "statut": "En attente",
            }
        ]
    return {
        "simulated": True,
        "responseCode": 200,
        "refDemande": snap.get("ref_demande") or loan_ref,
        "numDemande": snap.get("num_demande") or "",
        "numContrat": snap.get("num_contrat") or "",
        "codeAdherent": snap.get("code_adherent") or "",
        "montant": snap.get("principal") or amount,
        "datas": datas,
        "context": "CREDIT SITUATION",
    }


def credit_snapshot_from_cbs_row(row: dict) -> dict:
    """Normalise une ligne de liste crédits / impayés CBS."""
    row = row if isinstance(row, dict) else {}
    loan_ref = _first_text(
        row.get("loan_ref"),
        row.get("refDemande"),
        row.get("ref_demande"),
        row.get("numContrat"),
        row.get("num_contrat"),
        row.get("numDemande"),
        row.get("num_demande"),
        row.get("reference"),
        row.get("ref"),
    )
    days_raw = (
        row.get("days_overdue")
        or row.get("joursRetard")
        or row.get("nbreJoursRetard")
        or row.get("nbJoursRetard")
        or row.get("retard")
        or 0
    )
    try:
        days = int(days_raw or 0)
    except (TypeError, ValueError):
        days = 0
    try:
        overdue_amount = Decimal(
            str(
                row.get("overdue_amount")
                or row.get("montantImpaye")
                or row.get("montantRetard")
                or row.get("impaye")
                or "0"
            )
        )
    except (InvalidOperation, TypeError, ValueError):
        overdue_amount = Decimal("0")
    try:
        principal = Decimal(
            str(
                row.get("principal")
                or row.get("montantCredit")
                or row.get("montantDemande")
                or row.get("montant")
                or overdue_amount
                or "0"
            )
        )
    except (InvalidOperation, TypeError, ValueError):
        principal = overdue_amount
    return {
        "loan_ref": loan_ref,
        "ref_demande": _first_text(row.get("refDemande"), row.get("ref_demande"), loan_ref),
        "num_demande": _first_text(row.get("numDemande"), row.get("num_demande")),
        "num_contrat": _first_text(row.get("numContrat"), row.get("num_contrat")),
        "code_adherent": _first_text(
            row.get("codeAdherent"),
            row.get("code_adherent"),
            row.get("cbs_client_id"),
            row.get("code"),
        ),
        "num_manuel": _first_text(row.get("numManuel"), row.get("num_manuel")),
        "num_piece_identite": _first_text(
            row.get("numPieceIdentite"), row.get("num_piece_identite")
        ),
        "client_name": _first_text(
            row.get("nomAdherent"),
            row.get("nom"),
            row.get("raisonSociale"),
            row.get("client_name"),
        ),
        "product_code": _first_text(
            row.get("idProduitCrd"),
            row.get("produit"),
            row.get("product_code"),
        ),
        "days_overdue": max(days, 0),
        "overdue_amount": str(overdue_amount),
        "principal": str(principal),
        "outstanding": str(overdue_amount or principal),
        "raw": row,
    }


def normalize_cbs_credit_rows(payload) -> list[dict]:
    raw = payload if isinstance(payload, dict) else {}
    if isinstance(payload, list):
        rows = payload
        raw = {"datas": payload}
    else:
        inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
        rows = (
            raw.get("credits")
            or raw.get("datas")
            or raw.get("impayes")
            or raw.get("liste")
            or raw.get("items")
            or inner.get("credits")
            or inner.get("datas")
            or inner.get("impayes")
            or []
        )
    if not isinstance(rows, list):
        rows = []
    out = []
    seen = set()
    for row in rows:
        snap = credit_snapshot_from_cbs_row(row if isinstance(row, dict) else {})
        ref = snap.get("loan_ref")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        out.append(snap)
    return out


def list_cbs_outstanding_credits(
    tenant_id, *, overdue_only=True, connector=None
) -> dict:
    """Liste les crédits / impayés CBS (portefeuille initial)."""
    connector = connector or resolve_active_connector(tenant_id)
    extra = ((connector.mapping_rules or {}).get("portfolio") or {}).get(
        "loan_refs"
    ) or []
    log = send_operation(
        connector,
        OP_LIST_OVERDUE_CREDITS,
        {"overdue_only": overdue_only},
    )
    payload = _require_success(log, OP_LIST_OVERDUE_CREDITS)
    credits = normalize_cbs_credit_rows(payload)
    seen = {row["loan_ref"] for row in credits}
    for ref in extra:
        ref = str(ref or "").strip()
        if ref and ref not in seen:
            credits.append(
                credit_snapshot_from_cbs_row({"refDemande": ref, "loan_ref": ref})
            )
            seen.add(ref)
    return {
        "credits": credits,
        "log_id": str(log.id),
        "raw": payload.get("raw") or payload,
        "external_reference": log.external_reference,
    }


def get_loan_status(
    tenant_id,
    loan_ref,
    *,
    currency=None,
    code_adherent=None,
    num_manuel=None,
    num_piece_identite=None,
    connector=None,
) -> dict:
    """
    Vérifie dans le CBS si un crédit/prêt est soldé (Perfect ``crd/situation``).

    Retour normalisé :
    {settled, outstanding, currency, schedule, raw, log_id, …}
    """
    from apps.tenants.currency import tenant_currency

    loan_ref = (loan_ref or "").strip()
    if not loan_ref:
        raise CoreBankingError(
            "Référence prêt CBS manquante : impossible de vérifier le solde."
        )
    currency = (currency or "").strip().upper() or tenant_currency(tenant_id)
    op_payload = {
        "loan_ref": loan_ref,
        "refDemande": loan_ref,
        "currency": currency,
    }
    if code_adherent:
        op_payload["codeAdherent"] = str(code_adherent).strip()
    if num_manuel:
        op_payload["numManuel"] = str(num_manuel).strip()
    if num_piece_identite:
        op_payload["numPieceIdentite"] = str(num_piece_identite).strip()

    connector = connector or resolve_active_connector(tenant_id)
    log = send_operation(connector, OP_GET_LOAN_STATUS, op_payload)
    payload = _require_success(log, OP_GET_LOAN_STATUS)
    settled = bool(payload.get("settled"))
    outstanding = _to_decimal(payload.get("outstanding", "0"), "outstanding")
    raw = payload.get("raw") or payload
    schedule = payload.get("schedule") or raw.get("datas") or []
    overdue = compute_cbs_overdue(
        {**raw, "datas": schedule, "montant": payload.get("montant") or outstanding},
    )
    days = payload.get("days_overdue")
    if days in (None, ""):
        days = overdue["days_overdue"]
    amount = payload.get("overdue_amount")
    if amount in (None, ""):
        amount = overdue["overdue_amount"]
    else:
        amount = _to_decimal(amount, "overdue_amount")
    return {
        "settled": overdue["settled"] if overdue["settled"] else settled,
        "outstanding": overdue["outstanding"] or outstanding,
        "days_overdue": int(days or 0),
        "overdue_amount": amount,
        "oldest_due": overdue.get("oldest_due"),
        "currency": payload.get("currency") or currency,
        "schedule": schedule,
        "raw": raw,
        "log_id": str(log.id),
        "external_reference": log.external_reference,
        "num_demande": payload.get("num_demande") or "",
        "ref_demande": payload.get("ref_demande") or loan_ref,
        "num_contrat": payload.get("num_contrat") or "",
    }


def probe_credit_situation(
    tenant_id,
    *,
    ref_demande: str,
    code_adherent: str,
    connector=None,
) -> dict:
    """
    Appel diagnostic ``crd/situation`` (admin) : requête minimale doc Perfect
    + résultat classé pour affichage (échéancier ou liste de prêts Vision).
    """
    ref = (ref_demande or "").strip()
    code = (code_adherent or "").strip()
    if not ref:
        raise CoreBankingError("La référence de demande (refDemande) est obligatoire.")
    if not code:
        raise CoreBankingError("Le code adhérent est obligatoire.")

    result = get_loan_status(
        tenant_id,
        ref,
        code_adherent=code,
        connector=connector,
    )
    raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
    rows = result.get("schedule") or raw.get("datas") or []
    if not isinstance(rows, list):
        rows = []

    if _datas_looks_like_schedule(rows):
        kind = "schedule"
    elif _datas_looks_like_loans(rows):
        kind = "loans"
    elif rows:
        kind = "unknown"
    else:
        kind = "empty"

    def _dec(value) -> str:
        try:
            return str(_to_decimal(value if value not in (None, "") else "0", "v"))
        except CoreBankingError:
            return "0"

    display_rows: list[dict] = []
    if kind == "schedule":
        for row in rows:
            if not isinstance(row, dict):
                continue
            total = row.get("montantTotal")
            if total in (None, ""):
                try:
                    total = Decimal(str(row.get("montantCapital") or 0)) + Decimal(
                        str(row.get("montantInteret") or 0)
                    )
                except (InvalidOperation, TypeError, ValueError):
                    total = "0"
            display_rows.append(
                {
                    "echeance": row.get("echeance"),
                    "date": row.get("date"),
                    "montant_capital": _dec(row.get("montantCapital")),
                    "montant_interet": _dec(row.get("montantInteret")),
                    "montant_total": _dec(total),
                    "statut": str(row.get("statut") or ""),
                    "raw": row,
                }
            )
    elif kind == "loans":
        for row in rows:
            if not isinstance(row, dict):
                continue
            display_rows.append(
                {
                    "numero_demande": str(row.get("numeroDemande") or ""),
                    "numero_pret": str(row.get("numeroPret") or ""),
                    "compte_pret": str(row.get("comptePret") or ""),
                    "nom_adherent": str(row.get("nomAdherent") or ""),
                    "date_demande": row.get("dateDemande"),
                    "date_effet": row.get("dateEffet"),
                    "date_solde": row.get("dateSolde"),
                    "montant_pret": _dec(row.get("montantPret")),
                    "encours": _dec(row.get("encours")),
                    "impaye": _dec(row.get("impaye")),
                    "impaye_interet": _dec(row.get("impayeInteret")),
                    "penalite": _dec(row.get("penalite")),
                    "jours_retard": int(row.get("nbreJrsRetard") or 0),
                    "observations": str(row.get("observations") or ""),
                    "raw": row,
                }
            )
    else:
        for row in rows:
            if isinstance(row, dict):
                display_rows.append({"raw": row})

    outstanding = result.get("outstanding")
    return {
        "request": {"refDemande": ref, "codeAdherent": code},
        "kind": kind,
        "kind_label": {
            "schedule": "Échéancier (format documentation Perfect)",
            "loans": "Liste de prêts (format Vision)",
            "empty": "Aucune ligne dans datas",
            "unknown": "Format datas non reconnu",
        }.get(kind, kind),
        "message": str(raw.get("message") or ""),
        "response_code": raw.get("responseCode"),
        "num_demande": result.get("num_demande") or raw.get("numDemande") or "",
        "ref_demande": result.get("ref_demande") or raw.get("refDemande") or ref,
        "num_contrat": result.get("num_contrat") or raw.get("numContrat") or "",
        "montant": _dec(raw.get("montant") if raw.get("montant") not in (None, "") else outstanding),
        "currency": result.get("currency") or raw.get("codeDevise") or "",
        "settled": bool(result.get("settled")),
        "outstanding": _dec(outstanding),
        "days_overdue": int(result.get("days_overdue") or 0),
        "overdue_amount": _dec(result.get("overdue_amount")),
        "rows_count": len(display_rows),
        "rows": display_rows,
        "log_id": result.get("log_id"),
        "external_reference": result.get("external_reference") or "",
        "raw": raw,
    }


def get_client_outstanding(tenant_id, cbs_client_id, *, currency=None) -> dict:
    """
    Récupère l'encours total client dans le CBS.

    Retour normalisé :
    {total_outstanding: Decimal, currency: str, breakdown: list, raw: dict, log_id}
    """
    from apps.tenants.currency import tenant_currency

    cbs_client_id = (cbs_client_id or "").strip()
    if not cbs_client_id:
        raise CoreBankingError(
            "Identifiant client CBS manquant : impossible de récupérer l'encours."
        )
    currency = (currency or "").strip().upper() or tenant_currency(tenant_id)
    connector = resolve_active_connector(tenant_id)
    log = send_operation(
        connector,
        OP_GET_CLIENT_OUTSTANDING,
        {"cbs_client_id": cbs_client_id, "currency": currency},
    )
    payload = _require_success(log, OP_GET_CLIENT_OUTSTANDING)
    total = _to_decimal(
        payload.get("total_outstanding", "0"), "total_outstanding"
    )
    return {
        "total_outstanding": total,
        "currency": payload.get("currency") or currency,
        "breakdown": payload.get("breakdown") or [],
        "raw": payload.get("raw") or payload,
        "log_id": str(log.id),
        "external_reference": log.external_reference,
    }


def assert_loan_settled(
    tenant_id,
    loan_ref,
    *,
    currency=None,
    code_adherent=None,
    num_manuel=None,
    num_piece_identite=None,
) -> dict:
    """Blocage strict : lève CoreBankingError si le prêt n'est pas soldé."""
    result = get_loan_status(
        tenant_id,
        loan_ref,
        currency=currency,
        code_adherent=code_adherent,
        num_manuel=num_manuel,
        num_piece_identite=num_piece_identite,
    )
    if not result["settled"]:
        raise CoreBankingError(
            "Main levée impossible : le prêt n'est pas soldé dans le Core Banking "
            f"(encours restant : {result['outstanding']} {result['currency']})."
        )
    return result


def assert_client_outstanding_for_dation(
    tenant_id, cbs_client_id, *, currency=None, min_outstanding=None
) -> dict:
    """
    Blocage strict pour l'initiation d'une dation :
    - l'encours doit être récupérable ;
    - par défaut, un encours > 0 est exigé (sinon dation sans objet).
    """
    result = get_client_outstanding(
        tenant_id, cbs_client_id, currency=currency
    )
    threshold = (
        Decimal(str(min_outstanding))
        if min_outstanding is not None
        else Decimal("0")
    )
    if result["total_outstanding"] <= threshold:
        raise CoreBankingError(
            "Dation en paiement impossible : l'encours total client dans le "
            f"Core Banking est insuffisant ({result['total_outstanding']} "
            f"{result['currency']})."
        )
    return result


def _raw_str(raw: dict, *keys) -> str:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_client_situation(raw: dict) -> dict:
    """Normalise la réponse Perfect ``adh/situation`` pour l'UI / l'import."""
    raw = raw or {}
    est_valide = raw.get("estValide")
    if isinstance(est_valide, str):
        est_valide = est_valide.strip().lower() in {"1", "true", "oui", "yes"}
    else:
        est_valide = bool(est_valide)

    last_name = _raw_str(raw, "nom", "lastName")
    first_name = _raw_str(raw, "prenoms", "prenom", "firstName")
    company_name = _raw_str(raw, "nom", "raisonSociale")
    full_name = _raw_str(raw, "nomAdherent")
    if not full_name:
        full_name = " ".join(p for p in (first_name, last_name) if p).strip()
    if not full_name:
        full_name = company_name

    limit = raw.get("limitCredit")
    try:
        limit_credit = Decimal(str(limit)) if limit not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        limit_credit = None

    return {
        "full_name": full_name,
        "last_name": last_name,
        "first_name": first_name,
        "company_name": company_name,
        "sigle": _raw_str(raw, "sigle"),
        "code_adherent": _raw_str(raw, "codeAdherent"),
        "num_manuel": _raw_str(raw, "numManuel"),
        "num_piece_identite": _raw_str(raw, "numPieceIdentite"),
        "identification_nationale": _raw_str(raw, "identificationNationale"),
        "num_carte_operateur": _raw_str(
            raw, "numCarteOperateurEconomique", "rccm"
        ),
        "num_ordre": _raw_str(raw, "numOrdre"),
        "birth_date": _raw_str(raw, "dateNaissance"),
        "birth_place": _raw_str(raw, "lieuNaissance"),
        "civility": _raw_str(raw, "civilite"),
        "marital_status": _raw_str(raw, "statutMatrimonial"),
        "spouse_name": _raw_str(raw, "nomConjoint"),
        "id_document_issue_date": _raw_str(raw, "dateEtablissementPiece"),
        "id_document_expiry_date": _raw_str(raw, "dateExpirationPiece"),
        "id_profession": _raw_str(raw, "idProfession"),
        "profession": _raw_str(raw, "profession", "libelleProfession"),
        "id_nationalite": _raw_str(raw, "idNationalite"),
        "nationality": _raw_str(raw, "nationalite", "libelleNationalite"),
        "date_creation": _raw_str(raw, "dateCreation"),
        "head_office": _raw_str(raw, "siegeSocial"),
        "id_secteur_activite": _raw_str(raw, "idSecteurActivite"),
        "id_type_client": _raw_str(raw, "idTypeClient"),
        "id_zone": _raw_str(raw, "idZone"),
        "id_produit_epg": _raw_str(raw, "idProduitEpg"),
        "nbre_signature": raw.get("nbreSignature"),
        "distance": raw.get("distance"),
        "phone": _raw_str(raw, "telephone"),
        "email": _raw_str(raw, "email"),
        "boite_postale": _raw_str(raw, "boitePostale"),
        "city": _raw_str(raw, "ville"),
        "address": _raw_str(raw, "adresse"),
        "date_inscription": _raw_str(raw, "dateInscription"),
        "limit_credit": str(limit_credit) if limit_credit is not None else None,
        "est_valide": est_valide,
        "id_point_service": _raw_str(raw, "idPointService"),
        "nom_point_service": _raw_str(raw, "nomPointService"),
        "context": _raw_str(raw, "context"),
        "message": _raw_str(raw, "message"),
        "kyc_alert": not est_valide,
        "raw": raw,
    }


def get_client_situation(
    tenant_id,
    *,
    code_adherent: str = "",
    num_manuel: str = "",
    num_piece_identite: str = "",
    identification_nationale: str = "",
    num_carte_operateur: str = "",
    client_type: str = "",
) -> dict:
    """
    Récupère la situation / identité d'un adhérent CBS (Perfect).

    Retour normalisé via ``normalize_client_situation`` + ``log_id``.
    """
    code_adherent = (code_adherent or "").strip()
    num_manuel = (num_manuel or "").strip()
    num_piece_identite = (num_piece_identite or "").strip()
    identification_nationale = (identification_nationale or "").strip()
    num_carte_operateur = (num_carte_operateur or "").strip()
    client_type = (client_type or "").strip().upper()
    if not (
        code_adherent
        or num_manuel
        or num_piece_identite
        or identification_nationale
        or num_carte_operateur
    ):
        raise CoreBankingError(
            "Au moins un identifiant CBS est requis "
            "(code adhérent, n° manuel, n° pièce, identification nationale "
            "ou n° carte / RCCM)."
        )

    connector = resolve_active_connector(tenant_id)
    log = send_operation(
        connector,
        OP_GET_CLIENT_SITUATION,
        {
            "codeAdherent": code_adherent,
            "numManuel": num_manuel,
            "numPieceIdentite": num_piece_identite,
            "identificationNationale": identification_nationale,
            "numCarteOperateurEconomique": num_carte_operateur,
            "clientType": client_type,
        },
    )
    payload = _require_success(log, OP_GET_CLIENT_SITUATION)
    raw = payload.get("raw") or payload
    normalized = normalize_client_situation(raw)
    if not normalized["full_name"]:
        raise CoreBankingError(
            "Réponse CBS incomplète : nom de l'adhérent manquant."
        )
    normalized["log_id"] = str(log.id)
    normalized["external_reference"] = log.external_reference
    return normalized
