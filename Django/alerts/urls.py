from rest_framework.routers import DefaultRouter

from alerts import views

app_name = "alerts"

router = DefaultRouter()
router.register("rules", views.AlertRuleViewSet, basename="rule")
router.register("events", views.AlertEventViewSet, basename="event")
router.register("notifications", views.AlertNotificationViewSet, basename="notification")

urlpatterns = router.urls
