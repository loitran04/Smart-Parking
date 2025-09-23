# app/lpr_v8.py
from __future__ import annotations
from pathlib import Path
import os, yaml, numpy as np, cv2, torch
import torch.nn.functional as F

# ==== IMPORT CRNN & CHARSET từ repo của bạn ====
# nếu app/ nằm cạnh ocr_simple/, thêm path cho chắc chắn:
import sys
ROOT = Path(__file__).resolve().parents[1]  # thư mục gốc dự án
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from model import CRNN                       # ocr_simple/model.py :contentReference[oaicite:3]{index=3}
from dataset import read_charset            # ocr_simple/dataset.py :contentReference[oaicite:4]{index=4}

# ==== ĐƯỜNG DẪN MODEL ====
# YOLOv8 detect biển số (đã train xong)
DET_WEIGHTS = ROOT / r"runs/detect/train8/weights/best.pt"
# CRNN OCR (đã train xong)
OCR_WEIGHTS = ROOT / r"ocr_simple/out_rule2/best.pth"      # mặc định train.py lưu ở đây :contentReference[oaicite:5]{index=5}
CHARSET_TXT = ROOT / r"configs_clean_rule2/charset.txt"    # bảng ký tự bạn dùng khi train :contentReference[oaicite:6]{index=6}

# ==== THAM SỐ ====
IMG_H, IMG_W = 48, 320   # kích thước chuẩn CRNN (khớp infer của bạn) :contentReference[oaicite:7]{index=7}

# ==== CACHE MODEL ====
_det = None
_crnn = None
_ch2idx, _idx2ch = None, None
_device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

def _load_models():
    global _det, _crnn, _ch2idx, _idx2ch
    # YOLOv8 detector
    if _det is None:
        from ultralytics import YOLO
        _det = YOLO(str(DET_WEIGHTS))
    # CRNN OCR
    if _crnn is None:
        _ch2idx, _idx2ch = read_charset(str(CHARSET_TXT))  # :contentReference[oaicite:8]{index=8}
        _crnn = CRNN(num_classes=len(_idx2ch), in_ch=1, img_h=IMG_H).to(_device)  # :contentReference[oaicite:9]{index=9}
        state = torch.load(str(OCR_WEIGHTS), map_location=_device)
        _crnn.load_state_dict(state, strict=True)
        _crnn.eval()

def _to_bgr(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _best_plate_box(img_bgr, conf=0.25, imgsz=1024):
    """Detect biển số bằng YOLOv8, trả crop + bbox + conf"""
    _load_models()
    res = _det.predict(img_bgr, imgsz=imgsz, conf=conf, verbose=False)
    boxes = res[0].boxes
    if boxes is None or boxes.xyxy.shape[0] == 0:
        return None
    i = int(boxes.conf.argmax().item())
    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
    H, W = img_bgr.shape[:2]
    # nới biên 10–20% cho chắc (giống autoplate_infer.py) :contentReference[oaicite:10]{index=10}
    padx = int(0.08 * (x2 - x1))
    pady = int(0.20 * (y2 - y1))
    x1 = max(0, x1 - padx); y1 = max(0, y1 - pady)
    x2 = min(W, x2 + padx); y2 = min(H, y2 + pady)
    crop = img_bgr[y1:y2, x1:x2].copy()
    return crop, (int(x1), int(y1), int(x2), int(y2)), float(boxes.conf[i].item())

def _preprocess_for_crnn(img_bgr):
    """Giống logic preprocess gray/CLAHE/resize trong infer của bạn, rồi chuẩn hóa [-1,1]"""  # :contentReference[oaicite:11]{index=11}
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    g = clahe.apply(g)
    blur = cv2.GaussianBlur(g, (0,0), 1.0)
    sharp = cv2.addWeighted(g, 1.5, blur, -0.5, 0)
    im = cv2.resize(sharp, (IMG_W, IMG_H), interpolation=cv2.INTER_LINEAR)
    im = (im.astype(np.float32)/255.0 - 0.5)/0.5
    t = torch.from_numpy(im).unsqueeze(0).unsqueeze(0).to(_device)  # [1,1,H,W]
    return t

def _ctc_greedy_decode(logp):
    """logp: [T,B,C] ⇒ list ids (bỏ blank=0, gộp lặp)"""  # bị tương tự trong code của bạn :contentReference[oaicite:12]{index=12}
    pred = logp.argmax(2).permute(1,0).detach().cpu().numpy().tolist()  # [B,T]
    outs=[]
    for seq in pred:
        s=[]; prev=-1
        for a in seq:
            if a!=prev and a!=0: s.append(a)
            prev=a
        outs.append(s)
    return outs[0] if outs else []

def _force_plate_format(txt: str) -> str:
    """Áp luật biển số VN nhẹ (map O→0, I→1, …), giống autoplate_infer.py"""  # :contentReference[oaicite:13]{index=13}
    import re
    MAP = {"O":"0","I":"1","Z":"2","S":"5","B":"8","G":"6"}
    RULE = re.compile(r"^[0-9]{2}[A-Z0-9]{2}[0-9]{4,5}$")
    s = re.sub(r"[^A-Z0-9]", "", txt.upper())
    if len(s) > 9: s = s[:9]
    if len(s) < 4: return s
    L = list(s); n = len(L)
    for k in range(n):
        if k in (2,3): continue
        if L[k].isalpha(): L[k] = MAP.get(L[k], L[k])
    s2 = "".join(L)
    return s2 if RULE.match(s2) else s

def _ocr_text_from_crop(crop_bgr):
    """Crop biển -> CRNN -> text"""
    _load_models()
    inp = _preprocess_for_crnn(crop_bgr)
    with torch.no_grad():
        logits = _crnn(inp)               # [T,1,C]
        logp = F.log_softmax(logits, dim=2)
        ids = _ctc_greedy_decode(logp)    # list[int]
        text = "".join(_idx2ch[i] for i in ids if i < len(_idx2ch))
        text = _force_plate_format(text)
    # có thể tính “độ tự tin” riêng nếu cần; ở đây trả text là chính
    return text

# ===== API chính, giữ giống tên cũ =====
def recognize_plate_from_bytes(image_bytes: bytes):
    img = _to_bgr(image_bytes)
    best = _best_plate_box(img)
    if not best:
        return {"ok": False, "detail": "no_plate"}
    crop, bbox, det_conf = best
    text = _ocr_text_from_crop(crop)
    return {
        "ok": True,
        "text": text,
        "det_conf": float(det_conf),
        "ocr_conf": None,    # CRNN-CTC không có conf trực tiếp; nếu cần có thể ước lượng logp trung bình
        "n_chars": len(text),
        "bbox": bbox,
    }
