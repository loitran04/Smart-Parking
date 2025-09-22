# app/urls.py
from django.urls import path, include
from .views import (RegisterView, LoginView, LogoutView, register_parking,
                    entry, exit, GateViewSet, MeView,
                    change_info, change_password, my_reservations,
                    reservation_detail, stats_summary, TariffViewSet)
from rest_framework.routers import DefaultRouter

# Tạo router cho GateViewSet
router = DefaultRouter()
router.register(r"gates", GateViewSet, basename="gates")
router.register(r"tariffs", TariffViewSet, basename="tariff")

urlpatterns = [
    # Đăng ký, đăng nhập, đăng xuất
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path('auth/me/', MeView.as_view()),
    path('auth/changeInfo/', change_info, name="change_info"),
    path('auth/changePassword/', change_password, name="change_password"),

    # Các API gửi xe và rời bến
    path("parking/register/", register_parking, name="register_parking"),
    path("parking/entry/", entry, name="entry"),
    path("parking/exit/", exit, name="exit"),

    path("parking/reservations/", my_reservations),
    path("parking/reservations/<uuid:pk>/", reservation_detail),
    path('parking/admin/stats/', stats_summary, name='stats_summary'),

    # Các viewset CRUD của Gate
    path("", include(router.urls)),
]
