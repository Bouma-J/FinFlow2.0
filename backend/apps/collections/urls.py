from rest_framework.routers import DefaultRouter

from .views import (
    CollectionActionViewSet,
    CollectionCaseViewSet,
    CollectionDialogueMessageViewSet,
    CollectionEscalationRuleViewSet,
    CollectionTrancheViewSet,
    LegalPartyViewSet,
    LitigationFileViewSet,
    LoanRestructureViewSet,
    PaymentPromiseViewSet,
    RepaymentViewSet,
    WriteOffViewSet,
)

router = DefaultRouter()
router.register("repayments", RepaymentViewSet, basename="repayment")
router.register("collection-cases", CollectionCaseViewSet, basename="collection-case")
router.register("collection-actions", CollectionActionViewSet, basename="collection-action")
router.register("payment-promises", PaymentPromiseViewSet, basename="payment-promise")
router.register(
    "collection-dialogue",
    CollectionDialogueMessageViewSet,
    basename="collection-dialogue",
)
router.register(
    "collection-escalation-rules",
    CollectionEscalationRuleViewSet,
    basename="collection-escalation-rule",
)
router.register(
    "collection-tranches",
    CollectionTrancheViewSet,
    basename="collection-tranche",
)
router.register("legal-parties", LegalPartyViewSet, basename="legal-party")
router.register("litigations", LitigationFileViewSet, basename="litigation")
router.register(
    "loan-restructures", LoanRestructureViewSet, basename="loan-restructure"
)
router.register("write-offs", WriteOffViewSet, basename="write-off")

urlpatterns = router.urls
