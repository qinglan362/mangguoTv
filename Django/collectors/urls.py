from django.urls import path

from collectors.views import collector_list, collector_test

app_name = "collectors"

urlpatterns = [
    path("", collector_list, name="list"),
    path("<str:platform>/test/", collector_test, name="test"),
]
