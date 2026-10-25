from rest_framework.routers import DefaultRouter

from .views import (
    CbsProductReferenceViewSet,
    CbsManagerViewSet,
    CbsProfessionViewSet,
    ChecklistItemViewSet,
    CreditProductViewSet,
    CurrencyViewSet,
    DecisionMotifViewSet,
    FinancingObjectViewSet,
    FinancingSourceViewSet,
    LoanPeriodicityViewSet,
    ProductCategoryViewSet,
    RejectReasonViewSet,
    RepaymentMethodViewSet,
    ServicePointViewSet,
)

router = DefaultRouter()
router.register("cbs-product-references", CbsProductReferenceViewSet, basename="cbs-product-reference")
router.register("product-categories", ProductCategoryViewSet, basename="product-category")
router.register("credit-products", CreditProductViewSet, basename="credit-product")
router.register("reject-reasons", RejectReasonViewSet, basename="reject-reason")
router.register("loan-periodicities", LoanPeriodicityViewSet, basename="loan-periodicity")
router.register("repayment-methods", RepaymentMethodViewSet, basename="repayment-method")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("financing-objects", FinancingObjectViewSet, basename="financing-object")
router.register("service-points", ServicePointViewSet, basename="service-point")
router.register("cbs-managers", CbsManagerViewSet, basename="cbs-manager")
router.register("financing-sources", FinancingSourceViewSet, basename="financing-source")
router.register("decision-motifs", DecisionMotifViewSet, basename="decision-motif")
router.register("cbs-professions", CbsProfessionViewSet, basename="cbs-profession")
router.register("checklist-items", ChecklistItemViewSet, basename="checklist-item")

urlpatterns = router.urls
