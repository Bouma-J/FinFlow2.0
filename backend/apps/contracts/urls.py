from rest_framework.routers import DefaultRouter

from .views import ContractTemplateViewSet, GeneratedContractViewSet

router = DefaultRouter()
router.register("contract-templates", ContractTemplateViewSet, basename="contract-template")
router.register("generated-contracts", GeneratedContractViewSet, basename="generated-contract")

urlpatterns = router.urls
