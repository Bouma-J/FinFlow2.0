import django
django.setup()
from django.conf import settings
from django.test import RequestFactory
from apps.tenants.models import Tenant
from apps.tenants.serializers import TenantSerializer

print("QUERYSTRING_AUTH", getattr(settings, "AWS_QUERYSTRING_AUTH", None))
t = Tenant.objects.filter(logo__isnull=False).exclude(logo="").first()
assert t
raw = t.logo.url
rf = RequestFactory()
req = rf.get("/", HTTP_HOST="localhost")
ser = TenantSerializer(t, context={"request": req})
print("raw_url", raw)
print("serialized", ser.data.get("logo_url"))
