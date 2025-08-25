# api/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

# Swagger configuration
schema_view = get_schema_view(
    openapi.Info(title="Smart-Parking API", default_version="v1"),
    public=True, permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Admin URL
    path("admin/", admin.site.urls),

    # Include app URLs
    path("", include("app.urls")),  # <-- Đảm bảo rằng app.urls được include đúng

    # Swagger and Redoc URLs
    re_path(r"^docs(?P<format>\.json|\.yaml)$", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    re_path(r"^swagger/$", schema_view.with_ui("swagger", cache_timeout=0), name="swagger-ui"),
    re_path(r"^redoc/$", schema_view.with_ui("redoc", cache_timeout=0), name="redoc"),
]
