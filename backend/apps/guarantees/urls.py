from rest_framework.routers import DefaultRouter

from .views import (
    DationRequestViewSet,
    GuaranteeFormalizationRequestViewSet,
    GuaranteeMovementViewSet,
    GuaranteeReleaseRequestViewSet,
    GuaranteeViewSet,
)

router = DefaultRouter()
router.register("guarantees", GuaranteeViewSet, basename="guarantee")
router.register(
    "guarantee-movements", GuaranteeMovementViewSet, basename="guarantee-movement"
)
router.register(
    "guarantee-releases",
    GuaranteeReleaseRequestViewSet,
    basename="guarantee-release",
)
router.register("dation-requests", DationRequestViewSet, basename="dation-request")
router.register(
    "guarantee-formalizations",
    GuaranteeFormalizationRequestViewSet,
    basename="guarantee-formalization",
)

urlpatterns = router.urls
