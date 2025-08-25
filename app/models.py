import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

STATUS_CHOICES = [
    ('active','ACTIVE'),
    ('revoked','REVOKED'),
    ('expired','EXPIRED')
]
TYPES = [
    ('entry','ENTRY'),
    ('exit','EXIT')
]
STATUS = [
    ('open','OPEN'),
    ('closed','CLOSED')
]
STATUS_PAY = [
    ('pending','PENDING'),
    ('paid','PAID'),
    ('failed','FAILED'),
    ('refunded','REFUNDED')
]

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,editable=False)
    full_name=models.CharField(max_length=120)
    phone = models.CharField(max_length=10,blank=True, null=True)

    def __str__(self):
        return self.username
class Vehicle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vehicles")
    plate_number=models.CharField(max_length=15,db_index=True,default="")

    def __str__(self):
        return self.plate_number

class QRCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE,related_name="qr")
    value = models.CharField(max_length=128,unique=True,db_index=True)
    status = models.CharField(max_length=20,choices=STATUS_CHOICES, default="active")
    issued_at = models.DateTimeField(auto_now_add=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    last_plate = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    def __str__(self):
        return f"{self.user.username} - {self.value}"

class Gate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,editable=False)
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=15,choices=TYPES)
    location = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"{self.name} ({self.type})"

class Tariff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)
    pricing_rule = models.JSONField(default=dict)
    currency = models.CharField(max_length=8, default="VND")

    def __str__(self):
        return self.name

class ParkingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT,related_name="sessions")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT,related_name="sessions")
    entry_gate = models.ForeignKey(Gate, on_delete=models.PROTECT, related_name="entries")
    exit_gate = models.ForeignKey(Gate, on_delete=models.PROTECT, related_name="exits", null=True, blank=True)
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    entry_plate = models.CharField(max_length=20, null=True, blank=True)
    exit_plate = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=10,db_index=True, choices=STATUS, default="open")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.user} - {self.vehicle} - {self.status}"

class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(ParkingSession, on_delete=models.CASCADE, related_name="payment")
    provider = models.CharField(max_length=20)  # VNPAY/MOMO/STRIPE/CASH
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="VND")
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15,choices=STATUS_PAY, default="pending")
    tx_ref = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.provider} - {self.amount} {self.currency} ({self.status})"

class PlateReading(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gate = models.ForeignKey(Gate, on_delete=models.SET_NULL, null=True)
    image_path = models.CharField(max_length=255, blank=True)
    plate_text = models.CharField(max_length=20)
    confidence = models.FloatField(default=0.0)
    captured_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(ParkingSession, on_delete=models.SET_NULL,null=True)

    def __str__(self):
        return f"{self.plate_text} ({self.confidence})"