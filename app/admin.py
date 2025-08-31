# app/admin.py
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import (
    User, Reservation, QRCode, Gate, Tariff,
    ParkingSession, Payment, PlateReading, Vehicle
)

# --- User ---
try:
    admin.site.unregister(User)
except NotRegistered:
    pass

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Extra', {'fields': ('full_name', 'phone')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (None, {'classes': ('wide',), 'fields': ('full_name', 'phone')}),
    )
    list_display  = ('username', 'full_name', 'email', 'phone', 'is_staff')
    search_fields = ('username', 'full_name', 'email', 'phone')  # <-- bắt buộc

# --- Reservation ---
@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'vehicle_type', 'start_time', 'end_time', 'estimated_fee', 'status')
    list_filter   = ('status', 'vehicle_type')
    search_fields = ('id', 'user__username', 'user__full_name', 'user__email')  # <-- bắt buộc
    autocomplete_fields = ('user',)
    ordering = ('-start_time',)

# --- QRCode ---
@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display  = ('value', 'user', 'status', 'expired_at', 'reservation', 'last_plate')
    list_filter   = ('status',)
    search_fields = ('value', 'user__username', 'reservation__id', 'last_plate')  # <-- bắt buộc
    autocomplete_fields = ('user', 'reservation')

@admin.register(Gate)
class GateAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'location')
    list_filter  = ('type',)
    search_fields = ('name', 'location')

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency')
    search_fields = ('name',)

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('plate_number', 'owner')
    search_fields = ('plate_number', 'owner__username')
    autocomplete_fields = ('owner',)

@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'vehicle', 'entry_gate', 'exit_gate', 'entry_time', 'exit_time', 'status', 'amount')
    list_filter  = ('status',)
    search_fields = ('id', 'user__username', 'vehicle__plate_number')
    autocomplete_fields = ('user', 'vehicle', 'entry_gate', 'exit_gate', 'tariff')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('session', 'provider', 'amount', 'currency', 'paid_at', 'status')
    list_filter  = ('status', 'provider')
    search_fields = ('session__id', 'tx_ref')

@admin.register(PlateReading)
class PlateReadingAdmin(admin.ModelAdmin):
    list_display = ('plate_text', 'confidence', 'gate', 'captured_at', 'session')
    list_filter  = ('gate',)
    search_fields = ('plate_text', 'session__id')
    autocomplete_fields = ('gate', 'session')
