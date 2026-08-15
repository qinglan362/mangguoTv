from rest_framework.routers import DefaultRouter

from reports import views

app_name = "reports"

router = DefaultRouter()
router.register("exports", views.DataExportViewSet, basename="export")
router.register("reports", views.ReportViewSet, basename="report")

urlpatterns = router.urls
