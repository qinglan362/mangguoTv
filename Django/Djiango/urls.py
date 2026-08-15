"""Djiango 项目根路由。"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("Djiango.api_urls")),
]
