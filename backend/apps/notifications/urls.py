from rest_framework.routers import DefaultRouter

from .views import NotificationLogViewSet, TenantNotificationSettingsViewSet

router = DefaultRouter()
router.register(
    "notification-settings",
    TenantNotificationSettingsViewSet,
    basename="notification-settings",
)
router.register(
    "notification-logs",
    NotificationLogViewSet,
    basename="notification-log",
)

urlpatterns = router.urls
