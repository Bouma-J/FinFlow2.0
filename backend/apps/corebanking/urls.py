from rest_framework.routers import DefaultRouter
from django.urls import path

from .callback_views import CreditDisbursementCallbackView
from .views import CoreBankingConnectorViewSet, IntegrationLogViewSet

router = DefaultRouter()
router.register("cbs-connectors", CoreBankingConnectorViewSet, basename="cbs-connector")
router.register("integration-logs", IntegrationLogViewSet, basename="integration-log")

urlpatterns = [
    path(
        "cbs/callbacks/crd/<uuid:application_id>/",
        CreditDisbursementCallbackView.as_view(),
        name="cbs-crd-callback",
    ),
    *router.urls,
]
