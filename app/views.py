from difflib import SequenceMatcher
from datetime import datetime, timedelta
import secrets
from uuid import UUID

from django.contrib.auth import get_user_model
from decimal import Decimal

from django.utils import timezone
from rest_framework import permissions, status, viewsets, serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Count, Sum, Value, CharField, Q, DecimalField
from django.db.models.functions import Coalesce


from .models import Gate, QRCode, Vehicle, ParkingSession, Tariff, Reservation, Payment, PlateReading
from .serializers import (
    GateSerializer, QRCodeSerializer, VehicleSerializer,
    ParkingSessionSerializer, UserSerializer,
    ReservationSerializer, TariffSerializer
)
from rest_framework.permissions import IsAdminUser as IsAdmin
from .lpr import recognize_plate_from_bytes
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile


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
def _resolve_gate(request, expected_type: str):
    # Ưu tiên thứ tự: gate_id (UUID) -> gate_name -> gate_type (fallback)
    gid = request.data.get("gate_id") or request.data.get("gate_uuid")
    gname = request.data.get("gate_name") or request.data.get("gate")
    gtype = (request.data.get("gate_type") or expected_type)

    gate = None

    # 1) Thử bằng UUID
    if gid:
        try:
            gate = Gate.objects.get(pk=UUID(str(gid)))
        except Exception:
            gate = None

    # 2) Thử bằng tên (không phân biệt hoa thường, bỏ khoảng trắng hai đầu)
    if gate is None and gname:
        gate = Gate.objects.filter(name__iexact=str(gname).strip()).first()

    # 3) Fallback theo loại cổng
    if gate is None:
        gate = Gate.objects.filter(type=gtype).first()

    return gate
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
            "is_admin": user.is_staff, 
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
@permission_classes([IsAuthenticated])
def register_parking(request):

    user = request.user
    vt = request.data.get("vehicle_type")
    start_raw = request.data.get("start_time")
    duration = int(request.data.get("duration_minutes", 120))

    if vt not in ("car", "motorbike"):
        return Response({"detail": "vehicle_type phải là 'car' hoặc 'motorbike'."}, status=400)
    if not start_raw:
        return Response({"detail": "Thiếu start_time (ISO8601)."}, status=400)

    # parse start_time -> aware
    try:
        start = datetime.fromisoformat(start_raw)
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
    except Exception:
        return Response({"detail": "start_time không hợp lệ (ISO8601)."}, status=400)

    if start <= timezone.now():
        return Response({"detail": "start_time phải ở tương lai."}, status=400)

    end = start + timedelta(minutes=duration)

    # Giới hạn 5 đặt/ngày/người (bỏ qua cancelled/expired/completed)
    day = start.date()
    day_count = Reservation.objects.filter(
        user=user, start_time__date=day
    ).exclude(status__in=['cancelled', 'expired', 'completed']).count()
    if day_count >= MAX_RES_PER_DAY:
        return Response({"detail": "Vượt quá 5 đặt chỗ trong ngày."}, status=429)

    # Lấy tariff
    tariff = Tariff.objects.first()
    if not tariff:
        return Response({"detail": "Chưa cấu hình Tariff."}, status=400)

    est = _estimate_fee(tariff.pricing_rule or {}, duration, vt)

    # Tạo QR rỗng, TTL = end + NO_SHOW_GRACE_MIN
    qr = QRCode.objects.create(
        user=user,
        value=_gen_qr_value(),
        status="active",
        expired_at=end + timedelta(minutes=NO_SHOW_GRACE_MIN),
    )

    # Tạo Reservation & liên kết 1-1 với QR
    res = Reservation.objects.create(
        user=user,
        vehicle_type=vt,
        start_time=start,
        end_time=end,
        estimated_fee=est,
        status='booked',
    )
    qr.reservation = res
    qr.save(update_fields=['reservation'])

    # Có thể dùng serializer rồi thêm trường; ở đây build tay cho sát FE
    data = {
        "id": str(res.id),
        "vehicle_type": res.vehicle_type,
        "start_time": res.start_time.isoformat(),
        "end_time": res.end_time.isoformat(),
        "estimated_fee": res.estimated_fee or 0,
        "currency": tariff.currency,
        "qr_value": qr.value,
        "status": res.status,
    }
    return Response(data, status=201)

@api_view(["POST"])
@permission_classes([permissions.AllowAny])  # camera/thiết bị
def entry(request):

    # === 1) Lấy biển số từ ảnh nếu có ===
    plate_text = request.data.get("plate_text")
    upload = request.FILES.get("image")
    if upload and not plate_text:
        image_bytes = upload.read()
        lpr = recognize_plate_from_bytes(image_bytes)
        if not lpr["ok"]:
            return Response({"detail": "Không đọc được biển số từ ảnh"}, status=422)
        if lpr["ocr_conf"] < 0.60:   # ngưỡng tuỳ ý
            return Response({"detail": "Độ tin cậy thấp", "conf": lpr["ocr_conf"]}, status=422)
        plate_text = lpr["text"]

    # === 2) Giữ nguyên phần còn lại như bạn đã viết ===
    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active") \
                       .select_related("user", "reservation").first()
    if not qr:
        return Response({"detail": "QR không hợp lệ/không active"}, status=404)

    now = timezone.now()
    if qr.expired_at and qr.expired_at <= now:
        return Response({"detail": "QR đã hết hạn"}, status=410)

    res = qr.reservation
    if res:
        if now < res.start_time - timedelta(minutes=LEAD_MIN):
            return Response({"detail": "Đến quá sớm so với giờ đặt"}, status=409)
        if now > res.end_time + timedelta(minutes=NO_SHOW_GRACE_MIN):
            res.status = 'expired'; res.save(update_fields=['status'])
            qr.status = 'expired'; qr.save(update_fields=['status'])
            return Response({"detail": "Đặt chỗ hết hiệu lực"}, status=410)

    gate_name = request.data.get("gate_name") or request.data.get("gate")  # hỗ trợ nhiều key
    gate = None

    if gate_name:
        gate = Gate.objects.filter(name__iexact=gate_name.strip()).first()

    # fallback: nếu không gửi tên, lấy gate đầu tiên type='entry'
    if gate is None:
        gate = Gate.objects.filter(type="entry").first()

    if gate is None:
        return Response({"detail": "Không tìm thấy gate hợp lệ"}, status=404)

    # kiểm tra loại gate
    if gate.type != "entry":
        return Response({"detail": f"Gate '{gate.name}' không phải là ENTRY"}, status=400)

    if ParkingSession.objects.filter(user=qr.user, status="open").exists():
        return Response({"detail": "Người dùng đang có phiên OPEN"}, status=409)

    plate = _norm(plate_text or "")
    qr.last_plate = plate
    qr.save(update_fields=["last_plate"])

    vehicle = qr.user.vehicles.first() or Vehicle.objects.create(owner=qr.user, plate_number=plate or "UNKNOWN")
    if plate and vehicle.plate_number != plate:
        vehicle.plate_number = plate
        vehicle.save(update_fields=["plate_number"])

    tariff = Tariff.objects.first()
    if not tariff:
        return Response({"detail": "Chưa cấu hình Tariff"}, status=400)

    sess = ParkingSession.objects.create(
        user=qr.user, vehicle=vehicle, entry_gate=gate,
        entry_plate=plate or None, tariff=tariff, status="open",
        qrcode=qr, reservation=res if res else None,
    )
    # Lưu PlateReading
    PlateReading.objects.create(
        gate=gate,
        plate_text=plate,  # biển số vừa đọc
        confidence=lpr.get("ocr_conf", 1.0) if upload else 1.0,  # nếu từ ảnh thì lấy confidence
        session=sess
    )
    if res and res.status != 'active':
        res.status = 'active'; res.save(update_fields=['status'])

    # có thể trả thêm conf để debug
    return Response(ParkingSessionSerializer(sess).data, status=201)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])  # camera/thiết bị
def exit(request):
    # 1) Lấy biển số
    plate_text = request.data.get("plate_text")
    upload = request.FILES.get("image")
    if upload and not plate_text:
        image_bytes = upload.read()
        lpr = recognize_plate_from_bytes(image_bytes)
        if not lpr["ok"]:
            return Response({"detail": "Không đọc được biển số từ ảnh"}, status=422)
        if lpr["ocr_conf"] < 0.60:
            return Response({"detail": "Độ tin cậy thấp", "conf": lpr["ocr_conf"]}, status=422)
        plate_text = lpr["text"]

    # 2) Lấy QR code
    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active") \
        .select_related("user", "reservation").first()
    if not qr:
        return Response({"detail": "QR không hợp lệ/không active"}, status=404)

    # 3) Lấy gate theo tên
    gate_name = request.data.get("gate_name") or request.data.get("gate")
    gate = Gate.objects.filter(name__iexact=(gate_name or "").strip()).first()
    if not gate or gate.type != "exit":
        return Response({"detail": "Gate không hợp lệ hoặc không phải EXIT"}, status=400)

    # 4) Lấy session OPEN gần nhất
    sess = ParkingSession.objects.filter(user=qr.user, status="open").order_by("-entry_time").first()
    if not sess:
        return Response({"detail": "Không tìm thấy phiên OPEN"}, status=404)

    # 5) Kiểm tra biển số
    exit_plate = _norm(plate_text)
    score = _similar(exit_plate, getattr(qr, "last_plate", ""))
    if score < -0.80:
        return Response({"detail": "Biển số không khớp", "score": score}, status=409)

    # Lưu PlateReading tại cổng exit
    PlateReading.objects.create(
        gate=gate,
        plate_text=exit_plate,
        confidence=score,  # hoặc 1.0 nếu không từ OCR
        session=sess
    )
    # 6) Cập nhật session và tính phí
    now = timezone.now()
    sess.exit_gate = gate
    sess.exit_time = now
    sess.exit_plate = exit_plate

    duration = int((now - sess.entry_time).total_seconds() // 60)

    tariff = sess.tariff
    fee = _estimate_fee(tariff.pricing_rule or {}, duration, "car")  # hoặc vehicle_type thật
    sess.amount = fee
    sess.status = "closed"
    sess.save(update_fields=['exit_gate', 'exit_time', 'exit_plate', 'amount', 'status'])

    # 7) Trả dữ liệu
    return Response({
        "session_id": str(sess.id),
        "exit_plate": sess.exit_plate,
        "amount": sess.amount,
        "duration_minutes": duration
    }, status=200)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def change_info(request):

    if request.method == "GET":
        return Response(UserSerializer(request.user).data)

    ser = UserSerializer(request.user, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):

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

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_reservations(request):
    qs = Reservation.objects.filter(user=request.user).order_by('-start_time')
    return Response(ReservationSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reservation_detail(request, pk):
    try:
        r = Reservation.objects.get(pk=pk, user=request.user)
    except Reservation.DoesNotExist:
        return Response({"detail":"Not found"}, status=404)
    return Response(ReservationSerializer(r).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_summary(request):
    """
    Trả về tổng quan thống kê cho admin.
    """
    now = timezone.now()
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 1) Tổng số phiên gửi xe trong tháng
    total_sessions = ParkingSession.objects.filter(entry_time__gte=start_month).count()

    # 2) Tổng doanh thu tháng
    total_revenue = (
            ParkingSession.objects
            .filter(status='CLOSED', exit_time__gte=start_month, exit_time__lt=now)
            .aggregate(
                total=Coalesce(
                    Sum('amount'),
                    Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                )
            )['total'] or Decimal('0')
    )
    total_revenue = float(total_revenue)

    # 3) Số lượt đặt chỗ active / expired
    reservations = Reservation.objects.filter(start_time__gte=start_month)
    reserved_active = reservations.filter(status='active').count()
    reserved_expired = reservations.filter(status='expired').count()

    # 4) Phân loại xe (car / motorbike) trong tháng
    res_agg = Reservation.objects.filter(
        start_time__gte=start_month,
        # (tuỳ chọn) chỉ tính những trạng thái bạn muốn:
        # status__in=['booked', 'active', 'expired']
    ).aggregate(
        car=Count('id', filter=Q(vehicle_type='car')),
        motorbike=Count('id', filter=Q(vehicle_type='motorbike')),
    )

    vehicle_stats = [
        {"type": "car", "count": res_agg["car"] or 0},
        {"type": "motorbike", "count": res_agg["motorbike"] or 0},
    ]

    # 5) Lượt vào / ra mỗi cổng
    gate_entries = ParkingSession.objects.filter(entry_time__gte=start_month) \
        .values('entry_gate__name') \
        .annotate(count=Count('id'))
    gate_exits = ParkingSession.objects.filter(exit_time__gte=start_month) \
        .values('exit_gate__name') \
        .annotate(count=Count('id'))

    data = {
        "total_sessions": total_sessions,
        "total_revenue": total_revenue,
        "reservations": {
            "active": reserved_active,
            "expired": reserved_expired
        },
        "vehicle_stats": list(vehicle_stats),
        "gate_entries": list(gate_entries),
        "gate_exits": list(gate_exits),
    }
    return Response(data)
class TariffViewSet(viewsets.ModelViewSet):
    queryset = Tariff.objects.all().order_by('name')
    serializer_class = TariffSerializer

    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]
class GateViewSet(viewsets.ModelViewSet):
    queryset = Gate.objects.all().order_by('name')
    serializer_class = GateSerializer
    permission_classes = [IsAdmin]