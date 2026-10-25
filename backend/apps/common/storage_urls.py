"""URLs présignées / accès fichiers (S3 ou local)."""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

CLIENT_FILE_TOKEN_SALT = "finflow.client-file"
CLIENT_FILE_TOKEN_MAX_AGE = 3600  # 1 h — aligné Cache-Control historique


def is_s3_storage() -> bool:
    return getattr(settings, "STORAGE_BACKEND", "local") == "s3"


def sign_client_file_token(client_id, field: str) -> str:
    """Jeton court pour <img>/<a> sans JWT (stockage local / proxy API)."""
    signer = TimestampSigner(salt=CLIENT_FILE_TOKEN_SALT)
    return signer.sign(f"{client_id}:{field}")


def verify_client_file_token(
    token: str | None,
    client_id,
    field: str,
    *,
    max_age: int = CLIENT_FILE_TOKEN_MAX_AGE,
) -> bool:
    if not token:
        return False
    signer = TimestampSigner(salt=CLIENT_FILE_TOKEN_SALT)
    try:
        value = signer.unsign(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return value == f"{client_id}:{field}"


def _public_s3_endpoint() -> str | None:
    """
    Endpoint MinIO/S3 joignable depuis le navigateur.

    Distinct de AWS_S3_ENDPOINT_URL (souvent http://minio:9000, réseau Docker).
    """
    custom = (getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None) or "").strip()
    if custom:
        if "://" in custom:
            return custom.rstrip("/")
        protocol = getattr(settings, "AWS_S3_URL_PROTOCOL", "http:")
        if not protocol.endswith(":"):
            protocol = f"{protocol}:"
        return f"{protocol}//{custom}".rstrip("/")
    return None


def _s3_client(*, endpoint_url: str | None = None):
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url
        or getattr(settings, "AWS_S3_ENDPOINT_URL", None)
        or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
        config=Config(
            signature_version="s3v4",
            s3={
                "addressing_style": getattr(
                    settings, "AWS_S3_ADDRESSING_STYLE", "path"
                )
            },
        ),
    )


def _rewrite_presigned_host(url: str, public_endpoint: str) -> str:
    """Remplace l'hôte Docker (minio:9000) par l'hôte public (localhost:9000)."""
    src = urlparse(url)
    dst = urlparse(
        public_endpoint
        if "://" in public_endpoint
        else f"http://{public_endpoint}"
    )
    return urlunparse(
        (
            dst.scheme or src.scheme or "http",
            dst.netloc or src.netloc,
            src.path,
            src.params,
            src.query,
            src.fragment,
        )
    )


def presigned_get_url(key: str, *, expires: int = 3600) -> str | None:
    """
    URL GET présignée utilisable par le navigateur.

    django-storages + AWS_S3_CUSTOM_DOMAIN produit souvent une URL *sans*
    bucket et *sans* signature → AccessDenied MinIO. On signe donc via boto3
    (path-style) puis on réécrit l'hôte vers le domaine public.
    """
    if not is_s3_storage() or not key:
        return None

    bucket = settings.AWS_STORAGE_BUCKET_NAME
    internal = getattr(settings, "AWS_S3_ENDPOINT_URL", None) or None
    public = _public_s3_endpoint()

    # Signer avec l'endpoint que le navigateur utilisera, sinon la signature
    # inclut Host=minio:9000 et échoue après rewrite.
    sign_endpoint = public or internal
    client = _s3_client(endpoint_url=sign_endpoint)
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
        HttpMethod="GET",
    )

    # Si on a signé en interne (pas de domaine public), tenter un rewrite.
    if public and internal and urlparse(url).netloc == urlparse(internal).netloc:
        url = _rewrite_presigned_host(url, public)
    return url


def file_download_url(file_field, *, expires: int = 3600) -> str | None:
    """URL de téléchargement (présignée navigateur si S3, sinon storage.url)."""
    if not file_field or not getattr(file_field, "name", None):
        return None
    if is_s3_storage():
        url = presigned_get_url(file_field.name, expires=expires)
        if url:
            return url
    storage = file_field.storage
    name = file_field.name
    try:
        return storage.url(name, expire=expires)
    except TypeError:
        return storage.url(name)


def presign_file_fields(data, instance, *fields, expires: int = 3600):
    """Remplace les URL django-storages (sans bucket) par des GET présignés."""
    for name in fields:
        field = getattr(instance, name, None)
        if field and getattr(field, "name", None):
            url = file_download_url(field, expires=expires)
            if url:
                data[name] = url
    return data


def tenant_logo_url(tenant, request=None) -> str | None:
    """
    URL publique du logo filiale, servie via l'API Django.

    Les logos restent proxifiés (petits, branding, cache navigateur simple).
    """
    if tenant is None or not getattr(tenant, "logo", None):
        return None
    if not tenant.logo.name:
        return None
    path = f"/api/v1/tenants/{tenant.pk}/logo/"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def client_photo_url(client, request=None) -> str | None:
    return client_file_url(client, "photo", request=request)


def client_file_url(client, field: str, request=None) -> str | None:
    """
    URL d'un fichier client.

    Préfère une URL MinIO présignée (navigateur → MinIO direct).
    Repli : proxy API Django si le présigné est indisponible (stockage local).
    """
    if client is None:
        return None
    file_field = getattr(client, field, None)
    if not file_field or not getattr(file_field, "name", None):
        return None

    if is_s3_storage():
        url = file_download_url(file_field, expires=3600)
        if url:
            return url

    # Repli local / échec présigné : proxy API avec jeton signé (pas d'AllowAny nu)
    token = sign_client_file_token(client.pk, field)
    path = f"/api/v1/clients/{client.pk}/files/{field}/?token={token}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


CLIENT_FILE_FIELDS = (
    "photo",
    "id_document_scan",
    "ifu_scan",
    "rccm_scan",
    "manager_id_document_scan",
)


def image_content_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    # SVG volontairement exclu (XSS stocké)
    return "application/octet-stream"


def generate_presigned_upload(
    *,
    key: str,
    content_type: str = "application/octet-stream",
    expires: int = 900,
) -> dict | None:
    """
    Génère une URL PUT présignée pour un upload direct vers S3/MinIO.
    Retourne None si le stockage n'est pas S3.
    """
    if not is_s3_storage():
        return None

    bucket = settings.AWS_STORAGE_BUCKET_NAME
    public = _public_s3_endpoint()
    internal = getattr(settings, "AWS_S3_ENDPOINT_URL", None) or None
    sign_endpoint = public or internal
    client = _s3_client(endpoint_url=sign_endpoint)
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
        HttpMethod="PUT",
    )
    if public and internal and urlparse(url).netloc == urlparse(internal).netloc:
        url = _rewrite_presigned_host(url, public)
    return {
        "upload_url": url,
        "key": key,
        "headers": {"Content-Type": content_type},
        "expires_in": expires,
    }
