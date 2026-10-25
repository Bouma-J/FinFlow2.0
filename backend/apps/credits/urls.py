from rest_framework.routers import DefaultRouter

from .views import (
    AnalysisThresholdViewSet,
    CreditApplicationViewSet,
    CreditDocumentViewSet,
    CreditInstructionPolicyViewSet,
    FieldVisitViewSet,
    FinancialAnalysisViewSet,
    LoanViewSet,
)

router = DefaultRouter()
from .exposure_views import BorrowerGroupViewSet, CreditExposureObservationViewSet
router.register("borrower-groups", BorrowerGroupViewSet, basename="borrower-group")
router.register("credit-exposure-observations", CreditExposureObservationViewSet, basename="credit-exposure-observation")
router.register("credit-applications", CreditApplicationViewSet, basename="credit-application")
router.register("credit-documents", CreditDocumentViewSet, basename="credit-document")
router.register("financial-analyses", FinancialAnalysisViewSet, basename="financial-analysis")
router.register("analysis-thresholds", AnalysisThresholdViewSet, basename="analysis-threshold")
router.register(
    "credit-instruction-policy",
    CreditInstructionPolicyViewSet,
    basename="credit-instruction-policy",
)
router.register("field-visits", FieldVisitViewSet, basename="field-visit")
router.register("loans", LoanViewSet, basename="loan")

urlpatterns = router.urls
