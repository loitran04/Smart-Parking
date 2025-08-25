from django.contrib import admin
from .models import User, Vehicle, QRCode, Gate, Tariff, ParkingSession, Payment, PlateReading
admin.site.register([User, Vehicle, QRCode, Gate, Tariff, ParkingSession, Payment, PlateReading])
