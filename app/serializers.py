from datetime import datetime
import re

from django.utils import timezone
from rest_framework import serializers

from .models import (
    User, Vehicle, QRCode, Gate, Tariff,
    ParkingSession, Payment, PlateReading
)

# ==== Helpers ====
PLATE_RE = re.compile(r"^[A-Z0-9\-]{5,12}$")   # đơn giản & linh hoạt, bạn có thể siết theo chuẩn VN sau

def normalize_plate(s: str | None) -> str | None:
    if not s:
        return s
    s = s.strip().upper().replace(" ", "")
    return s


# ==== Serializers ====

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "full_name", "phone", "email", "date_joined", "last_login"]
        read_only_fields = ["id", "date_joined", "last_login"]

    def validate_phone(self, v):
        if v and not re.fullmatch(r"^\+?\d{8,20}$", v):
            raise serializers.ValidationError("Số điện thoại không hợp lệ.")
        return v


class VehicleSerializer(serializers.ModelSerializer):
    plate_number = serializers.CharField()

    class Meta:
        model = Vehicle
        fields = ["id", "owner", "plate_number"]
        read_only_fields = ["id"]

    def validate_plate_number(self, v):
        v = normalize_plate(v)
        if not v or not PLATE_RE.fullmatch(v):
            raise serializers.ValidationError("Biển số phải gồm 5-12 ký tự [A-Z0-9-].")
        return v

    def validate(self, attrs):
        # plate phải thuộc về owner (unique trong phạm vi owner nếu bạn muốn)
        owner = attrs.get("owner") or getattr(self.instance, "owner", None)
        plate = attrs.get("plate_number") or getattr(self.instance, "plate_number", None)
        if owner and plate:
            qs = Vehicle.objects.filter(owner=owner, plate_number=plate)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("Người dùng này đã có xe với biển số này.")
        return attrs

    def to_internal_value(self, data):
        # normalize trước khi validate
        if "plate_number" in data and data["plate_number"]:
            data = {**data, "plate_number": normalize_plate(data["plate_number"])}
        return super().to_internal_value(data)


class QRCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRCode
        fields = ["id", "user", "value", "status", "issued_at", "expired_at"]
        read_only_fields = ["id", "issued_at"]

    def validate_value(self, v):
        if len(v) < 6:
            raise serializers.ValidationError("Giá trị QR quá ngắn.")
        return v

    def validate(self, attrs):
        status = attrs.get("status") or getattr(self.instance, "status", None)
        expired_at = attrs.get("expired_at") or getattr(self.instance, "expired_at", None)
        if expired_at and expired_at <= timezone.now():
            # cho phép set quá khứ nếu status = expired
            if status != "expired":
                raise serializers.ValidationError("expired_at nằm trong quá khứ → status phải là 'expired'.")
        return attrs


class GateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gate
        fields = ["id", "name", "type", "location"]
        read_only_fields = ["id"]


class TariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariff
        fields = ["id", "name", "pricing_rule", "currency"]
        read_only_fields = ["id"]

    def validate_currency(self, v):
        v = v.upper()
        if not re.fullmatch(r"^[A-Z]{3}$", v) and v != "VND":
            raise serializers.ValidationError("Currency phải là mã 3 chữ cái (VD: VND, USD).")
        return v

    def validate_pricing_rule(self, rule):
        # ví dụ: {"free_first_min":15,"block_minutes":60,"per_block":10000}
        required = ["block_minutes", "per_block"]
        for k in required:
            if k not in rule:
                raise serializers.ValidationError(f"pricing_rule thiếu khóa bắt buộc: {k}")
            if not isinstance(rule[k], int) or rule[k] < 0:
                raise serializers.ValidationError(f"pricing_rule.{k} phải là số nguyên không âm.")
        if "free_first_min" in rule:
            if not isinstance(rule["free_first_min"], int) or rule["free_first_min"] < 0:
                raise serializers.ValidationError("pricing_rule.free_first_min phải là số nguyên không âm.")
        return rule


class ParkingSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkingSession
        fields = [
            "id", "user", "vehicle", "entry_gate", "exit_gate",
            "entry_time", "exit_time",
            "entry_plate", "exit_plate",
            "status", "amount", "tariff"
        ]
        read_only_fields = ["id", "entry_time"]

    def to_internal_value(self, data):
        for k in ("entry_plate", "exit_plate"):
            if k in data and data[k]:
                data[k] = normalize_plate(data[k])
        return super().to_internal_value(data)

    def validate(self, attrs):
        # user & vehicle phải khớp chủ sở hữu
        user = attrs.get("user") or getattr(self.instance, "user", None)
        vehicle = attrs.get("vehicle") or getattr(self.instance, "vehicle", None)
        if user and vehicle and vehicle.owner_id != user.id:
            raise serializers.ValidationError("Xe không thuộc về người dùng này.")

        # kiểm tra gate type
        entry_gate = attrs.get("entry_gate") or getattr(self.instance, "entry_gate", None)
        exit_gate = attrs.get("exit_gate") or getattr(self.instance, "exit_gate", None)
        if entry_gate and entry_gate.type != "entry":
            raise serializers.ValidationError("entry_gate phải có type = 'entry'.")
        if exit_gate and exit_gate.type != "exit":
            raise serializers.ValidationError("exit_gate phải có type = 'exit'.")

        # kiểm tra thời gian
        entry_time = attrs.get("entry_time") or getattr(self.instance, "entry_time", None)
        exit_time = attrs.get("exit_time") or getattr(self.instance, "exit_time", None)
        if entry_time and exit_time and exit_time < entry_time:
            raise serializers.ValidationError("exit_time không thể trước entry_time.")

        # nếu status = closed ⇒ cần có exit_time & amount
        status_val = attrs.get("status") or getattr(self.instance, "status", None)
        amount = attrs.get("amount") or getattr(self.instance, "amount", None)
        if status_val == "closed":
            if not exit_time:
                raise serializers.ValidationError("Đóng phiên cần có exit_time.")
            if amount is None or amount < 0:
                raise serializers.ValidationError("Đóng phiên cần amount hợp lệ (>=0).")

        # format plate
        for key in ("entry_plate", "exit_plate"):
            v = attrs.get(key) or getattr(self.instance, key, None)
            if v and not PLATE_RE.fullmatch(v):
                raise serializers.ValidationError(f"{key} không hợp lệ (5-12 ký tự [A-Z0-9-]).")
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "session", "provider", "amount", "currency", "paid_at", "status", "tx_ref"]
        read_only_fields = ["id"]

    def validate_amount(self, v):
        if v is None or v < 0:
            raise serializers.ValidationError("amount phải >= 0.")
        return v

    def validate_currency(self, v):
        v = v.upper()
        if not re.fullmatch(r"^[A-Z]{3}$", v) and v != "VND":
            raise serializers.ValidationError("Currency phải là mã 3 chữ cái (VD: VND, USD).")
        return v

    def validate(self, attrs):
        session = attrs.get("session") or getattr(self.instance, "session", None)
        if not session:
            return attrs

        # nếu mark PAID, session nên đã closed & amount khớp (nếu bạn muốn chặt chẽ)
        status_val = attrs.get("status") or getattr(self.instance, "status", None)
        amount = attrs.get("amount") or getattr(self.instance, "amount", None)
        if status_val == "paid":
            if session.status != "closed":
                raise serializers.ValidationError("Chỉ thanh toán cho phiên đã 'closed'.")
            if session.amount is not None and amount is not None and amount != session.amount:
                raise serializers.ValidationError("amount không khớp amount của session.")
        return attrs


class PlateReadingSerializer(serializers.ModelSerializer):
    plate_text = serializers.CharField()

    class Meta:
        model = PlateReading
        fields = ["id", "gate", "image_path", "plate_text", "confidence", "captured_at", "session"]
        read_only_fields = ["id", "captured_at"]

    def to_internal_value(self, data):
        if "plate_text" in data and data["plate_text"]:
            data = {**data, "plate_text": normalize_plate(data["plate_text"])}
        return super().to_internal_value(data)

    def validate_plate_text(self, v):
        if v and not PLATE_RE.fullmatch(v):
            raise serializers.ValidationError("plate_text không hợp lệ (5-12 ký tự [A-Z0-9-]).")
        return v

    def validate_confidence(self, v):
        if v < 0 or v > 1:
            raise serializers.ValidationError("confidence phải trong khoảng [0, 1].")
        return v

    def validate(self, attrs):
        # nếu gắn vào session: chỉ cho phép gắn session đang mở
        sess = attrs.get("session") or getattr(self.instance, "session", None)
        if sess and sess.status != "open":
            raise serializers.ValidationError("Chỉ nhận PlateReading cho session đang 'open'.")
        return attrs
