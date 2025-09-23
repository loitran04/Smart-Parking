from __future__ import annotations
from pathlib import Path
import re, cv2, torch, numpy as np
import torch.nn.functional as F
from .model import CRNN
from .dataset import read_charset

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "lpr_models"
DET_WEIGHTS = MODELS_DIR / "best.pt"
OCR_WEIGHTS = MODELS_DIR / "best_acc.pth"
CHARSET_TXT = MODELS_DIR / "charset.txt"

IMG_H, IMG_W = 48, 320
_device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

_det = None
_crnn = None
_ch2idx, _idx2ch = None, None

RULE = re.compile(r"^[0-9]{2}[A-Z0-9]{2}[0-9]{4,5}$")
MAP_LET2NUM = {"O":"0","I":"1","Z":"2","S":"5","B":"8","G":"6"}
def _force_plate_format(txt: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", txt.upper())
    if len(s) > 9: s = s[:9]
    if len(s) < 4: return s
    L = list(s)
    for k,ch in enumerate(L):
        if k in (2,3): continue
        if ch.isalpha(): L[k] = MAP_LET2NUM.get(ch, ch)
    s2 = "".join(L)
    return s2 if RULE.match(s2) else s

def _load_models():
    global _det, _crnn, _ch2idx, _idx2ch
    if _det is None:
        from ultralytics import YOLO
        _det = YOLO(str(DET_WEIGHTS))
    if _crnn is None:
        _ch2idx, _idx2ch = read_charset(str(CHARSET_TXT))
        _crnn = CRNN(num_classes=len(_idx2ch), img_h=IMG_H).to(_device)
        state = torch.load(str(OCR_WEIGHTS), map_location=_device)
        _crnn.load_state_dict(state, strict=True)
        _crnn.eval()

def _to_bgr(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _best_plate_box(img_bgr, conf=0.25, imgsz=1024):
    _load_models()
    r = _det.predict(img_bgr, imgsz=imgsz, conf=conf, verbose=False)
    boxes = r[0].boxes
    if boxes is None or boxes.xyxy.shape[0] == 0:
        return None
    i = int(boxes.conf.argmax().item())
    x1,y1,x2,y2 = boxes.xyxy[i].cpu().numpy().astype(int)
    det_conf = float(boxes.conf[i].item())
    H,W = img_bgr.shape[:2]
    padx = int(0.08*(x2-x1)); pady = int(0.20*(y2-y1))
    x1 = max(0, x1-padx); y1 = max(0, y1-pady)
    x2 = min(W, x2+padx); y2 = min(H, y2+pady)
    crop = img_bgr[y1:y2, x1:x2].copy()
    return crop, (x1,y1,x2,y2), det_conf

def _preprocess_for_crnn(img_bgr):
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(2.0,(8,8)); g = clahe.apply(g)
    blur = cv2.GaussianBlur(g,(0,0),1.0)
    sharp = cv2.addWeighted(g,1.5,blur,-0.5,0)
    im = cv2.resize(sharp,(IMG_W,IMG_H),interpolation=cv2.INTER_LINEAR).astype(np.float32)
    im = (im/255.0 - 0.5)/0.5
    t = torch.from_numpy(im).unsqueeze(0).unsqueeze(0).to(_device)
    return t

def _ctc_greedy_decode(logp):
    pred = logp.argmax(2).permute(1,0).detach().cpu().numpy().tolist()
    outs=[]
    for seq in pred:
        s=[]; prev=-1
        for a in seq:
            if a!=prev and a!=0: s.append(a)
            prev=a
        outs.append(s)
    return outs[0] if outs else []

def _ocr_text_and_conf(crop_bgr):
    _load_models()
    x = _preprocess_for_crnn(crop_bgr)
    with torch.no_grad():
        logits = _crnn(x)
        logp = torch.log_softmax(logits, dim=2)
        ids = _ctc_greedy_decode(logp)
        text = "".join(_idx2ch[i] for i in ids if i < len(_idx2ch))
        text = _force_plate_format(text)
        prob = torch.exp(logp).max(2).values.mean().item()
    return text, float(prob)

def recognize_plate_from_bytes(image_bytes: bytes):
    img = _to_bgr(image_bytes)
    best = _best_plate_box(img)
    if not best:
        return {"ok": False, "detail": "no_plate"}
    crop, bbox, det_conf = best
    text, ocr_conf = _ocr_text_and_conf(crop)
    return {
        "ok": True,
        "text": text,
        "det_conf": det_conf,
        "ocr_conf": ocr_conf,
        "n_chars": len(text),
        "bbox": bbox,
    }
