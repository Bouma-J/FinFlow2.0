from rest_framework.routers import DefaultRouter

from .views import ConfigurationProfileViewSet

router = DefaultRouter()
router.register("configuration-profiles", ConfigurationProfileViewSet, basename="configuration-profile")
urlpatterns = router.urls
