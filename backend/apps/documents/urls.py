from rest_framework.routers import DefaultRouter

from .views import DocumentCategoryViewSet, DocumentViewSet

router = DefaultRouter()
router.register("document-categories", DocumentCategoryViewSet, basename="document-category")
router.register("documents", DocumentViewSet, basename="document")

urlpatterns = router.urls
