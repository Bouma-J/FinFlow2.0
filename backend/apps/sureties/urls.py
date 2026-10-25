from rest_framework.routers import DefaultRouter

from .views import SuretyEngagementViewSet, SuretyViewSet

router = DefaultRouter()
router.register("sureties", SuretyViewSet, basename="surety")
router.register("surety-engagements", SuretyEngagementViewSet, basename="surety-engagement")

urlpatterns = router.urls
