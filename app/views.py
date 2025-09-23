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
    ReservationSerializer, TariffSerializer, PaymentSerializer
)
from rest_framework.permissions import IsAdminUser as IsAdmin
from .lpr import recognize_plate_from_bytes
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile


User = get_user_model()

LEAD_MIN = 15
NO_SHOW_GRACE_MIN = 30
MAX_RES_PER_DAY = 5

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
    gid = request.data.get("gate_id") or request.data.get("gate_uuid")
    gname = request.data.get("gate_name") or request.data.get("gate")
    gtype = (request.data.get("gate_type") or expected_type)

    gate = None

    if gid:
        try:
            gate = Gate.objects.get(pk=UUID(str(gid)))
        except Exception:
            gate = None

    if gate is None and gname:
        gate = Gate.objects.filter(name__iexact=str(gname).strip()).first()

    if gate is None:
        gate = Gate.objects.filter(type=gtype).first()

    return gate
class RegisterSerializer(serializers.ModelSerializer):
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
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Logged out"}, status=status.HTTP_200_OK)


class GateViewSet(viewsets.ModelViewSet):

    queryset = Gate.objects.all()
    serializer_class = GateSerializer
    permission_classes = [permissions.IsAuthenticated]


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

    try:
        start = datetime.fromisoformat(start_raw)
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
    except Exception:
        return Response({"detail": "start_time không hợp lệ (ISO8601)."}, status=400)

    if start <= timezone.now():
        return Response({"detail": "start_time phải ở tương lai."}, status=400)

    end = start + timedelta(minutes=duration)

    day = start.date()
    day_count = Reservation.objects.filter(
        user=user, start_time__date=day
    ).exclude(status__in=['cancelled', 'expired', 'completed']).count()
    if day_count >= MAX_RES_PER_DAY:
        return Response({"detail": "Vượt quá 5 đặt chỗ trong ngày."}, status=429)

    tariff = Tariff.objects.first()
    if not tariff:
        return Response({"detail": "Chưa cấu hình Tariff."}, status=400)

    est = _estimate_fee(tariff.pricing_rule or {}, duration, vt)

    qr = QRCode.objects.create(
        user=user,
        value=_gen_qr_value(),
        status="active",
        expired_at=end + timedelta(minutes=NO_SHOW_GRACE_MIN),
    )

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
@permission_classes([permissions.AllowAny])
def entry(request):

    plate_text = request.data.get("plate_text")
    upload = request.FILES.get("image")
    if upload and not plate_text:
        image_bytes = upload.read()
        lpr = recognize_plate_from_bytes(image_bytes)
        if not lpr["ok"]:
            return Response({"detail": "Không đọc được biển số từ ảnh"}, status=422)
        plate_text = lpr["text"]

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

    gate_name = request.data.get("gate_name") or request.data.get("gate")
    gate = None

    if gate_name:
        gate = Gate.objects.filter(name__iexact=gate_name.strip()).first()

    if gate is None:
        gate = Gate.objects.filter(type="entry").first()

    if gate is None:
        return Response({"detail": "Không tìm thấy gate hợp lệ"}, status=404)

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
    PlateReading.objects.create(
        gate=gate,
        plate_text=plate,
        confidence=lpr.get("ocr_conf", 1.0) if upload else 1.0,
        session=sess
    )
    if res and res.status != 'active':
        res.status = 'active'; res.save(update_fields=['status'])

    return Response(ParkingSessionSerializer(sess).data, status=201)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def exit(request):
    plate_text = request.data.get("plate_text")
    upload = request.FILES.get("image")
    if upload and not plate_text:
        image_bytes = upload.read()
        lpr = recognize_plate_from_bytes(image_bytes)
        if not lpr["ok"]:
            return Response({"detail": "Không đọc được biển số từ ảnh"}, status=422)

        plate_text = lpr["text"]

    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active") \
        .select_related("user", "reservation").first()
    if not qr:
        return Response({"detail": "QR không hợp lệ/không active"}, status=404)

    gate_name = request.data.get("gate_name") or request.data.get("gate")
    gate = Gate.objects.filter(name__iexact=(gate_name or "").strip()).first()
    if not gate or gate.type != "exit":
        return Response({"detail": "Gate không hợp lệ hoặc không phải EXIT"}, status=400)

    sess = ParkingSession.objects.filter(user=qr.user, status="open").order_by("-entry_time").first()
    if not sess:
        return Response({"detail": "Không tìm thấy phiên OPEN"}, status=404)

    exit_plate = _norm(plate_text)
    score = _similar(exit_plate, getattr(qr, "last_plate", ""))
    if score < -0.80:
        return Response({"detail": "Biển số không khớp", "score": score}, status=409)

    PlateReading.objects.create(
        gate=gate,
        plate_text=exit_plate,
        confidence=score,
        session=sess
    )
    now = timezone.now()
    sess.exit_gate = gate
    sess.exit_time = now
    sess.exit_plate = exit_plate

    duration = int((now - sess.entry_time).total_seconds() // 60)

    tariff = sess.tariff
    fee = _estimate_fee(tariff.pricing_rule or {}, duration, "car")
    sess.amount = fee
    sess.status = "closed"
    sess.save(update_fields=['exit_gate', 'exit_time', 'exit_plate', 'amount', 'status'])

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
    now = timezone.now()
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_sessions = ParkingSession.objects.filter(entry_time__gte=start_month).count()

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

    reservations = Reservation.objects.filter(start_time__gte=start_month)
    reserved_active = reservations.filter(status='active').count()
    reserved_expired = reservations.filter(status='expired').count()

    res_agg = Reservation.objects.filter(
        start_time__gte=start_month,
    ).aggregate(
        car=Count('id', filter=Q(vehicle_type='car')),
        motorbike=Count('id', filter=Q(vehicle_type='motorbike')),
    )

    vehicle_stats = [
        {"type": "car", "count": res_agg["car"] or 0},
        {"type": "motorbike", "count": res_agg["motorbike"] or 0},
    ]

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
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_payments(request):
    qs = Payment.objects.filter(session__user=request.user) \
                        .select_related('session') \
                        .order_by('-paid_at', '-session__exit_time', '-session__entry_time')

    status_param = request.query_params.get('status')
    if status_param:
        qs = qs.filter(status=status_param)

    return Response(PaymentSerializer(qs, many=True).data)