import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

# ===== Choices =====
STATUS_QR = [
    ('active',  'ACTIVE'),
    ('revoked', 'REVOKED'),
    ('expired', 'EXPIRED'),
]
GATE_TYPES = [
    ('entry', 'ENTRY'),
    ('exit',  'EXIT'),
]
SESSION_STATUS = [
    ('open',   'OPEN'),
    ('closed', 'CLOSED'),
]
PAY_STATUS = [
    ('pending',  'PENDING'),
    ('paid',     'PAID'),
    ('failed',   'FAILED'),
    ('refunded', 'REFUNDED'),
]
RES_STATUS = [
    ('booked',     'BOOKED'),     # đặt chỗ đã tạo, chưa vào
    ('active',     'ACTIVE'),     # đã vào bãi (đang sử dụng)
    ('completed',  'COMPLETED'),  # rời bãi xong
    ('cancelled',  'CANCELLED'),  # hủy bởi user/hệ thống
    ('expired',    'EXPIRED'),    # quá giờ mà chưa vào (no-show)
    ('overstayed', 'OVERSTAYED'), # rời bãi nhưng vượt quá end_time (để thống kê)
]
VEHICLE_TYPES = [
    ('car',       'CAR'),
    ('motorbike', 'MOTORBIKE'),
]

# ===== User =====
class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.username

# ===== Vehicle (biển số unique theo chủ) =====
class Vehicle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vehicles")
    plate_number = models.CharField(max_length=15, db_index=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'plate_number'], name='uq_owner_plate'),
        ]

    def __str__(self):
        return self.plate_number

# ===== Tariff =====
class Tariff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)
    pricing_rule = models.JSONField(default=dict)
    currency = models.CharField(max_length=8, default="VND")

    def __str__(self):
        return self.name

# ===== Reservation (đặt chỗ) =====
class Reservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    vehicle_type = models.CharField(max_length=16, choices=VEHICLE_TYPES)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    estimated_fee = models.IntegerField(default=0)  # ước tính theo tariff tại thời điểm đặt
    status = models.CharField(max_length=12, choices=RES_STATUS, default='booked')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'start_time']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.user} {self.vehicle_type} {self.start_time:%Y-%m-%d %H:%M}"

# ===== QRCode (nhiều QR / user; gắn 1-1 với Reservation) =====
class QRCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="qrcodes")
    # mỗi đặt chỗ 1 QR; nullable để vẫn hỗ trợ “QR rỗng không qua đặt chỗ”
    reservation = models.OneToOneField(
        Reservation, on_delete=models.SET_NULL, null=True, blank=True, related_name='qr'
    )
    value = models.CharField(max_length=128, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_QR, default="active")
    issued_at = models.DateTimeField(auto_now_add=True)
    expired_at = models.DateTimeField(null=True, blank=True)  # TTL hoặc end_time(+grace)
    last_plate = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'expired_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.value}"

# ===== Gate =====
class Gate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=15, choices=GATE_TYPES)
    location = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"{self.name} ({self.type})"

# ===== ParkingSession =====
class ParkingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sessions")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="sessions")
    entry_gate = models.ForeignKey(Gate, on_delete=models.PROTECT, related_name="entries")
    exit_gate = models.ForeignKey(Gate, on_delete=models.PROTECT, related_name="exits", null=True, blank=True)
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    entry_plate = models.CharField(max_length=20, null=True, blank=True)
    exit_plate = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=10, db_index=True, choices=SESSION_STATUS, default="open")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT)

    # liên kết để truy vết
    qrcode = models.ForeignKey(QRCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['entry_time']),
        ]

    def __str__(self):
        return f"{self.user} - {self.vehicle} - {self.status}"

# ===== Payment =====
class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(ParkingSession, on_delete=models.CASCADE, related_name="payment")
    provider = models.CharField(max_length=20)  # VNPAY/MOMO/STRIPE/CASH
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="VND")
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=PAY_STATUS, default="pending")
    tx_ref = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.provider} - {self.amount} {self.currency} ({self.status})"

# ===== PlateReading =====
class PlateReading(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gate = models.ForeignKey(Gate, on_delete=models.SET_NULL, null=True)
    image_path = models.CharField(max_length=255, blank=True)
    plate_text = models.CharField(max_length=20)
    confidence = models.FloatField(default=0.0)
    captured_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(ParkingSession, on_delete=models.SET_NULL, null=True, related_name='readings')

    def __str__(self):
        return f"{self.plate_text} ({self.confidence})"
