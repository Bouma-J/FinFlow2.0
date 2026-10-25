from rest_framework.routers import DefaultRouter

from .views import (
    DelegationViewSet,
    GroupViewSet,
    PermissionViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", GroupViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("delegations", DelegationViewSet, basename="delegation")

urlpatterns = router.urls
