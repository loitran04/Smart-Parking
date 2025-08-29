from difflib import SequenceMatcher
from datetime import datetime, timedelta
import secrets

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import permissions, status, viewsets, serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Gate, QRCode, Vehicle, ParkingSession, Tariff, Reservation
from .serializers import (
    GateSerializer, QRCodeSerializer, VehicleSerializer,
    ParkingSessionSerializer, UserSerializer, ReservationSerializer
)


User = get_user_model()

# ======== Constants cho rule ========
LEAD_MIN = 15               # cho vào sớm 15'
NO_SHOW_GRACE_MIN = 30      # quá giờ +30' mà chưa vào -> hết hiệu lực
MAX_RES_PER_DAY = 5         # tối đa 5 đặt chỗ/ngày/người

# ========= Helpers =========
def _norm(s): return (s or "").upper().replace(" ", "")
def _similar(a, b): return SequenceMatcher(None, _norm(a), _norm(b)).ratio()
def _gen_qr_value(): return secrets.token_urlsafe(18)

def _estimate_fee(rule: dict, duration_min: int, vehicle_type: str) -> int:
    free = int(rule.get('free_first_min', 0))
    block = int(rule.get('block_minutes', 60))
    per_by_type = rule.get('per_block_by_type') or {}
    per = int(per_by_type.get(vehicle_type, rule.get('per_block', 10000)))
    payable = max(0, duration_min - free)
    blocks = (payable + block - 1) // block
    return blocks * per

# ========= AUTH (Token) =========
class RegisterSerializer(serializers.ModelSerializer):
    """Đăng ký tài khoản, trả luôn token."""
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["id", "username", "password", "full_name", "phone", "email"]

    def create(self, validated_data):
        pwd = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(pwd)
        user.save()
        return user


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({**ser.data, "token": token.key}, status=status.HTTP_201_CREATED)


class LoginView(ObtainAuthToken):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user_id": user.id,
            "user": UserSerializer(user).data
        })

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
class LogoutView(APIView):
    """Xoá token hiện tại (đăng xuất)."""
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Logged out"}, status=status.HTTP_200_OK)


# ========= Gate CRUD =========
class GateViewSet(viewsets.ModelViewSet):
    """
    CRUD cho cổng (ENTRY/EXIT).
    """
    queryset = Gate.objects.all()
    serializer_class = GateSerializer
    permission_classes = [permissions.IsAuthenticated]


# ========= Parking Flow =========
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def register_parking(request):
    """
    Cấp QR RỖNG nhanh cho user (không qua đặt chỗ).
    TTL mặc định 24h (bạn có thể đổi).
    """
    user = request.user
    now = timezone.now()
    ttl = now + timedelta(hours=24)

    qr = QRCode.objects.create(
        user=user,
        value=_gen_qr_value(),
        status="active",
        expired_at=ttl
    )
    return Response(QRCodeSerializer(qr).data, status=201)

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_reservation(request):
    """
    Body: { "vehicle_type": "car"|"motorbike", "start_time": ISO, "duration_minutes": int }
    Trả: Reservation + qr_value (kèm ước tính phí).
    Giới hạn: tối đa 5 đặt/ngày/người (không tính cancelled/expired/completed).
    """
    user = request.user
    vt = request.data.get("vehicle_type")
    start_raw = request.data.get("start_time")
    duration = int(request.data.get("duration_minutes", 60))

    if not vt or not start_raw:
        return Response({"detail": "Thiếu vehicle_type hoặc start_time"}, status=400)

    try:
        # start_time ISO -> aware
        start = datetime.fromisoformat(start_raw)
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
    except Exception:
        return Response({"detail": "start_time không hợp lệ (ISO8601)"}, status=400)

    if start <= timezone.now():
        return Response({"detail": "start_time phải ở tương lai"}, status=400)

    end = start + timedelta(minutes=duration)

    # Giới hạn 5 đặt/ngày
    day = start.date()
    day_count = Reservation.objects.filter(
        user=user, start_time__date=day
    ).exclude(status__in=['cancelled','expired','completed']).count()
    if day_count >= MAX_RES_PER_DAY:
        return Response({"detail": "Vượt quá 5 đặt chỗ trong ngày"}, status=429)

    tariff = Tariff.objects.first()
    if not tariff:
        return Response({"detail": "Chưa cấu hình Tariff"}, status=400)

    est = _estimate_fee(tariff.pricing_rule or {}, duration, vt)

    # Cấp QR gắn với reservation, TTL = end + NO_SHOW_GRACE_MIN
    qr = QRCode.objects.create(
        user=user,
        value=_gen_qr_value(),
        status="active",
        expired_at=end + timedelta(minutes=NO_SHOW_GRACE_MIN)
    )
    res = Reservation.objects.create(
        user=user, vehicle_type=vt, start_time=start, end_time=end,
        estimated_fee=est, status='booked'
    )
    # liên kết 1-1
    qr.reservation = res
    qr.save(update_fields=['reservation'])

    data = ReservationSerializer(res).data
    data["qr_value"] = qr.value
    data["currency"] = tariff.currency
    return Response(data, status=201)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])  # camera/thiết bị
def entry(request):
    """
    Body: { qr, gate_id, plate_text }
    - Xác thực QR active + TTL.
    - Nếu QR gắn reservation: kiểm tra khoảng thời gian hợp lệ (lead/grace).
    - Khóa plate vào QR.last_plate.
    - Chặn nhiều phiên OPEN cho cùng user.
    - Tạo ParkingSession (link qrcode/reservation).
    """
    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active") \
                       .select_related("user", "reservation").first()
    if not qr:
        return Response({"detail": "QR không hợp lệ/không active"}, status=404)

    now = timezone.now()
    if qr.expired_at and qr.expired_at <= now:
        return Response({"detail": "QR đã hết hạn"}, status=410)

    # Reservation timing (nếu có)
    res = qr.reservation
    if res:
        if now < res.start_time - timedelta(minutes=LEAD_MIN):
            return Response({"detail": "Đến quá sớm so với giờ đặt"}, status=409)
        if now > res.end_time + timedelta(minutes=NO_SHOW_GRACE_MIN):
            res.status = 'expired'; res.save(update_fields=['status'])
            qr.status = 'expired'; qr.save(update_fields=['status'])
            return Response({"detail": "Đặt chỗ hết hiệu lực"}, status=410)

    # Gate
    try:
        gate = Gate.objects.get(pk=request.data.get("gate_id"))
        if gate.type != "entry":
            return Response({"detail": "gate_id phải là ENTRY"}, status=400)
    except Gate.DoesNotExist:
        return Response({"detail": "gate_id không tồn tại"}, status=404)

    # Chặn OPEN trùng
    if ParkingSession.objects.filter(user=qr.user, status="open").exists():
        return Response({"detail": "Người dùng đang có phiên OPEN"}, status=409)

    # Khóa plate
    plate = _norm(request.data.get("plate_text"))
    qr.last_plate = plate
    qr.save(update_fields=["last_plate"])

    # Vehicle (tuỳ chọn cập nhật)
    vehicle = qr.user.vehicles.first()
    if not vehicle:
        vehicle = Vehicle.objects.create(owner=qr.user, plate_number=plate or "UNKNOWN")
    elif plate:
        vehicle.plate_number = plate
        vehicle.save(update_fields=["plate_number"])

    tariff = Tariff.objects.first()
    if not tariff:
        return Response({"detail": "Chưa cấu hình Tariff"}, status=400)

    sess = ParkingSession.objects.create(
        user=qr.user,
        vehicle=vehicle,
        entry_gate=gate,
        entry_plate=plate or None,
        tariff=tariff,
        status="open",
        qrcode=qr,
        reservation=res if res else None,
    )
    if res and res.status != 'active':
        res.status = 'active'
        res.save(update_fields=['status'])

    return Response(ParkingSessionSerializer(sess).data, status=201)

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def change_info(request):
    """
    GET  /auth/changeInfo/  -> trả hồ sơ hiện tại
    PATCH /auth/changeInfo/ -> cập nhật một phần (full_name, phone, email, ...)
    """
    if request.method == "GET":
        return Response(UserSerializer(request.user).data)

    ser = UserSerializer(request.user, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    POST /auth/changePassword/
    Body: { "old_password": "...", "new_password": "..." }
    """
    old = request.data.get("old_password")
    new = request.data.get("new_password")

    if not old or not new:
        return Response({"detail": "Thiếu old_password/new_password"}, status=400)
    if not request.user.check_password(old):
        return Response({"detail": "Mật khẩu cũ không đúng"}, status=400)
    if len(new) < 6:
        return Response({"detail": "Mật khẩu mới tối thiểu 6 ký tự"}, status=400)

    request.user.set_password(new)
    request.user.save()
    # (Tuỳ chọn) đăng xuất tất cả thiết bị hiện tại:
    Token.objects.filter(user=request.user).delete()
    return Response({"detail": "Đổi mật khẩu thành công, vui lòng đăng nhập lại"}, status=200)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])  # camera/thiết bị
def exit(request):
    """
    Body: { qr, gate_id, plate_text }
    - Tìm session OPEN theo user của QR.
    - So khớp plate với QR.last_plate (>=0.80).
    - Tính phí thực tế; nếu có reservation và quá end_time + grace -> phụ phí (overstay).
    - Đóng phiên, (tuỳ chọn) vô hiệu QR.
    """
    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active") \
                       .select_related("user", "reservation").first()
    if not qr:
        return Response({"detail": "QR không hợp lệ/không active"}, status=404)

    try:
        gate = Gate.objects.get(pk=request.data.get("gate_id"))
        if gate.type != "exit":
            return Response({"detail": "gate_id phải là EXIT"}, status=400)
    except Gate.DoesNotExist:
        return Response({"detail": "gate_id không tồn tại"}, status=404)

    sess = ParkingSession.objects.filter(user=qr.user, status="open").order_by("-entry_time").first()
    if not sess:
        return Response({"detail": "Không tìm thấy phiên OPEN"}, status=404)

    exit_plate = _norm(request.data.get("plate_text"))
    score = _similar(exit_plate, getattr(qr, "last_plate", ""))
    if score < 0.80:
        return Response({"detail": "Biển số không khớp", "score": score}, status=409)

    # Tính phí
    now = timezone.now()
    rule = sess.tariff.pricing_rule or {}
    minutes = int((now - sess.entry_time).total_seconds() // 60)
    fee = _estimate_fee(rule, minutes, getattr(qr.reservation, 'vehicle_type', 'car'))

    # Overstay nếu có reservation
    res = qr.reservation
    over_grace = int(rule.get('overstay_grace_min', 10))
    over_factor = float(rule.get('overstay_factor', 0.5))  # 50% phí phần vượt (ví dụ)
    if res:
        deadline = res.end_time + timedelta(minutes=over_grace)
        if now > deadline:
            over_min = int((now - deadline).total_seconds() // 60)
            over_fee = int(_estimate_fee(rule, over_min, res.vehicle_type) * over_factor)
            fee += max(0, over_fee)
            res.status = 'overstayed'
        else:
            res.status = 'completed'
        res.save(update_fields=['status'])

    # Đóng phiên
    sess.exit_gate = gate
    sess.exit_time = now
    sess.exit_plate = exit_plate or None
    sess.amount = fee
    sess.status = "closed"
    sess.save()

    # (tuỳ chọn) vô hiệu QR ngay sau phiên
    qr.status = "expired"
    qr.save(update_fields=["status"])

    return Response({"session_id": str(sess.id), "amount": fee, "minutes": minutes}, status=200)
