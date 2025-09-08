# app/lpr.py
from __future__ import annotations
from pathlib import Path
import yaml, numpy as np, cv2, torch

MODELS_DIR = Path(__file__).resolve().parent / "lpr_models"
DET_WEIGHTS = MODELS_DIR / "LP_detector.pt"       # hoặc *_nano_61.pt
OCR_WEIGHTS = MODELS_DIR / "LP_ocr.pt"            # hoặc *_nano_62.pt
LABEL_FILE  = MODELS_DIR / "Letter_detect.yaml"

_det_model = None
_ocr_model = None
_CHARS = None

def _load_models():
    global _det_model, _ocr_model, _CHARS
    if _det_model is None:
        # tải code YOLOv5 từ GitHub bằng Torch Hub (không cần pip install yolov5)
        _det_model = torch.hub.load(
            'ultralytics/yolov5', 'custom',
            path=str(DET_WEIGHTS),
            trust_repo=True  # cho phép load repo ngoài
        )
        _det_model.conf = 0.25
        _det_model.iou = 0.45
        _det_model.max_det = 1  # chỉ 1 biển

    if _ocr_model is None:
        _ocr_model = torch.hub.load(
            'ultralytics/yolov5', 'custom',
            path=str(OCR_WEIGHTS),
            trust_repo=True
        )
        _ocr_model.conf = 0.25
        _ocr_model.iou = 0.45
        _ocr_model.max_det = 128

    if _CHARS is None:
        with open(LABEL_FILE, "r", encoding="utf-8") as f:
            _CHARS = yaml.safe_load(f)["names"]

def _to_bgr(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _best_plate_box(img):
    _load_models()
    r = _det_model(img, size=640)
    xyxy = r.xyxy[0]
    if xyxy is None or len(xyxy) == 0:
        return None
    b = xyxy[xyxy[:, 4].argmax()]
    x1, y1, x2, y2, conf, _ = b.tolist()
    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1]-1, x2), min(img.shape[0]-1, y2)
    crop = img[y1:y2, x1:x2].copy()
    return crop, (x1, y1, x2, y2), float(conf)

def _ocr_chars(crop):
    _load_models()
    r = _ocr_model(crop, size=320)
    xyxy = r.xyxy[0]
    if xyxy is None or len(xyxy) == 0:
        return "", 0.0, 0
    items = []
    for row in xyxy.tolist():
        x1, y1, x2, y2, conf, cls = row
        items.append({"x": (x1+x2)/2, "char": _CHARS[int(cls)] if int(cls) < len(_CHARS) else "?", "conf": conf})
    items.sort(key=lambda it: it["x"])
    text = "".join(it["char"] for it in items)
    conf = float(np.mean([it["conf"] for it in items]))
    return text, conf, len(items)

def recognize_plate_from_bytes(image_bytes: bytes):
    img = _to_bgr(image_bytes)
    best = _best_plate_box(img)
    if not best:
        return {"ok": False, "detail": "no_plate"}
    crop, bbox, det_conf = best
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    crop3 = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    text, ocr_conf, n = _ocr_chars(crop3)
    return {
        "ok": True,
        "text": text.upper().replace(" ", ""),
        "det_conf": det_conf,
        "ocr_conf": ocr_conf,
        "n_chars": n,
        "bbox": bbox,
    }
