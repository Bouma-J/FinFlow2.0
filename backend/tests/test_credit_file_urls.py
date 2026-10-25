import importlib
import inspect
from unittest.mock import patch

from django.db import models
from rest_framework import serializers

from apps.common.storage_urls import presign_file_fields
from apps.contracts.serializers import (
    ContractTemplateSerializer,
    GeneratedContractSerializer,
)
from apps.credits.serializers import (
    CreditApplicationSerializer,
    CreditDocumentSerializer,
    FinancialDocumentSerializer,
    StockPhotoSerializer,
)
from apps.documents.serializers import DocumentSerializer
from apps.guarantees.serializers import (
    GuaranteeDocumentSerializer,
    GuaranteeFormalizationRequestSerializer,
    GuaranteePhotoSerializer,
    GuaranteeSerializer,
)
from apps.sureties.serializers import SuretyDocumentSerializer, SuretySerializer


def test_presign_fields_replaces_storages_url_without_bucket():
    field = type("F", (), {"name": "credits/tid/aid/Demande.pdf"})()
    inst = type("D", (), {"file": field})()
    raw = "http://10.0.0.8:9000/credits/tid/aid/Demande.pdf"
    signed = (
        "http://10.0.0.8:9000/finflow-documents/credits/tid/aid/Demande.pdf"
        "?X-Amz-Signature=abc"
    )
    with patch(
        "apps.common.storage_urls.file_download_url", return_value=signed
    ):
        out = presign_file_fields({"file": raw}, inst, "file")
    assert "finflow-documents" in out["file"]
    assert "X-Amz-Signature" in out["file"]
    assert not out["file"].startswith("http://10.0.0.8:9000/credits/")


def test_file_serializers_rewrite_exposed_file_fields():
    """Chaque serializer qui expose un FileField doit le réécrire."""
    expected = {
        FinancialDocumentSerializer: ("file",),
        StockPhotoSerializer: ("image",),
        CreditDocumentSerializer: ("file",),
        CreditApplicationSerializer: ("request_letter_scan",),
        GuaranteePhotoSerializer: ("image",),
        GuaranteeDocumentSerializer: ("file",),
        GuaranteeSerializer: (
            "document_scan",
            "expertise_report_scan",
            "lease_contract_scan",
            "legal_situation_certificate_scan",
            "registration_card_scan",
            "mechanical_expertise_scan",
            "technical_inspection_scan",
            "insurance_scan",
            "purchase_invoice_scan",
            "expertise_certificate_scan",
            "origin_certificate_scan",
            "pledge_deed_scan",
        ),
        GuaranteeFormalizationRequestSerializer: (
            "acte_file",
            "acte_signed_file",
            "registration_proof",
        ),
        SuretySerializer: (
            "id_document_scan",
            "photo",
            "ifu_scan",
            "rccm_scan",
            "manager_id_document_scan",
        ),
        SuretyDocumentSerializer: ("file",),
        ContractTemplateSerializer: ("file",),
        GeneratedContractSerializer: ("file", "signed_file"),
        DocumentSerializer: ("file",),
    }
    for cls, fields in expected.items():
        method = getattr(cls, "to_representation")
        code = method.__code__
        source = code.co_names
        assert "presign_file_fields" in source, (
            f"{cls.__name__}.to_representation n'appelle pas "
            "presign_file_fields"
        )
        consts = code.co_consts
        flat = []
        for item in consts:
            if isinstance(item, tuple):
                flat.extend(item)
            else:
                flat.append(item)
        for field in fields:
            assert field in flat, (
                f"{cls.__name__} ne présigne pas le champ {field!r}"
            )


_SERIALIZER_MODULES = (
    "apps.credits.serializers",
    "apps.guarantees.serializers",
    "apps.sureties.serializers",
    "apps.contracts.serializers",
    "apps.documents.serializers",
    "apps.clients.serializers",
    "apps.tenants.serializers",
    "apps.collections.serializers",
)


def test_model_serializers_override_representation_for_file_fields():
    """Aucun FileField/ImageField exposé sans to_representation dédié."""
    missing = []
    for mod_name in _SERIALIZER_MODULES:
        mod = importlib.import_module(mod_name)
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if not issubclass(cls, serializers.ModelSerializer):
                continue
            if cls is serializers.ModelSerializer:
                continue
            meta = getattr(cls, "Meta", None)
            if meta is None:
                continue
            model = getattr(meta, "model", None)
            declared = getattr(meta, "fields", None)
            if model is None or not declared or declared == "__all__":
                continue
            file_names = [
                f.name
                for f in model._meta.get_fields()
                if isinstance(f, (models.FileField, models.ImageField))
            ]
            extra = getattr(meta, "extra_kwargs", {})
            exposed = [
                n
                for n in file_names
                if n in declared and not extra.get(n, {}).get("write_only")
            ]
            if not exposed:
                continue
            if "to_representation" in cls.__dict__:
                continue
            missing.append(f"{cls.__name__}: {', '.join(exposed)}")
    assert not missing, (
        "FileFields exposés sans to_representation :\n" + "\n".join(missing)
    )
