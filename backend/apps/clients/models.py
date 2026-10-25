"""Clients particuliers, professionnels et entreprises (avec KYC)."""
from django.db import models
from django.utils import timezone

from apps.common.files import safe_filename
from apps.common.models import AuthoredModel, TenantScopedModel
from apps.common.tenancy import get_current_tenant_id


def client_file_path(instance, filename):
    """Chemin de stockage des pièces jointes d'un client (scans, photo)."""
    return f"clients/{instance.tenant_id}/{instance.id}/{safe_filename(filename)}"


class Civility(models.TextChoices):
    MR = "MR", "Monsieur"
    MRS = "MRS", "Madame"
    MISS = "MISS", "Mademoiselle"


class MaritalStatus(models.TextChoices):
    SINGLE = "SINGLE", "Célibataire"
    MARRIED = "MARRIED", "Marié(e)"
    DIVORCED = "DIVORCED", "Divorcé(e)"
    WIDOWED = "WIDOWED", "Veuf/Veuve"


class IdDocumentType(models.TextChoices):
    PASSPORT = "PASSPORT", "Passeport"
    CNI = "CNI", "Carte nationale d'identité"
    DRIVING_LICENSE = "DRIVING_LICENSE", "Permis de conduire"
    CONSULAR_CARD = "CONSULAR_CARD", "Carte consulaire"


class LegalForm(models.TextChoices):
    SARL = "SARL", "SARL"
    SA = "SA", "SA"
    ASSOCIATION = "ASSOCIATION", "Association"
    INDIVIDUAL = "INDIVIDUAL", "Entreprise individuelle"
    SASU = "SASU", "SASU"
    SAS = "SAS", "SAS"
    EURL = "EURL", "EURL"
    SNC_SCS = "SNC_SCS", "SNC / SCS"


class Client(TenantScopedModel, AuthoredModel):
    """Client d'une filiale. Les champs varient selon le type."""

    class ClientType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Personne physique"
        PROFESSIONAL = "PROFESSIONAL", "Groupement"
        CORPORATE = "CORPORATE", "Personne morale"

    class KycStatus(models.TextChoices):
        PENDING = "PENDING", "À vérifier"
        VALIDATED = "VALIDATED", "Validé"
        REJECTED = "REJECTED", "Rejeté"
        EXPIRED = "EXPIRED", "Expiré"

    reference = models.CharField(
        "matricule", max_length=30, blank=True, db_index=True,
        help_text="Généré automatiquement à la création.",
    )
    client_type = models.CharField(max_length=20, choices=ClientType.choices)
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients",
        verbose_name="agence",
    )

    # ------------------------------------------------------------------ #
    # Personne physique
    # ------------------------------------------------------------------ #
    civility = models.CharField(
        "civilité", max_length=10, choices=Civility.choices, blank=True
    )
    first_name = models.CharField("prénom", max_length=100, blank=True)
    last_name = models.CharField("nom", max_length=100, blank=True)
    birth_date = models.DateField("date de naissance", null=True, blank=True)
    birth_country = models.CharField("pays de naissance", max_length=100, blank=True)
    country = models.CharField("pays", max_length=100, blank=True)
    marital_status = models.CharField(
        "situation matrimoniale", max_length=15,
        choices=MaritalStatus.choices, blank=True,
    )
    nationality = models.CharField("nationalité", max_length=100, blank=True)
    profession = models.CharField("profession", max_length=150, blank=True)

    # Pièce d'identité (personne physique)
    id_document_type = models.CharField(
        "type de pièce d'identité", max_length=20,
        choices=IdDocumentType.choices, blank=True,
    )
    national_id = models.CharField(
        "n° de la pièce d'identité", max_length=50, blank=True
    )
    id_document_issue_date = models.DateField(
        "date d'établissement de la pièce", null=True, blank=True
    )
    id_document_expiry_date = models.DateField(
        "date d'expiration de la pièce", null=True, blank=True
    )
    id_document_scan = models.FileField(
        "scan de la pièce d'identité", upload_to=client_file_path, max_length=255, blank=True
    )
    photo = models.ImageField(
        "photo", upload_to=client_file_path, max_length=255, blank=True
    )

    # Conjoint (si marié)
    spouse_last_name = models.CharField("nom du conjoint", max_length=100, blank=True)
    spouse_first_name = models.CharField(
        "prénom du conjoint", max_length=100, blank=True
    )
    spouse_phone = models.CharField(
        "téléphone du conjoint", max_length=50, blank=True
    )
    spouse_profession = models.CharField(
        "profession du conjoint", max_length=150, blank=True
    )

    # Parents
    father_last_name = models.CharField("nom du père", max_length=100, blank=True)
    father_first_name = models.CharField(
        "prénom du père", max_length=100, blank=True
    )
    mother_last_name = models.CharField("nom de la mère", max_length=100, blank=True)
    mother_first_name = models.CharField(
        "prénom de la mère", max_length=100, blank=True
    )

    # ------------------------------------------------------------------ #
    # Personne morale (entreprise)
    # ------------------------------------------------------------------ #
    company_name = models.CharField("raison sociale", max_length=255, blank=True)
    legal_form = models.CharField(
        "statut juridique", max_length=20, choices=LegalForm.choices, blank=True
    )
    ifu = models.CharField("numéro IFU", max_length=50, blank=True)
    rccm = models.CharField("numéro RCCM", max_length=50, blank=True)
    ifu_scan = models.FileField(
        "scan IFU", upload_to=client_file_path, max_length=255, blank=True
    )
    rccm_scan = models.FileField(
        "scan RCCM", upload_to=client_file_path, max_length=255, blank=True
    )

    # Gérant de l'entreprise
    manager_last_name = models.CharField("nom du gérant", max_length=100, blank=True)
    manager_first_name = models.CharField(
        "prénom du gérant", max_length=100, blank=True
    )
    manager_phone = models.CharField(
        "téléphone du gérant", max_length=50, blank=True
    )
    manager_email = models.EmailField("email du gérant", blank=True)
    manager_address = models.CharField(
        "adresse du gérant", max_length=255, blank=True
    )
    manager_id_document_type = models.CharField(
        "type de pièce du gérant", max_length=20,
        choices=IdDocumentType.choices, blank=True,
    )
    manager_id_document_number = models.CharField(
        "n° de pièce du gérant", max_length=50, blank=True
    )
    manager_id_document_issue_date = models.DateField(
        "date d'établissement de la pièce du gérant", null=True, blank=True
    )
    manager_id_document_expiry_date = models.DateField(
        "date d'expiration de la pièce du gérant", null=True, blank=True
    )
    manager_id_document_scan = models.FileField(
        "scan pièce du gérant", upload_to=client_file_path, max_length=255, blank=True
    )
    manager_position = models.CharField(
        "poste du gérant dans l'entreprise", max_length=150, blank=True
    )
    manager_birth_date = models.DateField(
        "date de naissance du gérant", null=True, blank=True
    )
    manager_birth_country = models.CharField(
        "pays de naissance du gérant", max_length=100, blank=True
    )
    manager_birth_city = models.CharField(
        "ville de naissance du gérant", max_length=100, blank=True
    )

    # ------------------------------------------------------------------ #
    # Coordonnées communes
    # ------------------------------------------------------------------ #
    phone = models.CharField("téléphone principal", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    city = models.CharField("ville", max_length=100, blank=True)
    postal_box = models.CharField("boîte postale", max_length=50, blank=True)
    head_office = models.CharField("siège social", max_length=255, blank=True)
    sigle = models.CharField("sigle", max_length=50, blank=True)

    # ------------------------------------------------------------------ #
    # Core Banking — mapping 1:1 de la situation adhérent (adh/situation)
    # ------------------------------------------------------------------ #
    cbs_client_id = models.CharField(
        "matricule Core Banking", max_length=50, blank=True, db_index=True,
        help_text="codeAdherent",
    )
    cbs_account_number = models.CharField(
        "n° de compte Core Banking", max_length=50, blank=True,
        help_text="numManuel",
    )
    cbs_full_name = models.CharField(
        "nom adhérent CBS", max_length=255, blank=True,
        help_text="nomAdherent",
    )
    cbs_order_number = models.CharField(
        "n° d'ordre CBS", max_length=50, blank=True,
        help_text="numOrdre",
    )
    cbs_profession_id = models.CharField(
        "id profession CBS", max_length=50, blank=True,
        help_text="idProfession",
    )
    cbs_nationality_id = models.CharField(
        "id nationalité CBS", max_length=50, blank=True,
        help_text="idNationalite",
    )
    cbs_sector_id = models.CharField(
        "id secteur d'activité CBS", max_length=50, blank=True,
        help_text="idSecteurActivite",
    )
    cbs_client_type_id = models.CharField(
        "id type client CBS", max_length=50, blank=True,
        help_text="idTypeClient",
    )
    cbs_zone_id = models.CharField(
        "id zone CBS", max_length=50, blank=True,
        help_text="idZone",
    )
    cbs_savings_product_id = models.CharField(
        "id produit épargne CBS", max_length=50, blank=True,
        help_text="idProduitEpg",
    )
    cbs_signature_count = models.PositiveIntegerField(
        "nombre de signatures CBS", null=True, blank=True,
        help_text="nbreSignature",
    )
    cbs_distance = models.DecimalField(
        "distance CBS",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="distance",
    )
    cbs_registration_date = models.DateField(
        "date d'inscription CBS", null=True, blank=True,
        help_text="dateInscription",
    )
    cbs_creation_date = models.DateField(
        "date de création CBS", null=True, blank=True,
        help_text="dateCreation",
    )
    cbs_credit_limit = models.DecimalField(
        "limite de crédit CBS",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="limitCredit",
    )
    cbs_est_valide = models.BooleanField(
        "adhérent valide CBS", null=True, blank=True,
        help_text="estValide",
    )
    cbs_point_of_service_id = models.CharField(
        "point de service CBS", max_length=50, blank=True,
        help_text="idPointService",
    )
    cbs_point_of_service_name = models.CharField(
        "libellé point de service CBS", max_length=255, blank=True,
        help_text="nomPointService",
    )
    cbs_external_id = models.CharField(
        "identifiant externe CBS", max_length=100, blank=True,
        help_text="externalId",
    )
    cbs_context = models.CharField(
        "contexte réponse CBS", max_length=100, blank=True,
        help_text="context",
    )
    cbs_message = models.CharField(
        "message réponse CBS", max_length=255, blank=True,
        help_text="message",
    )
    cbs_synced_at = models.DateTimeField(
        "dernière synchronisation CBS", null=True, blank=True,
    )
    cbs_situation = models.JSONField(
        "situation CBS (copie brute)",
        default=dict,
        blank=True,
        help_text=(
            "Copie de sauvegarde de la dernière réponse CBS "
            "(normalisée + raw). La source métier reste les colonnes ci-dessus."
        ),
    )

    # KYC
    custom_fields = models.JSONField(default=dict, blank=True)
    kyc_status = models.CharField(
        "statut KYC", max_length=20,
        choices=KycStatus.choices, default=KycStatus.PENDING,
    )
    kyc_validated_at = models.DateField("KYC validé le", null=True, blank=True)

    is_active = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "client_type"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["tenant", "reference"]),
        ]

    def __str__(self):
        return self.display_name

    @property
    def is_legal_entity(self) -> bool:
        """Entreprise ou groupement : fiche morale, pas particulier."""
        return self.client_type in (
            self.ClientType.CORPORATE,
            self.ClientType.PROFESSIONAL,
        )

    @property
    def display_name(self):
        if self.is_legal_entity:
            return self.company_name or "(sans raison sociale)"
        return f"{self.first_name} {self.last_name}".strip() or "(client sans nom)"

    def _generate_reference(self):
        """Génère un matricule unique par filiale (ex. PAR-2026-00001)."""
        if self.client_type == self.ClientType.CORPORATE:
            prefix = "ENT"
        elif self.client_type == self.ClientType.PROFESSIONAL:
            prefix = "GRP"
        else:
            prefix = "PAR"
        base = f"{prefix}-{timezone.now().year}-"
        existing = (
            Client.all_tenants.filter(
                tenant_id=self.tenant_id, reference__startswith=base
            ).count()
        )
        seq = existing + 1
        ref = f"{base}{seq:05d}"
        while Client.all_tenants.filter(
            tenant_id=self.tenant_id, reference=ref
        ).exists():
            seq += 1
            ref = f"{base}{seq:05d}"
        return ref

    def save(self, *args, **kwargs):
        # S'assure que le tenant est résolu avant de générer le matricule.
        if self.tenant_id is None:
            current = get_current_tenant_id()
            if current is not None:
                self.tenant_id = current
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)


class ClientPhone(TenantScopedModel):
    """Numéro de téléphone additionnel d'un client (multi-numéros)."""

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="phones",
        verbose_name="client",
    )
    number = models.CharField("numéro", max_length=50)
    label = models.CharField("libellé", max_length=50, blank=True)

    class Meta:
        verbose_name = "téléphone client"
        verbose_name_plural = "téléphones client"
        ordering = ["created_at"]

    def __str__(self):
        return self.number
