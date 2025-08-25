# app/views.py
from difflib import SequenceMatcher

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import permissions, status, viewsets, serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Gate, QRCode, Vehicle, ParkingSession, Tariff
from .serializers import (
    GateSerializer, QRCodeSerializer, VehicleSerializer, ParkingSessionSerializer
)

User = get_user_model()

# ========= Helpers =========
def _norm(s): return (s or "").upper().replace(" ", "")
def _similar(a, b): return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


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


from rest_framework.views import APIView
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """
        Đăng ký tài khoản.
        ---
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  username: {type: string}
                  password: {type: string}
                  full_name: {type: string}
                  phone: {type: string}
                  email: {type: string}
        """
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({**ser.data, "token": token.key}, status=status.HTTP_201_CREATED)


class LoginView(ObtainAuthToken):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        """
        Đăng nhập, trả về token.
        ---
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  username: {type: string}
                  password: {type: string}
        """
        resp = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=resp.data["token"])
        return Response({"token": token.key, "user_id": token.user_id})


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
    Cấp/refresh mã QR cho user hiện tại.
    Trả về QR đang active (tạo mới nếu chưa có).
    """
    user = request.user
    qr = getattr(user, "qr", None)
    if not qr:
        qr = QRCode.objects.create(user=user, value=f"QR-{user.id}", status="active")
    elif qr.status != "active":
        qr.status = "active"
        qr.save(update_fields=["status"])
    return Response(QRCodeSerializer(qr).data)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])   # Thiết bị/camera test; production nên yêu cầu token hoặc API key
def entry(request):
    """
    Gửi xe (ENTRY):
    - Body: { qr, gate_id, plate_text }
    - Kiểm tra QR active + gate là ENTRY.
    - Lưu plate_text vào QR.last_plate.
    - Cập nhật/khởi tạo Vehicle cho user.
    - Tạo ParkingSession status='open'.
    """
    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active").select_related("user").first()
    if not qr:
        return Response({"detail": "QR không hợp lệ/không active"}, status=404)

    # Gate
    try:
        gate = Gate.objects.get(pk=request.data.get("gate_id"))
        if gate.type != "entry":
            return Response({"detail": "gate_id phải là ENTRY"}, status=400)
    except Gate.DoesNotExist:
        return Response({"detail": "gate_id không tồn tại"}, status=404)

    # Plate
    plate = _norm(request.data.get("plate_text"))
    qr.last_plate = plate
    qr.save(update_fields=["last_plate"])

    # Vehicle của user
    vehicle = qr.user.vehicles.first()
    if not vehicle:
        vehicle = Vehicle.objects.create(owner=qr.user, plate_number=plate or "UNKNOWN")
    elif plate:
        vehicle.plate_number = plate
        vehicle.save(update_fields=["plate_number"])

    # Tariff
    tariff = Tariff.objects.first()
    if not tariff:
        return Response({"detail": "Chưa cấu hình Tariff"}, status=400)

    # Session OPEN
    sess = ParkingSession.objects.create(
        user=qr.user,
        vehicle=vehicle,
        entry_gate=gate,
        entry_plate=plate or None,
        tariff=tariff,
        status="open",
    )
    return Response(ParkingSessionSerializer(sess).data, status=201)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])   # Thiết bị/camera test; production nên yêu cầu token hoặc API key
def exit(request):
    """
    Rời bến (EXIT):
    - Body: { qr, gate_id, plate_text }
    - Tìm session OPEN của user từ QR.
    - So khớp plate_text với QR.last_plate và/hoặc Vehicle.
    - Nếu khớp: đóng phiên, tính tiền theo tariff.pricing_rule, trả amount.
    """
    qr = QRCode.objects.filter(value=request.data.get("qr"), status="active").select_related("user").first()
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
    score_qr = _similar(exit_plate, getattr(qr, "last_plate", ""))
    score_vehicle = _similar(exit_plate, getattr(sess.vehicle, "plate_number", ""))

    if max(score_qr, score_vehicle) < 0.80:
        return Response(
            {"detail": "Biển số không khớp", "score_qr": score_qr, "score_vehicle": score_vehicle},
            status=409,
        )

    # Tính phí đơn giản theo pricing_rule
    now = timezone.now()
    rule = sess.tariff.pricing_rule or {}
    free = int(rule.get("free_first_min", 0))
    block = int(rule.get("block_minutes", 60))
    per = int(rule.get("per_block", 10000))

    minutes = int((now - sess.entry_time).total_seconds() // 60)
    payable = max(0, minutes - free)
    blocks = (payable + block - 1) // block
    fee = blocks * per

    # Cập nhật phiên
    sess.exit_gate = gate
    sess.exit_time = now
    sess.exit_plate = exit_plate or None
    sess.amount = fee
    sess.status = "closed"
    sess.save()

    return Response({"session_id": str(sess.id), "amount": fee, "minutes": minutes}, status=200)
