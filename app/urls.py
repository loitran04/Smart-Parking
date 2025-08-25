# app/urls.py
from django.urls import path, include
from .views import RegisterView, LoginView, LogoutView, register_parking, entry, exit, GateViewSet
from rest_framework.routers import DefaultRouter

# Tạo router cho GateViewSet
router = DefaultRouter()
router.register(r"gates", GateViewSet, basename="gates")

urlpatterns = [
    # Đăng ký, đăng nhập, đăng xuất
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),

    # Các API gửi xe và rời bến
    path("parking/register/", register_parking, name="register_parking"),
    path("parking/entry/", entry, name="entry"),
    path("parking/exit/", exit, name="exit"),

    # Các viewset CRUD của Gate
    path("", include(router.urls)),
]
