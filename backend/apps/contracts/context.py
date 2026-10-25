"""Construction du contexte de variables injecté dans les modèles de contrats.

Le dictionnaire retourné par :func:`build_context` définit toutes les balises
utilisables dans les modèles Word/Excel (ex. ``{{ client_nom }}``). Le
catalogue :data:`VARIABLE_CATALOG` documente ces balises pour l'interface.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.utils import timezone

try:
    from num2words import num2words
except Exception:  # pragma: no cover - dépendance optionnelle
    num2words = None


# --------------------------------------------------------------------------- #
# Formateurs
# --------------------------------------------------------------------------- #
def fmt_money(value) -> str:
    """Formate un montant avec séparateur de milliers (espace insécable)."""
    if value in (None, ""):
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    quantized = d.quantize(Decimal("1")) if d == d.to_integral_value() else d
    text = f"{quantized:,.0f}" if d == d.to_integral_value() else f"{quantized:,.2f}"
    return text.replace(",", " ")


def fmt_amount_words(value, currency: str = "francs CFA") -> str:
    """Montant en toutes lettres (français)."""
    if value in (None, "") or num2words is None:
        return ""
    try:
        number = int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return ""
    words = num2words(number, lang="fr")
    return f"{words} {currency}".strip()


def fmt_date(value) -> str:
    """Formate une date au format jj/mm/aaaa."""
    if not value:
        return ""
    try:
        return value.strftime("%d/%m/%Y")
    except AttributeError:
        return str(value)


def _display(choice_value, choices) -> str:
    mapping = dict(choices)
    return mapping.get(choice_value, choice_value or "")


def _full_name(*parts) -> str:
    return " ".join(p for p in parts if p).strip()


def _client_type_label(client) -> str:
    ctype = getattr(client, "client_type", "")
    if ctype == "CORPORATE":
        return "Entreprise"
    if ctype == "PROFESSIONAL":
        return "Groupement"
    return "Particulier"


# --------------------------------------------------------------------------- #
# Catalogue documenté (exposé à l'interface)
# --------------------------------------------------------------------------- #
VARIABLE_CATALOG = [
    {"group": "Filiale & date", "items": [
        ("date_du_jour", "Date du jour (jj/mm/aaaa)"),
        ("filiale_nom", "Raison sociale de la filiale"),
        ("filiale_adresse", "Adresse de la filiale"),
        ("filiale_telephone", "Téléphone de la filiale"),
        ("filiale_email", "Email de la filiale"),
        ("filiale_pays", "Pays de la filiale"),
        ("agence_nom", "Nom de l'agence du dossier"),
        ("agence_code", "Code de l'agence du dossier"),
        ("agence_region", "Région de l'agence du dossier"),
        ("agence", "Agence complète (code — nom)"),
        ("ville_agence", "Ville / région de l'agence"),
        ("agence_adresse", "Adresse de l'agence"),
        ("agence_chef_nom", "Nom du chef d'agence"),
        ("agence_chef_prenom", "Prénom du chef d'agence"),
        ("agence_chef_nom_complet", "Nom complet du chef d'agence"),
        ("agence_chef_telephone", "Téléphone du chef d'agence"),
        ("responsables", "Liste des responsables filiale (boucle : r.poste, r.nom, r.prenom, r.telephone, r.nom_complet)"),
        ("responsables_texte", "Responsables filiale résumés en une ligne"),
        ("nombre_responsables", "Nombre de responsables de la filiale"),
        ("responsable1_poste", "1er responsable : intitulé du poste"),
        ("responsable1_nom", "1er responsable : nom"),
        ("responsable1_prenom", "1er responsable : prénom"),
        ("responsable1_telephone", "1er responsable : téléphone"),
        ("responsable2_poste", "2e responsable : idem avec le préfixe responsable2_…"),
    ]},
    {"group": "Dossier", "items": [
        ("dossier_reference", "Référence du dossier"),
        ("dossier_objet", "Objet du financement"),
        ("objet_financement", "Alias de l'objet du financement"),
        ("dossier_details", "Détails de la demande"),
        ("dossier_date_decision", "Date de décision"),
    ]},
    {"group": "Client", "items": [
        ("client_type", "Type de client (Particulier / Groupement / Entreprise)"),
        ("client_civilite", "Civilité"),
        ("client_nom", "Nom du client"),
        ("client_prenom", "Prénom du client"),
        ("client_nom_complet", "Nom complet / raison sociale"),
        ("client_cni_type", "Type de pièce d'identité"),
        ("client_cni", "Numéro de pièce d'identité"),
        ("client_cni_delivrance", "Date d'établissement de la pièce d'identité"),
        ("client_cni_expiration", "Date d'expiration de la pièce d'identité"),
        ("client_adresse", "Adresse du client"),
        ("client_ville", "Ville du client"),
        ("client_pays", "Pays de résidence du client"),
        ("client_telephone", "Téléphone principal du client"),
        ("client_telephones", "Tous les téléphones (principal + additionnels)"),
        ("client_telephones_autres", "Téléphones additionnels (libellé — numéro)"),
        ("client_telephone2", "2e téléphone (1er numéro additionnel)"),
        ("client_telephone3", "3e téléphone (2e numéro additionnel)"),
        ("client_email", "Email du client"),
        ("client_profession", "Profession"),
        ("client_date_naissance", "Date de naissance"),
        ("client_lieu_naissance", "Pays / lieu de naissance (pays de naissance)"),
        ("client_pays_naissance", "Pays de naissance"),
        ("client_nationalite", "Nationalité"),
        ("client_situation_matrimoniale", "Situation matrimoniale"),
        ("client_kyc", "Statut KYC"),
        ("client_kyc_valide_le", "Date de validation KYC"),
        ("client_agence_nom", "Nom de l'agence du client (fiche client)"),
        ("client_agence_code", "Code de l'agence du client (fiche client)"),
        ("client_matricule", "Matricule client / ID Core Banking"),
        ("client_matricule_cbs", "Matricule Core Banking (CBS)"),
        ("client_compte", "Numéro de compte CBS"),
        ("client_compte_cbs", "Numéro de compte Core Banking (CBS)"),
        ("compte_cbs", "Alias du numéro de compte CBS"),
    ]},
    {"group": "Famille", "items": [
        ("client_conjoint_nom", "Nom du conjoint"),
        ("client_conjoint_prenom", "Prénom du conjoint"),
        ("client_conjoint_nom_complet", "Nom complet du conjoint"),
        ("client_conjoint_telephone", "Téléphone du conjoint"),
        ("client_conjoint_profession", "Profession du conjoint"),
        ("client_pere_nom", "Nom du père"),
        ("client_pere_prenom", "Prénom du père"),
        ("client_pere_nom_complet", "Nom complet du père"),
        ("client_mere_nom", "Nom de la mère"),
        ("client_mere_prenom", "Prénom de la mère"),
        ("client_mere_nom_complet", "Nom complet de la mère"),
    ]},
    {"group": "Entreprise", "items": [
        ("societe_nom", "Raison sociale"),
        ("societe_forme", "Forme juridique"),
        ("societe_rccm", "RCCM"),
        ("societe_ninea", "NINEA / IFU (alias de societe_ifu)"),
        ("societe_ifu", "IFU"),
        ("societe_siege", "Siège social"),
        ("societe_ville", "Ville"),
        ("societe_telephone", "Téléphone"),
        ("societe_email", "Email"),
        ("societe_activite", "Activité / secteur"),
        ("societe_date_creation", "Date de création de l'activité"),
        ("societe_effectif", "Nombre d'employés"),
        ("societe_matricule", "Matricule / ID Core Banking"),
        ("societe_compte", "Numéro de compte CBS"),
        ("societe_compte_cbs", "Numéro de compte Core Banking (CBS)"),
    ]},
    {"group": "Gérant / représentant légal", "items": [
        ("representant", "Représentant légal (nom complet)"),
        ("gerant_nom", "Nom complet du gérant"),
        ("gerant_nom_seul", "Nom du gérant"),
        ("gerant_prenom", "Prénom du gérant"),
        ("gerant_poste", "Poste du gérant dans l'entreprise"),
        ("gerant_telephone", "Téléphone du gérant"),
        ("gerant_email", "Email du gérant"),
        ("gerant_adresse", "Adresse du gérant"),
        ("gerant_date_naissance", "Date de naissance du gérant"),
        ("gerant_pays_naissance", "Pays de naissance du gérant"),
        ("gerant_ville_naissance", "Ville de naissance du gérant"),
        ("gerant_piece_type", "Type de pièce d'identité du gérant"),
        ("gerant_piece_numero", "N° de pièce d'identité du gérant"),
        ("gerant_piece_delivrance", "Date d'établissement de la pièce du gérant"),
        ("gerant_piece_expiration", "Date d'expiration de la pièce du gérant"),
    ]},
    {"group": "Crédit", "items": [
        ("produit", "Produit de crédit"),
        ("montant_demande", "Montant demandé"),
        ("montant_accorde", "Montant accordé"),
        ("montant_accorde_lettres", "Montant accordé en toutes lettres"),
        ("taux", "Taux d'intérêt (%)"),
        ("frais_dossier", "Frais de dossier (%)"),
        ("frais_total", "Total des frais, taxes sur frais comprises"),
        ("taxes_frais_total", "Total des taxes sur les frais configurés"),
        ("frais_detail", "Liste des frais : label, amount, tax_amount"),
        ("taux_epargne", "Taux d'épargne obligatoire (%)"),
        ("duree_mois", "Durée (mois)"),
        ("periodicite", "Périodicité"),
        ("mecanisme_remboursement", "Mécanisme de remboursement"),
        ("dossier_mecanisme", "Alias du mécanisme de remboursement"),
        ("mensualite", "Échéance périodique estimée"),
        ("premiere_echeance", "Date de première échéance"),
        ("derniere_echeance", "Date de dernière échéance"),
        ("cout_total_projet", "Coût total du projet"),
        ("apport_personnel", "Apport personnel"),
        ("quotite", "Quotité financée (%)"),
        ("devise", "Devise"),
        ("total_interets", "Total des intérêts"),
        ("total_a_rembourser", "Total à rembourser"),
    ]},
    {"group": "Emploi / cession sur salaire", "items": [
        ("employeur", "Nom de l'employeur (dossier)"),
        ("type_contrat", "Type de contrat de travail"),
        ("personnes_a_charge", "Nombre de personnes à charge"),
        ("domiciliation_salaire", "Domiciliation du salaire (Oui/Non)"),
    ]},
    {"group": "Assurance", "items": [
        ("assurance_adi", "Assurance ADI (Oui/Non)"),
        ("assurance_compagnie", "Compagnie d'assurance"),
        ("assurance_prime", "Prime d'assurance"),
    ]},
    {"group": "Caution — commun (1re caution)", "items": [
        ("caution_type", "Type (personne physique / morale)"),
        ("caution_type_engagement", "Type d'engagement (simple / solidaire)"),
        ("caution_nom_complet", "Nom complet / raison sociale de la caution"),
        ("caution_adresse", "Adresse de la caution"),
        ("caution_ville", "Ville de la caution"),
        ("caution_telephone", "Téléphone de la caution"),
        ("caution_email", "Email de la caution"),
        ("caution_activite", "Activité / profession"),
        ("caution_montant", "Montant de l'engagement"),
        ("caution_montant_lettres", "Montant de l'engagement en lettres"),
        ("caution_date_signature", "Date de signature de l'engagement"),
        ("caution2_nom_complet", "2e caution : idem avec le préfixe caution2_…"),
    ]},
    {"group": "Caution — particulier", "items": [
        ("caution_nom", "Nom de la caution"),
        ("caution_prenom", "Prénom de la caution"),
        ("caution_date_naissance", "Date de naissance"),
        ("caution_lieu_naissance", "Lieu / pays de naissance"),
        ("caution_cni_type", "Type de pièce d'identité"),
        ("caution_cni", "N° de pièce d'identité"),
        ("caution_piece_rccm", "Pièce d'identité (alias)"),
        ("caution_revenu", "Estimation de revenu"),
    ]},
    {"group": "Caution — entreprise", "items": [
        ("caution_raison_sociale", "Raison sociale"),
        ("caution_forme_juridique", "Forme juridique"),
        ("caution_ifu", "N° IFU"),
        ("caution_rccm", "N° RCCM"),
        ("caution_piece_rccm", "RCCM (alias)"),
        ("caution_gerant_nom", "Nom complet du gérant"),
        ("caution_gerant_nom_seul", "Nom du gérant"),
        ("caution_gerant_prenom", "Prénom du gérant"),
        ("caution_gerant_poste", "Poste du gérant"),
        ("caution_gerant_telephone", "Téléphone du gérant"),
        ("caution_gerant_email", "Email du gérant"),
        ("caution_gerant_adresse", "Adresse du gérant"),
        ("caution_gerant_date_naissance", "Date de naissance du gérant"),
        ("caution_gerant_pays_naissance", "Pays de naissance du gérant"),
        ("caution_gerant_ville_naissance", "Ville de naissance du gérant"),
        ("caution_gerant_piece_type", "Type de pièce du gérant"),
        ("caution_gerant_piece_numero", "N° de pièce du gérant"),
        ("caution_gerant_piece_delivrance", "Date d'établissement de la pièce du gérant"),
        ("caution_gerant_piece_expiration", "Date d'expiration de la pièce du gérant"),
    ]},
    {"group": "Garantie — commun (1re garantie)", "items": [
        ("garantie_type", "Type de garantie"),
        ("garantie_categorie_gage", "Catégorie de gage (moyen roulant / objet de valeur)"),
        ("garantie_details", "Détails formatés selon le type"),
        ("garantie_description", "Description"),
        ("garantie_reference", "Référence"),
        ("garantie_statut", "Statut de la garantie"),
        ("garantie_valeur", "Valeur actualisée"),
        ("garantie_valeur_expertise", "Valeur d'expertise"),
        ("garantie_valeur_consideree", "Valeur à considérer"),
        ("garantie_ratio_ltv", "Ratio LTV"),
        ("garantie_assuree", "Assurée (Oui/Non)"),
        ("garantie_assurance_ref", "Référence de l'assurance"),
        ("garantie_expert", "Nom de l'expert"),
        ("garantie_cabinet_expertise", "Cabinet d'expertise"),
        ("garantie_date_expertise", "Date de l'expertise"),
        ("garantie2_type", "2e garantie : idem avec le préfixe garantie2_…"),
    ]},
    {"group": "Garantie — hypothèque", "items": [
        ("garantie_proprietaire_nom_complet", "Propriétaire du bien"),
        ("garantie_proprietaire_nom", "Nom du propriétaire"),
        ("garantie_proprietaire_prenom", "Prénom du propriétaire"),
        ("garantie_proprietaire_situation_matrimoniale", "Situation matrimoniale du propriétaire"),
        ("garantie_regime_matrimonial", "Régime matrimonial"),
        ("garantie_document_type", "Type de document (titre foncier / attestation)"),
        ("garantie_document_numero", "N° du titre / document"),
        ("garantie_document_date", "Date d'établissement du document"),
        ("garantie_adresse_bien", "Adresse du bien"),
        ("garantie_statut_occupation", "Statut d'occupation du bien"),
        ("garantie_valeur_expertise", "Valeur expertisée"),
        ("garantie_valeur_consideree", "Valeur à considérer"),
        ("garantie_ratio_ltv", "Ratio LTV"),
        ("garantie_expert", "Nom de l'expert"),
        ("garantie_cabinet_expertise", "Cabinet d'expertise"),
        ("garantie_date_expertise", "Date de l'expertise"),
        ("garantie_assuree", "Bien assuré (Oui/Non)"),
    ]},
    {"group": "Garantie — gage (moyen roulant)", "items": [
        ("garantie_proprietaire_nom_complet", "Propriétaire du véhicule"),
        ("garantie_proprietaire_nom", "Nom du propriétaire"),
        ("garantie_proprietaire_prenom", "Prénom du propriétaire"),
        ("garantie_marque", "Marque"),
        ("garantie_modele", "Modèle"),
        ("garantie_immatriculation", "Immatriculation"),
        ("garantie_chassis", "N° de châssis"),
        ("garantie_moteur", "N° du moteur"),
        ("garantie_puissance", "Puissance"),
        ("garantie_annee", "Année de 1re mise en circulation"),
        ("garantie_date_acquisition", "Date d'acquisition"),
        ("garantie_valeur_acquisition", "Valeur d'acquisition"),
        ("garantie_valeur_revente", "Valeur estimée à la revente"),
        ("garantie_date_estimation", "Date d'estimation"),
        ("garantie_info_complementaire", "Information complémentaire"),
        ("garantie_expert", "Nom de l'expert"),
        ("garantie_cabinet_expertise", "Cabinet d'expertise"),
        ("garantie_date_expertise", "Date de l'expertise"),
    ]},
    {"group": "Garantie — gage (bijoux)", "items": [
        ("garantie_description", "Description générale du gage"),
        ("garantie_cours_matiere", "Cours actuel de la matière première"),
        ("garantie_expert", "Nom de l'expert"),
        ("garantie_cabinet_expertise", "Cabinet d'expertise"),
        ("garantie_date_expertise", "Date de l'expertise"),
        ("garantie_nombre_bijoux", "Nombre de bijoux du gage"),
        ("garantie_bijoux_texte", "Bijoux résumés en une ligne"),
        ("garantie_bijoux", "Liste des bijoux (boucle : b.nature, b.poids, b.description)"),
    ]},
    {"group": "Garantie — financière", "items": [
        ("garantie_type_financier", "Type (DAT / épargne / titre)"),
        ("garantie_numero_compte", "N° de compte"),
        ("garantie_solde", "Solde"),
        ("garantie_taux_remuneration", "Taux de rémunération"),
        ("garantie_isin", "Code ISIN / nom de la valeur"),
        ("garantie_echeance_depot", "Date d'échéance du dépôt"),
        ("garantie_decote_securite", "Décote de sécurité"),
    ]},
    {"group": "Totaux & listes (boucles Word)", "items": [
        ("nombre_cautions", "Nombre de cautions"),
        ("total_cautions", "Total des engagements des cautions"),
        ("cautions_texte", "Cautions résumées en une ligne"),
        ("nombre_garanties", "Nombre de garanties"),
        ("total_garanties", "Total de la valeur des garanties"),
        ("garanties_texte", "Garanties résumées en une ligne"),
        ("cautions", "Liste des cautions (boucle : c.nom_complet, c.cni, c.montant…)"),
        ("garanties", "Liste des garanties (boucle : g.type, g.details, g.valeur…)"),
        ("echeancier", "Échéancier (boucle de LIGNE de tableau — voir aide)"),
    ]},
]

# Aide affichée dans l'interface pour l'usage des boucles/tableaux.
LOOP_HELP = (
    "Pour un tableau (échéancier, liste de garanties/cautions), utilisez la "
    "boucle de LIGNE de docxtpl : dans la 1re cellule de la ligne à répéter, "
    "écrivez {%tr for e in echeancier %} et dans la dernière cellule {%tr endfor %}, "
    "puis {{ e.numero }}, {{ e.date }}, {{ e.capital }}, {{ e.interet }}, "
    "{{ e.total }} dans les cellules. Idem pour {%tr for g in garanties %} "
    "(g.type, g.details, g.valeur) et {%tr for c in cautions %} "
    "(c.nom_complet, c.cni, c.montant). Pour lister les bijoux d'un gage : "
    "{%tr for b in garantie_bijoux %} avec {{ b.nature }}, {{ b.poids }}, "
    "{{ b.description }}. Pour les responsables de filiale : "
    "{%tr for r in responsables %} avec {{ r.poste }}, {{ r.nom }}, "
    "{{ r.prenom }}, {{ r.telephone }}, {{ r.nom_complet }}."
)


# --------------------------------------------------------------------------- #
# Construction du contexte
# --------------------------------------------------------------------------- #
def build_context(
    application,
    extra_values: dict | None = None,
    *,
    primary_engagement=None,
) -> dict:
    """Assemble le dictionnaire de variables pour un dossier de crédit."""
    from apps.clients.models import (
        Civility,
        Client,
        IdDocumentType,
        LegalForm,
        MaritalStatus,
    )
    from apps.credits.amounts import reference_amount
    from apps.credits.models import (
        ActivitySector,
        ContractType,
        Periodicity,
        PurposeType,
        RepaymentMechanism,
    )
    from apps.credits.services import compute_amortization_schedule

    client = application.client
    tenant = application.tenant
    agency = application.agency
    product = application.product
    currency = application.currency or "XOF"
    currency_label = "francs CFA" if currency == "XOF" else currency

    amount = reference_amount(application)
    from apps.credits.pricing import quote_pricing
    pricing = quote_pricing(application)
    rate = Decimal(pricing["rates"]["interest_rate"])

    ctx: dict = {}

    # --- Filiale & date -------------------------------------------------- #
    ctx["date_du_jour"] = fmt_date(timezone.now().date())
    ctx["filiale_nom"] = getattr(tenant, "name", "") if tenant else ""
    ctx["filiale_adresse"] = getattr(tenant, "address", "") if tenant else ""
    ctx["filiale_telephone"] = getattr(tenant, "phone", "") if tenant else ""
    ctx["filiale_email"] = getattr(tenant, "email", "") if tenant else ""
    ctx["filiale_pays"] = getattr(tenant, "country", "") if tenant else ""
    ctx["agence_nom"] = getattr(agency, "name", "") if agency else ""
    ctx["agence_code"] = getattr(agency, "code", "") if agency else ""
    ctx["agence_region"] = getattr(agency, "region", "") if agency else ""
    ctx["agence_adresse"] = getattr(agency, "address", "") if agency else ""
    ctx["ville_agence"] = (
        (getattr(agency, "region", "") if agency else "")
        or client.city
        or (getattr(tenant, "country", "") if tenant else "")
    )
    chef_nom = getattr(agency, "manager_last_name", "") if agency else ""
    chef_prenom = getattr(agency, "manager_first_name", "") if agency else ""
    ctx["agence_chef_nom"] = chef_nom or ""
    ctx["agence_chef_prenom"] = chef_prenom or ""
    ctx["agence_chef_nom_complet"] = f"{chef_prenom} {chef_nom}".strip()
    ctx["agence_chef_telephone"] = (
        getattr(agency, "manager_phone", "") if agency else ""
    ) or ""
    # Alias pratique : « AGE01 — Agence Centre »
    if agency:
        ctx["agence"] = f"{agency.code} — {agency.name}".strip(" —")
    else:
        ctx["agence"] = ""

    # Responsables de la filiale (DG, Directeur d'exploitation, …)
    officers = list(tenant.officers.all()) if tenant else []
    responsables = [
        {
            "poste": o.title or "",
            "nom": o.last_name or "",
            "prenom": o.first_name or "",
            "telephone": o.phone or "",
            "nom_complet": o.display_name,
        }
        for o in officers
    ]
    ctx["responsables"] = responsables
    ctx["nombre_responsables"] = len(responsables)
    ctx["responsables_texte"] = " ; ".join(
        " — ".join(
            p for p in [
                r["poste"],
                r["nom_complet"],
                r["telephone"],
            ] if p
        )
        for r in responsables
    )
    for idx, r in enumerate(responsables[:5], start=1):
        for key, value in r.items():
            ctx[f"responsable{idx}_{key}"] = value
            if idx == 1:
                ctx[f"responsable_{key}"] = value

    # --- Dossier --------------------------------------------------------- #
    ctx["dossier_reference"] = application.reference or ""
    objet = _display(application.purpose_type, PurposeType.choices)
    ctx["dossier_objet"] = objet
    ctx["objet_financement"] = objet
    ctx["dossier_details"] = application.purpose or ""
    ctx["dossier_date_decision"] = fmt_date(application.decision_date)

    # --- Client ---------------------------------------------------------- #
    ctx["client_type"] = _client_type_label(client)
    ctx["client_civilite"] = _display(client.civility, Civility.choices)
    ctx["client_nom"] = client.last_name or ""
    ctx["client_prenom"] = client.first_name or ""
    ctx["client_nom_complet"] = client.display_name
    ctx["client_cni_type"] = _display(
        client.id_document_type, IdDocumentType.choices
    )
    ctx["client_cni"] = client.national_id or ""
    ctx["client_cni_delivrance"] = fmt_date(client.id_document_issue_date)
    ctx["client_cni_expiration"] = fmt_date(client.id_document_expiry_date)
    ctx["client_adresse"] = client.address or ""
    ctx["client_ville"] = client.city or ""
    ctx["client_pays"] = client.country or ""
    ctx["client_telephone"] = client.phone or ""
    extra_phones = list(client.phones.all())
    all_numbers = [client.phone] if client.phone else []
    all_numbers.extend(ph.number for ph in extra_phones if ph.number)
    ctx["client_telephones"] = " ; ".join(all_numbers)
    ctx["client_telephones_autres"] = " ; ".join(
        " — ".join(p for p in [ph.label, ph.number] if p)
        for ph in extra_phones
    )
    ctx["client_telephone2"] = extra_phones[0].number if len(extra_phones) > 0 else ""
    ctx["client_telephone3"] = extra_phones[1].number if len(extra_phones) > 1 else ""
    ctx["client_email"] = client.email or ""
    ctx["client_profession"] = client.profession or ""
    ctx["client_date_naissance"] = fmt_date(client.birth_date)
    ctx["client_lieu_naissance"] = client.birth_country or ""
    ctx["client_pays_naissance"] = client.birth_country or ""
    ctx["client_nationalite"] = client.nationality or ""
    ctx["client_situation_matrimoniale"] = _display(
        client.marital_status, MaritalStatus.choices
    )
    ctx["client_kyc"] = _display(client.kyc_status, Client.KycStatus.choices)
    ctx["client_kyc_valide_le"] = fmt_date(client.kyc_validated_at)
    client_agency = getattr(client, "agency", None)
    ctx["client_agence_nom"] = getattr(client_agency, "name", "") if client_agency else ""
    ctx["client_agence_code"] = getattr(client_agency, "code", "") if client_agency else ""
    ctx["client_matricule"] = client.cbs_client_id or client.reference or ""
    ctx["client_matricule_cbs"] = client.cbs_client_id or ""
    compte_cbs = (
        client.cbs_account_number or application.client_account_number or ""
    )
    ctx["client_compte"] = compte_cbs
    ctx["client_compte_cbs"] = compte_cbs
    ctx["compte_cbs"] = compte_cbs

    ctx["client_conjoint_nom"] = client.spouse_last_name or ""
    ctx["client_conjoint_prenom"] = client.spouse_first_name or ""
    ctx["client_conjoint_nom_complet"] = _full_name(
        client.spouse_first_name, client.spouse_last_name
    )
    ctx["client_conjoint_telephone"] = client.spouse_phone or ""
    ctx["client_conjoint_profession"] = client.spouse_profession or ""
    ctx["client_pere_nom"] = client.father_last_name or ""
    ctx["client_pere_prenom"] = client.father_first_name or ""
    ctx["client_pere_nom_complet"] = _full_name(
        client.father_first_name, client.father_last_name
    )
    ctx["client_mere_nom"] = client.mother_last_name or ""
    ctx["client_mere_prenom"] = client.mother_first_name or ""
    ctx["client_mere_nom_complet"] = _full_name(
        client.mother_first_name, client.mother_last_name
    )

    # --- Entreprise ------------------------------------------------------ #
    ctx["societe_nom"] = client.company_name or ""
    ctx["societe_forme"] = _display(client.legal_form, LegalForm.choices)
    ctx["societe_rccm"] = client.rccm or ""
    ctx["societe_ninea"] = client.ifu or ""
    ctx["societe_ifu"] = client.ifu or ""
    ctx["societe_siege"] = client.address or ""
    ctx["societe_ville"] = client.city or ""
    ctx["societe_telephone"] = client.phone or ""
    ctx["societe_email"] = client.email or ""
    # Activité / effectif : portés par l'analyse financière (plus sur le dossier).
    analysis = (
        application.financial_analyses.filter(is_reference=True)
        .order_by("-created_at")
        .first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    activite = ""
    effectif = ""
    if analysis is not None:
        activite = (
            (analysis.sub_sector or "").strip()
            or _display(analysis.sector, ActivitySector.choices)
        )
        if analysis.workforce_count is not None:
            effectif = analysis.workforce_count
    ctx["societe_activite"] = activite
    ctx["societe_date_creation"] = fmt_date(application.activity_start_date)
    ctx["societe_matricule"] = client.cbs_client_id or client.reference or ""
    ctx["societe_compte"] = compte_cbs
    ctx["societe_compte_cbs"] = compte_cbs
    ctx["societe_effectif"] = effectif

    # --- Gérant / représentant légal ------------------------------------ #
    gerant_nom = f"{client.manager_first_name} {client.manager_last_name}".strip()
    ctx["gerant_nom"] = gerant_nom
    ctx["gerant_nom_seul"] = client.manager_last_name or ""
    ctx["gerant_prenom"] = client.manager_first_name or ""
    ctx["gerant_telephone"] = client.manager_phone or ""
    ctx["gerant_email"] = client.manager_email or ""
    ctx["gerant_adresse"] = client.manager_address or ""
    ctx["gerant_piece_type"] = _display(
        client.manager_id_document_type, IdDocumentType.choices
    )
    ctx["gerant_piece_numero"] = client.manager_id_document_number or ""
    ctx["gerant_piece_delivrance"] = fmt_date(
        client.manager_id_document_issue_date
    )
    ctx["gerant_piece_expiration"] = fmt_date(
        client.manager_id_document_expiry_date
    )
    ctx["gerant_date_naissance"] = fmt_date(client.manager_birth_date)
    ctx["gerant_pays_naissance"] = client.manager_birth_country or ""
    ctx["gerant_ville_naissance"] = client.manager_birth_city or ""
    ctx["gerant_poste"] = client.manager_position or ""
    ctx["representant"] = gerant_nom

    # --- Crédit ---------------------------------------------------------- #
    ctx["produit"] = getattr(product, "label", "") if product else ""
    ctx["montant_demande"] = fmt_money(application.amount_requested)
    ctx["montant_accorde"] = fmt_money(amount)
    ctx["montant_accorde_lettres"] = fmt_amount_words(amount, currency_label)
    ctx["taux"] = fmt_money(rate) if rate is not None else ""
    ctx["frais_dossier"] = fmt_money(Decimal(pricing["rates"]["fees_rate"]))
    ctx["tarification"] = pricing
    ctx["frais_detail"] = pricing["fees"]["lines"]
    ctx["frais_total"] = fmt_money(Decimal(pricing["fees"]["total"] or "0"))
    ctx["taxes_frais_total"] = fmt_money(Decimal(pricing["fees"].get("total_taxes") or "0"))
    ctx["taux_epargne"] = (
        fmt_money(application.mandatory_savings_rate)
        if application.mandatory_savings_rate else ""
    )
    ctx["duree_mois"] = application.duration_months or ""
    ctx["periodicite"] = _display(application.periodicity, Periodicity.choices)
    mecanisme = _display(
        application.repayment_mechanism, RepaymentMechanism.choices
    )
    ctx["mecanisme_remboursement"] = mecanisme
    ctx["dossier_mecanisme"] = mecanisme
    ctx["premiere_echeance"] = fmt_date(application.first_due_date)
    ctx["derniere_echeance"] = fmt_date(application.last_due_date)
    ctx["cout_total_projet"] = fmt_money(application.project_total_cost)
    ctx["apport_personnel"] = fmt_money(application.personal_contribution)
    ctx["quotite"] = fmt_money(application.financed_quota) if application.financed_quota else ""
    ctx["devise"] = currency

    ctx["employeur"] = application.employer_name or ""
    ctx["type_contrat"] = _display(application.contract_type, ContractType.choices)
    ctx["personnes_a_charge"] = (
        application.dependents_count
        if application.dependents_count is not None
        else ""
    )
    ctx["domiciliation_salaire"] = (
        "Oui" if application.salary_domiciliation else "Non"
    )

    # --- Assurance ------------------------------------------------------- #
    ctx["assurance_adi"] = "Oui" if application.has_credit_insurance else "Non"
    ctx["assurance_compagnie"] = application.insurance_company or ""
    ctx["assurance_prime"] = fmt_money(application.insurance_premium)

    # --- Échéancier ------------------------------------------------------ #
    echeancier = []
    total_interets = Decimal("0")
    total_rembourse = Decimal("0")
    mensualite = ""
    if amount and rate is not None and application.duration_months:
        try:
            schedule = compute_amortization_schedule(
                principal=amount,
                annual_rate=rate,
                duration_months=application.duration_months,
                periodicity=application.periodicity,
                first_due_date=application.first_due_date,
                savings_rate=application.mandatory_savings_rate or 0,
                mechanism=application.repayment_mechanism or "DEGRESSIVE",
            )
            for row in schedule:
                total_interets += Decimal(str(row["interest"]))
                total_rembourse += Decimal(str(row["total"]))
                echeancier.append({
                    "numero": row["number"],
                    "date": fmt_date(row["due_date"]),
                    "capital": fmt_money(row["principal"]),
                    "interet": fmt_money(row["interest"]),
                    "epargne": fmt_money(row["savings"]),
                    "total": fmt_money(row["total"]),
                    "solde": fmt_money(row["balance"]),
                })
            if schedule:
                mensualite = fmt_money(schedule[0]["total"])
        except Exception:
            echeancier = []
    ctx["echeancier"] = echeancier
    ctx["mensualite"] = mensualite
    ctx["total_interets"] = fmt_money(total_interets) if echeancier else ""
    ctx["total_a_rembourser"] = fmt_money(total_rembourse) if echeancier else ""

    # --- Garanties ------------------------------------------------------- #
    from apps.guarantees.models import (
        DocumentType,
        FinancialType,
        Guarantee,
        MatrimonialRegime,
        OccupancyStatus,
        PledgeCategory,
    )

    def build_garantie(g) -> dict:
        gt = g.guarantee_type
        bijoux = [
            {
                "nature": j.nature or "",
                "poids": (f"{j.weight:g}" if j.weight is not None else ""),
                "description": j.description or "",
            }
            for j in g.jewelry_items.all()
        ]
        bijoux_texte = " ; ".join(
            " ".join(
                p for p in [
                    b["nature"],
                    f"{b['poids']} g" if b["poids"] else "",
                    f"({b['description']})" if b["description"] else "",
                ] if p
            )
            for b in bijoux
        )
        d = {
            "type": g.get_guarantee_type_display(),
            "categorie_gage": _display(g.pledge_category, PledgeCategory.choices),
            "reference": g.reference or "",
            "description": g.description or "",
            "proprietaires": g.owners or "",
            "proprietaire_nom": g.owner_last_name or "",
            "proprietaire_prenom": g.owner_first_name or "",
            "proprietaire_nom_complet": (
                f"{g.owner_first_name} {g.owner_last_name}".strip()
            ),
            "proprietaire_situation_matrimoniale": g.owner_marital_status or "",
            "regime_matrimonial": _display(
                g.matrimonial_regime, MatrimonialRegime.choices
            ),
            "valeur": fmt_money(g.current_value or g.expertise_value),
            "valeur_expertise": fmt_money(g.expertise_value),
            "valeur_consideree": fmt_money(g.value_to_consider),
            "ratio_ltv": (f"{g.ltv_ratio:g}" if g.ltv_ratio is not None else ""),
            "assuree": "Oui" if g.is_insured else "Non",
            "assurance_ref": g.insurance_reference or "",
            "statut": g.get_status_display(),
            # Expertise (commun véhicule / bijou / hypothèque)
            "expert": g.expert_name or "",
            "cabinet_expertise": g.expertise_firm or "",
            "date_expertise": fmt_date(g.expertise_date),
            # Hypothèque / immobilier
            "document_type": _display(g.document_type, DocumentType.choices),
            "document_numero": g.document_number or "",
            "document_date": fmt_date(g.document_issue_date),
            "adresse_bien": g.address or "",
            "statut_occupation": _display(
                g.occupancy_status, OccupancyStatus.choices
            ),
            # Gage véhicule
            "marque": g.brand or "",
            "modele": g.model_name or "",
            "immatriculation": g.registration or "",
            "chassis": g.chassis_number or "",
            "moteur": g.engine_number or "",
            "puissance": g.power or "",
            "annee": g.first_registration_year or "",
            "date_acquisition": fmt_date(g.acquisition_date),
            "valeur_acquisition": fmt_money(g.acquisition_value),
            "valeur_revente": fmt_money(g.resale_value),
            "date_estimation": fmt_date(g.estimation_date),
            "info_complementaire": g.additional_info or "",
            # Gage bijou / objet de valeur
            "cours_matiere": fmt_money(g.raw_material_price),
            "bijoux": bijoux,
            "bijoux_texte": bijoux_texte,
            "nombre_bijoux": len(bijoux),
            # Garantie financière
            "type_financier": _display(g.financial_type, FinancialType.choices),
            "numero_compte": g.account_number or "",
            "solde": fmt_money(g.balance),
            "taux_remuneration": (
                f"{g.remuneration_rate:g}" if g.remuneration_rate is not None else ""
            ),
            "isin": g.isin_code or "",
            "echeance_depot": fmt_date(g.deposit_maturity_date),
            "decote_securite": (
                f"{g.security_discount:g}" if g.security_discount is not None else ""
            ),
        }
        if gt == Guarantee.GuaranteeType.MORTGAGE:
            d["details"] = ", ".join(
                p for p in [
                    d["document_type"],
                    f"n°{d['document_numero']}" if d["document_numero"] else "",
                    d["adresse_bien"],
                ] if p
            )
        elif gt == Guarantee.GuaranteeType.PLEDGE and g.pledge_category == "VEHICLE":
            d["details"] = " ".join(
                p for p in [
                    d["marque"], d["modele"], d["immatriculation"],
                    f"(châssis {d['chassis']})" if d["chassis"] else "",
                ] if p
            )
        elif gt == Guarantee.GuaranteeType.PLEDGE and g.pledge_category == "VALUABLE":
            d["details"] = bijoux_texte or d["description"]
        elif gt == Guarantee.GuaranteeType.FINANCIAL:
            d["details"] = ", ".join(
                p for p in [
                    d["type_financier"],
                    f"compte n°{d['numero_compte']}" if d["numero_compte"] else "",
                    f"solde {d['solde']}" if d["solde"] else "",
                ] if p
            )
        else:
            d["details"] = d["description"]
        return d

    garanties = [build_garantie(g) for g in application.guarantees.all()]
    ctx["garanties"] = garanties
    ctx["nombre_garanties"] = len(garanties)
    total_garanties = sum(
        Decimal(str(g.current_value or g.expertise_value or 0))
        for g in application.guarantees.all()
    )
    ctx["total_garanties"] = fmt_money(total_garanties) if garanties else ""
    ctx["garanties_texte"] = " ; ".join(
        f"{g['type']} ({g['valeur']})".strip() for g in garanties
    )

    # --- Cautions -------------------------------------------------------- #
    def build_caution(engagement) -> dict:
        from apps.clients.models import LegalForm

        s = engagement.surety
        if not s:
            return {
                "nom": "", "prenom": "", "nom_complet": "", "type": "",
                "cni_type": "", "cni": "", "piece_rccm": "", "adresse": "",
                "ville": "", "telephone": "", "email": "", "activite": "",
                "date_naissance": "", "lieu_naissance": "", "revenu": "",
                "montant": fmt_money(engagement.amount),
                "montant_lettres": fmt_amount_words(engagement.amount, currency_label),
                "date_signature": fmt_date(engagement.signed_date),
                "type_engagement": getattr(
                    engagement, "get_engagement_type_display", lambda: ""
                )(),
                "type_engagement_code": getattr(engagement, "engagement_type", "") or "",
                "raison_sociale": "", "forme_juridique": "", "ifu": "", "rccm": "",
                "gerant_nom": "", "gerant_nom_seul": "", "gerant_prenom": "",
                "gerant_poste": "", "gerant_telephone": "", "gerant_email": "",
                "gerant_adresse": "", "gerant_date_naissance": "",
                "gerant_pays_naissance": "", "gerant_ville_naissance": "",
                "gerant_piece_type": "", "gerant_piece_numero": "",
                "gerant_piece_delivrance": "", "gerant_piece_expiration": "",
            }
        is_moral = s.surety_type == s.SuretyType.MORAL
        gerant_nom = f"{s.manager_first_name} {s.manager_last_name}".strip()
        rccm = s.rccm or s.identifier or ""
        type_engagement = ""
        type_engagement_code = getattr(engagement, "engagement_type", "") or ""
        if hasattr(engagement, "get_engagement_type_display"):
            type_engagement = engagement.get_engagement_type_display()
        d = {
            "nom": (s.company_name if is_moral else (s.last_name or s.name or "")),
            "prenom": "" if is_moral else (s.first_name or ""),
            "nom_complet": s.display_name,
            "type": s.get_surety_type_display(),
            "type_engagement": type_engagement,
            "type_engagement_code": type_engagement_code,
            "cni_type": _display(s.id_document_type, IdDocumentType.choices),
            "cni": s.national_id or "",
            "piece_rccm": rccm,
            "adresse": s.address or "",
            "ville": s.city or "",
            "telephone": s.phone or "",
            "email": s.email or "",
            "activite": s.activity or "",
            "date_naissance": fmt_date(s.birth_date),
            "lieu_naissance": s.birth_country or "",
            "revenu": fmt_money(s.estimated_income),
            "montant": fmt_money(engagement.amount),
            "montant_lettres": fmt_amount_words(engagement.amount, currency_label),
            "date_signature": fmt_date(engagement.signed_date),
            # Entreprise
            "raison_sociale": s.company_name or (s.name if is_moral else ""),
            "forme_juridique": _display(s.legal_form, LegalForm.choices),
            "ifu": s.ifu or "",
            "rccm": rccm,
            # Gérant
            "gerant_nom": gerant_nom,
            "gerant_nom_seul": s.manager_last_name or "",
            "gerant_prenom": s.manager_first_name or "",
            "gerant_poste": s.manager_position or "",
            "gerant_telephone": s.manager_phone or "",
            "gerant_email": s.manager_email or "",
            "gerant_adresse": s.manager_address or "",
            "gerant_date_naissance": fmt_date(s.manager_birth_date),
            "gerant_pays_naissance": s.manager_birth_country or "",
            "gerant_ville_naissance": s.manager_birth_city or "",
            "gerant_piece_type": _display(
                s.manager_id_document_type, IdDocumentType.choices
            ),
            "gerant_piece_numero": s.manager_id_document_number or "",
            "gerant_piece_delivrance": fmt_date(s.manager_id_document_issue_date),
            "gerant_piece_expiration": fmt_date(s.manager_id_document_expiry_date),
        }
        return d

    engagements = list(
        application.surety_engagements.select_related("surety").all()
    )
    if primary_engagement is not None:
        primary_id = getattr(primary_engagement, "pk", None)
        engagements = sorted(
            engagements,
            key=lambda e: (0 if e.pk == primary_id else 1, str(e.pk)),
        )
    cautions = [build_caution(e) for e in engagements]
    ctx["cautions"] = cautions
    ctx["nombre_cautions"] = len(cautions)
    total_cautions = sum(Decimal(str(e.amount or 0)) for e in engagements)
    ctx["total_cautions"] = fmt_money(total_cautions) if cautions else ""
    ctx["cautions_texte"] = " ; ".join(
        f"{c['nom_complet']} ({c['montant']})".strip() for c in cautions
    )

    # --- Raccourcis scalaires (1re, 2e, 3e caution / garantie) ----------- #
    # Permettent d'utiliser {{ caution_nom }}, {{ caution1_cni }},
    # {{ garantie_details }}, {{ garantie2_valeur }}… sans écrire de boucle.
    for idx, c in enumerate(cautions[:5], start=1):
        for key, value in c.items():
            ctx[f"caution{idx}_{key}"] = value
            if idx == 1:
                ctx[f"caution_{key}"] = value
    for idx, g in enumerate(garanties[:5], start=1):
        for key, value in g.items():
            ctx[f"garantie{idx}_{key}"] = value
            if idx == 1:
                ctx[f"garantie_{key}"] = value

    # --- Variables manuelles (priorité aux valeurs saisies) -------------- #
    if extra_values:
        for key, value in extra_values.items():
            if value not in (None, ""):
                ctx[str(key)] = value

    return ctx
