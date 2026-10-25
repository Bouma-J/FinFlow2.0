from django.urls import path

from .views import (
    AfterSalesHubView,
    GroupBreakdownView,
    GroupConsolidationView,
    OperationalDashboardView,
)

urlpatterns = [
    path("reporting/dashboard/", OperationalDashboardView.as_view(), name="dashboard"),
    path(
        "reporting/after-sales-hub/",
        AfterSalesHubView.as_view(),
        name="after-sales-hub",
    ),
    path(
        "reporting/group-consolidation/",
        GroupConsolidationView.as_view(),
        name="group-consolidation",
    ),
    path(
        "reporting/group-breakdown/",
        GroupBreakdownView.as_view(),
        name="group-breakdown",
    ),
]
