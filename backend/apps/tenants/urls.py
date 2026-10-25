from rest_framework.routers import DefaultRouter

from .views import AgencyViewSet, TenantViewSet

router = DefaultRouter()
router.register("tenants", TenantViewSet, basename="tenant")
router.register("agencies", AgencyViewSet, basename="agency")

urlpatterns = router.urls
