from django.urls import path, include
from .views import (RegisterView, LoginView, LogoutView, register_parking,
                    entry, exit, GateViewSet, MeView,
                    change_info, change_password, my_reservations,
                    reservation_detail, stats_summary, TariffViewSet,
                    my_payments)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"gates", GateViewSet, basename="gates")
router.register(r"tariffs", TariffViewSet, basename="tariff")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path('auth/me/', MeView.as_view()),
    path('auth/changeInfo/', change_info, name="change_info"),
    path('auth/changePassword/', change_password, name="change_password"),

    path("parking/register/", register_parking, name="register_parking"),
    path("parking/entry/", entry, name="entry"),
    path("parking/exit/", exit, name="exit"),

    path("parking/payments/", my_payments),
    path("parking/reservations/", my_reservations),
    path("parking/reservations/<uuid:pk>/", reservation_detail),
    path('parking/admin/stats/', stats_summary, name='stats_summary'),

    path("", include(router.urls)),
]
