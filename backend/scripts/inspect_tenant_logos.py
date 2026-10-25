import django
django.setup()

from django.conf import settings
from apps.tenants.models import Tenant

print("STORAGE_BACKEND", getattr(settings, "STORAGE_BACKEND", None))
print("MEDIA_URL", settings.MEDIA_URL)
print("AWS_S3_ENDPOINT_URL", getattr(settings, "AWS_S3_ENDPOINT_URL", None))
print("AWS_S3_CUSTOM_DOMAIN", getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None))
print("STORAGES", settings.STORAGES.get("default"))

for t in Tenant.objects.all():
    print("---", t.code, t.name)
    print("  has_logo", bool(t.logo))
    if t.logo:
        print("  name", t.logo.name)
        try:
            print("  url", t.logo.url)
        except Exception as e:
            print("  url_error", e)
