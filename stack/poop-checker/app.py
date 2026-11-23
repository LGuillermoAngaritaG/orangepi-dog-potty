"""Photographs the potty spot and estimates whether it holds poop.

POST /check    grab a frame, save the cropped spot, return {"id", "poop_prob"}
POST /label    ?id=...&label=clean|poop, file the photo into the training set
POST /preview  save the full frame with the crop box drawn, for aiming the crop
POST /frame    save one full frame to data/frames/, raw material for synthetic training images
POST /note     ?id=...&event=rinse_open|rinsed|rinse_skipped|rinse_paused, what the hose did for a photo
POST /delete   ?id=..., move every file of a photo to data/deleted/<id>/ (recoverable)
GET  /history  ?limit=30, the newest check photos with their label and what the hose did
GET  /health   model status, labeled photo counts and the number of saved patio frames

poop_prob is null until data/model.onnx exists. Dropping in a new model.onnx
takes effect on the next check, with no restart.
"""

import ast
import json
import os
import shutil
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import onnxruntime as ort

RTSP_URL = os.environ["RTSP_URL"]
CROP = [float(v) for v in os.environ.get("CROP", "0,0,1,1").split(",")]
DATA = Path(os.environ.get("DATA_DIR", "/data"))
WWW = Path(os.environ.get("WWW_DIR", "/www"))
PORT = int(os.environ.get("PORT", "8099"))
MODEL_PATH = DATA / "model.onnx"
UNLABELED = DATA / "unlabeled"
DATASET = DATA / "dataset"

# Full camera frames, kept next to each crop and filed under the same label,
# so a later change of CROP (or a crop around the dog) can reuse old labels.
FULL = DATA / "full"

# Full frames of the empty patio across the day and night, onto which poop and
# decoys are added later to make training images.
FRAMES = DATA / "frames"
LABELS = ("clean", "poop")

# One JSON line per check (with the model's poop_prob) and per hose event, for
# the history page. Labels come from the dataset folders instead.
HISTORY = DATA / "history.jsonl"
NOTES = ("rinse_open", "rinsed", "rinse_skipped", "rinse_paused")

# Small copies of the check photos for the history page.
THUMBS = WWW / "thumbs"
THUMB_SIZE = 160

# Photos deleted from the history page. Moved here, not erased, so a wrong tap
# can be undone by moving the files back.
DELETED = DATA / "deleted"

# Training photos and model inputs share this square size, so the model sees
# the spot the same way in both places.
SPOT_SIZE = 640

_model = {"mtime": None, "session": None, "names": None, "size": None}


def grab_frame():
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    frame = None
    try:

        # The first frames after connecting can be gray until a keyframe arrives.
        for _ in range(10):
            ok, img = cap.read()
            if ok:
                frame = img
    finally:
        cap.release()
    if frame is None:
        raise RuntimeError(f"no frame from {RTSP_URL}")
    return frame


def crop_box(frame):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = CROP
    return int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)


def crop_spot(frame):
    x1, y1, x2, y2 = crop_box(frame)
    spot = frame[y1:y2, x1:x2]
    return cv2.resize(spot, (SPOT_SIZE, SPOT_SIZE), interpolation=cv2.INTER_AREA)


def load_model():
    if not MODEL_PATH.exists():
        return None
    mtime = MODEL_PATH.stat().st_mtime
    if mtime != _model["mtime"]:
        session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])

        # Ultralytics stores class names as a dict literal, e.g. "{0: 'clean', 1: 'poop'}".
        meta = session.get_modelmeta().custom_metadata_map
        names = ast.literal_eval(meta["names"]) if "names" in meta else dict(enumerate(LABELS))
        _model.update(
            mtime=mtime,
            session=session,
            names=[names[i] for i in sorted(names)],
            size=session.get_inputs()[0].shape[2],
        )
    return _model


def poop_probability(spot):
    model = load_model()
    if model is None:
        return None
    size = model["size"]
    img = cv2.resize(spot, (size, size), interpolation=cv2.INTER_AREA)
    x = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = x.transpose(2, 0, 1)[None]
    session = model["session"]
    out = session.run(None, {session.get_inputs()[0].name: x})[0][0]

    # Ultralytics exports softmax outputs. Raw logits get normalized here.
    if not np.isclose(out.sum(), 1.0, atol=1e-3):
        out = np.exp(out - out.max())
        out = out / out.sum()
    return round(float(out[model["names"].index("poop")]), 4)


def log_event(shot, event, **extra):
    record = {"id": shot, "event": event, "time": time.strftime("%Y-%m-%d %H:%M:%S"), **extra}
    with HISTORY.open("a") as f:
        f.write(json.dumps(record) + "\n")


def save_thumb(shot, spot):
    THUMBS.mkdir(parents=True, exist_ok=True)
    small = cv2.resize(spot, (THUMB_SIZE, THUMB_SIZE), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(THUMBS / f"{shot}.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 80])


def check():
    frame = grab_frame()
    spot = crop_spot(frame)
    shot = uuid.uuid4().hex[:12]
    UNLABELED.mkdir(parents=True, exist_ok=True)
    WWW.mkdir(parents=True, exist_ok=True)
    (FULL / "unlabeled").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(FULL / "unlabeled" / f"{shot}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(UNLABELED / f"{shot}.jpg"), spot)
    cv2.imwrite(str(WWW / f"{shot}.jpg"), spot)
    save_thumb(shot, spot)
    prob = poop_probability(spot)
    log_event(shot, "check", poop_prob=prob)
    return {"id": shot, "poop_prob": prob}


def label(shot, name):
    if not shot.isalnum() or name not in LABELS:
        return 400, {"error": "id must be alphanumeric and label clean or poop"}
    candidates = [UNLABELED / f"{shot}.jpg"] + [DATASET / n / f"{shot}.jpg" for n in LABELS]
    source = next((p for p in candidates if p.exists()), None)
    if source is None:
        return 404, {"error": f"no photo {shot}"}
    target = DATASET / name / f"{shot}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, target)
    full = next((p for p in (FULL / d / f"{shot}.jpg" for d in ("unlabeled",) + LABELS) if p.exists()), None)
    if full is not None:
        (FULL / name).mkdir(parents=True, exist_ok=True)
        shutil.move(full, FULL / name / f"{shot}.jpg")
    return 200, {"id": shot, "label": name}


def preview():
    frame = grab_frame()
    x1, y1, x2, y2 = crop_box(frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
    WWW.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(WWW / "preview.jpg"), frame)
    return {"saved": "/local/potty/preview.jpg"}


def frame():
    shot = grab_frame()
    FRAMES.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + ".jpg"
    cv2.imwrite(str(FRAMES / name), shot, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return {"saved": name}


def note(shot, event):
    if not shot.isalnum() or event not in NOTES:
        return 400, {"error": f"id must be alphanumeric and event one of {', '.join(NOTES)}"}
    if not (WWW / f"{shot}.jpg").exists():
        return 404, {"error": f"no photo {shot}"}
    log_event(shot, event)
    return 200, {"id": shot, "event": event}


def delete(shot):
    if not shot.isalnum():
        return 400, {"error": "id must be alphanumeric"}
    places = [(WWW, "www"), (THUMBS, "thumb"), (UNLABELED, "crop-unlabeled"), (FULL / "unlabeled", "full-unlabeled")]
    places += [(DATASET / n, f"crop-{n}") for n in LABELS] + [(FULL / n, f"full-{n}") for n in LABELS]
    moved = []
    for folder, name in places:
        source = folder / f"{shot}.jpg"
        if source.exists():
            (DELETED / shot).mkdir(parents=True, exist_ok=True)
            shutil.move(source, DELETED / shot / f"{name}.jpg")
            moved.append(name)
    if not moved:
        return 404, {"error": f"no photo {shot}"}
    log_event(shot, "deleted")
    return 200, {"id": shot, "moved_to": f"deleted/{shot}", "files": moved}


def history(limit):
    events = {}
    if HISTORY.exists():
        for line in HISTORY.read_text().splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            events.setdefault(record.get("id"), []).append(record)

    # Every check photo stays in WWW under its id, and its file time is the
    # time of the check.
    photos = [p for p in WWW.glob("*.jpg") if p.stem.isalnum() and p.stem != "preview"]
    photos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for p in photos[:limit]:
        shot = p.stem
        if not (THUMBS / p.name).exists():
            img = cv2.imread(str(p))
            if img is not None:
                save_thumb(shot, img)
        mine = events.get(shot, [])
        kinds = {e.get("event") for e in mine}
        hose = (
            "rinsed" if "rinsed" in kinds
            else "stopped" if "rinse_open" in kinds
            else "skipped" if "rinse_skipped" in kinds
            else "paused" if "rinse_paused" in kinds
            else None
        )
        items.append({
            "id": shot,
            "time": time.strftime("%d/%m %H:%M", time.localtime(p.stat().st_mtime)),
            "label": next((n for n in LABELS if (DATASET / n / p.name).exists()), None),
            "prob": next((e.get("poop_prob") for e in mine if e.get("event") == "check"), None),
            "hose": hose,
        })
    return {"items": items}


def health():
    counts = {n: len(list((DATASET / n).glob("*.jpg"))) for n in LABELS}
    frames = len(list(FRAMES.glob("*.jpg"))) if FRAMES.exists() else 0
    return {"model": MODEL_PATH.exists(), "labeled": counts, "frames": frames}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def run(self, fn):
        try:
            self.reply(*fn())
        except Exception as exc:
            self.reply(500, {"error": str(exc)})

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        routes = {
            "/health": lambda: (200, health()),
            "/history": lambda: (200, history(max(1, min(200, int(query.get("limit", "30")))))),
        }
        if url.path in routes:
            self.run(routes[url.path])
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        routes = {
            "/check": lambda: (200, check()),
            "/label": lambda: label(query.get("id", ""), query.get("label", "")),
            "/preview": lambda: (200, preview()),
            "/frame": lambda: (200, frame()),
            "/note": lambda: note(query.get("id", ""), query.get("event", "")),
            "/delete": lambda: delete(query.get("id", "")),
        }
        if url.path in routes:
            self.run(routes[url.path])
        else:
            self.reply(404, {"error": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
