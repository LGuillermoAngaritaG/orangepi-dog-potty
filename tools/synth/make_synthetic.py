#!/usr/bin/env python3
"""Makes synthetic training images for the poop detector: poop, or a harmless
decoy, added to frames of the empty patio, with YOLO box labels.

Providers
  paste   cut-outs of real poop from labeled camera photos. Free and local.
  openai  OpenAI image edit API on a floor patch around the chosen spot.
  gemini  Gemini image model on the same patch.
  fake    draws a dark blob and adds noise. Tests the compositing, no API.

Only a square patch of floor around the chosen spot goes to OpenAI or Gemini,
never the whole frame. The returned patch is compared with the original and
only the changed area near the spot is pasted back, so the rest of each
training image stays a real camera frame. Decoys (leaf, wet spot, urine,
toy, ...) go through the same steps and are labeled clean, so a model can't
learn "edited means poop".

API keys come from OPENAI_API_KEY / GEMINI_API_KEY, or from
~/.config/potty-synth/keys.env (KEY=value lines). They are never printed.

Output, in --out:
  images/<name>.jpg   full frame with the edit
  labels/<name>.txt   "0 cx cy w h" (normalized) for poop, empty for a decoy
  review/<name>.jpg   small copy with the box drawn, for checking by eye
  manifest.csv        one row per attempt, including rejected ones
  review.html         all review images on one page
"""

import argparse
import base64
import csv
import io
import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

HERE = Path(__file__).resolve().parent

# Floor of the patio in the camera view since 2026-11-21 23:40, as fractions
# of the frame width and height. The walls, the strip behind the hose on the
# right (bin, bottles) and the bottom-left corner, hidden by the object right
# at the lens, are left out. The view shifts a little between frames, so the
# edges stay a bit inside the real floor.
FLOOR = [(0.02, 0.42), (0.41, 0.27), (0.60, 0.28), (0.75, 0.32), (0.86, 0.39), (0.93, 0.45),
         (0.99, 0.50), (0.99, 0.99), (0.37, 0.99), (0.21, 0.71), (0.13, 0.61), (0.02, 0.59)]

# Things shrink toward the back wall. The real poop next to the drain (y 0.43)
# is about 90 px wide in a 2304 px frame. HORIZON is the height where size
# would reach zero.
REF_Y, REF_W, HORIZON = 0.43, 90 / 2304, 0.15

API_SIZE = 1024
DEFAULT_MODELS = {"openai": "gpt-image-1.5", "gemini": "gemini-3.1-flash-image"}

POOP_SHAPES = [
    "a single log of dog poop",
    "two or three small pieces of dog poop close together",
    "a soft pile of dog poop",
    "a dry, dark log of dog poop",
    "a fresh, slightly shiny pile of dog poop",
    "a long, curved log of dog poop",
]
DECOYS = [
    "a fallen dry leaf",
    "a small puddle of clear water",
    "a small yellow puddle of dog urine",
    "a small twig",
    "a crumpled piece of white paper",
    "a small rubber dog toy ball",
    "a faint smudge of dirt",
    "a plastic bottle cap",
]


def load_keys():
    keys = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "GEMINI_API_KEY")}
    path = Path.home() / ".config/potty-synth/keys.env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                keys.setdefault(k.strip(), None)
                if not keys.get(k.strip()):
                    keys[k.strip()] = v.strip().strip('"')
    return keys


def inside(x, y, poly):
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def expected_width(y_frac, frame_w):
    return frame_w * REF_W * max(y_frac - HORIZON, 0.02) / (REF_Y - HORIZON)


def is_gray(im):
    r, g, b = ImageStat.Stat(im.resize((64, 36))).mean
    return max(abs(r - g), abs(g - b), abs(r - b)) < 4


def pick_spot(rng, frame, patch_factor=None):
    """A floor point, its expected poop width and, for the APIs, a square
    patch centered on it that fits inside the frame."""
    W, H = frame.size
    for _ in range(500):
        x, y = rng.uniform(0, 1), rng.uniform(0.2, 1)
        if not inside(x, y, FLOOR):
            continue
        w = expected_width(y, W) * rng.uniform(0.6, 1.4)

        # The whole object, not just its center, must be on the floor.
        dx, dy = 0.7 * w / W, 0.35 * w / H
        if not all(inside(x + sx * dx, y + sy * dy, FLOOR) for sx in (-1, 1) for sy in (-1, 1)):
            continue
        if patch_factor is None:
            return int(x * W), int(y * H), w, None
        side = int(min(max(w * patch_factor, 320), 1024))
        cx = min(max(int(x * W), side // 2), W - side // 2)
        cy = min(max(int(y * H), side // 2), H - side // 2)
        if not inside(cx / W, cy / H, FLOOR):
            continue
        w = expected_width(cy / H, W) * rng.uniform(0.6, 1.4)
        return cx, cy, w, (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
    raise RuntimeError("no floor spot found")


def prompt_for(kind, thing, gray, frac):
    where = f"exactly in the center of the image, about {frac:.0%} of the image width"
    style = (
        "This is a black-and-white infrared night image from a security camera, so the added "
        "object must be grayscale and lit like the floor."
        if gray else
        "This is a photo from a security camera. Match its lighting, colors, blur, sharpening "
        "halo and noise."
    )
    return (
        f"Tiled patio floor seen from a low security camera. Add {thing} on the floor {where}. "
        f"{style} It must look like it was really there when the photo was taken, with a small "
        "contact shadow. Do not change anything else in the image."
    )


def png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def call_openai(patch, prompt, mask_radius, key, model, quality):
    img = patch.resize((API_SIZE, API_SIZE), Image.LANCZOS)
    mask = Image.new("RGBA", img.size, (0, 0, 0, 255))
    c, r = API_SIZE // 2, mask_radius
    ImageDraw.Draw(mask).ellipse((c - r, c - r, c + r, c + r), fill=(0, 0, 0, 0))
    resp = requests.post(
        "https://api.openai.com/v1/images/edits",
        headers={"Authorization": f"Bearer {key}"},
        data={"model": model, "prompt": prompt, "size": f"{API_SIZE}x{API_SIZE}", "n": "1",
              "quality": quality},
        files={"image[]": ("patch.png", png_bytes(img), "image/png"),
               "mask": ("mask.png", png_bytes(mask), "image/png")},
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI {resp.status_code}: {resp.text[:300]}")
    return Image.open(io.BytesIO(base64.b64decode(resp.json()["data"][0]["b64_json"]))).convert("RGB")


def call_gemini(patch, prompt, key, model):
    img = patch.resize((API_SIZE, API_SIZE), Image.LANCZOS)
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png_bytes(img)).decode()}},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=body,
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini {resp.status_code}: {resp.text[:300]}")
    for cand in resp.json().get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            data = part.get("inline_data") or part.get("inlineData")
            if data:
                return Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")
    raise RuntimeError("Gemini returned no image")


def call_fake(patch, kind, rng, radius):
    """Stands in for an API: a dark blob (or a pale one for a decoy) in the
    center, plus the faint whole-image drift that real models add."""
    img = patch.resize((API_SIZE, API_SIZE), Image.LANCZOS)
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.97, 1.03))
    d = ImageDraw.Draw(img)
    c = API_SIZE // 2
    rx, ry = radius * rng.uniform(0.6, 1.0), radius * rng.uniform(0.25, 0.45)
    color = (70, 55, 45) if kind == "poop" else (190, 170, 90)
    d.ellipse((c - rx, c - ry, c + rx, c + ry), fill=color)
    return img.filter(ImageFilter.GaussianBlur(1))


def composite_edit(orig, edited, expect_w):
    """Paste back only what changed near the center. Returns the new patch and
    the changed area's box in patch pixels, or raises with the reason."""
    s = orig.size[0]
    edited = edited.resize(orig.size, Image.LANCZOS)
    diff = ImageChops.difference(orig, edited).convert("L").filter(ImageFilter.GaussianBlur(2))

    # Models redraw the whole image slightly. The change level away from the
    # center sets the threshold for what counts as the added object.
    ring = Image.new("L", orig.size, 255)
    ImageDraw.Draw(ring).ellipse((s * 0.2, s * 0.2, s * 0.8, s * 0.8), fill=0)
    background = ImageStat.Stat(diff, mask=ring).mean[0]
    threshold = max(25, background * 3 + 12)

    allowed = Image.new("L", orig.size, 0)
    r = min(max(expect_w * 1.8, s * 0.12), s * 0.42)
    ImageDraw.Draw(allowed).ellipse((s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r), fill=255)
    hard = diff.point(lambda v: 255 if v > threshold else 0)
    hard = ImageChops.multiply(hard, allowed)
    hard = hard.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    box = hard.getbbox()
    if box is None:
        raise RuntimeError(f"nothing changed near the center (threshold {threshold:.0f})")
    bw = box[2] - box[0]
    if not 0.25 * expect_w <= bw <= 3.5 * expect_w:
        raise RuntimeError(f"changed area {bw}px wide, expected about {expect_w:.0f}px")
    alpha = hard.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3))
    return Image.composite(edited, orig, alpha), box


def cutout(source_dir, sources, rng):
    """A real poop cut out of a labeled photo: opaque where it's darker than
    the floor around it, fading to clear at the edges."""
    src = rng.choice(sources)
    im = Image.open(source_dir / src["file"]).convert("RGB")
    x1, y1, x2, y2 = src["box"]
    pad = int(max(x2 - x1, y2 - y1) * 0.35)
    crop = im.crop((x1 - pad, y1 - pad, x2 + pad, y2 + pad))
    gray = crop.convert("L")
    border = [gray.getpixel((x, y)) for x in range(crop.width) for y in (0, crop.height - 1)]
    floor = sorted(border)[len(border) // 2]
    alpha = gray.point(lambda v: max(0, min(255, (floor - v - 12) * 6)))

    # Widen by a few pixels so the light halo the camera's sharpening draws
    # around dark objects comes along, instead of a hard dark rim.
    alpha = alpha.filter(ImageFilter.MaxFilter(7))
    ellipse = Image.new("L", crop.size, 0)
    ImageDraw.Draw(ellipse).ellipse((pad * 0.6, pad * 0.6, crop.width - pad * 0.6, crop.height - pad * 0.6), fill=255)
    alpha = ImageChops.multiply(alpha, ellipse.filter(ImageFilter.GaussianBlur(3))).filter(ImageFilter.GaussianBlur(1.5))
    crop.putalpha(alpha)
    return crop, floor


def paste_poop(frame, x, y, want_w, source_dir, sources, rng):
    piece, src_floor = cutout(source_dir, sources, rng)
    if rng.random() < 0.5:
        piece = ImageOps.mirror(piece)
    piece = piece.rotate(rng.uniform(-25, 25), resample=Image.BICUBIC, expand=True)
    tight = piece.getchannel("A").point(lambda v: 255 if v > 60 else 0).getbbox()
    scale = want_w / max(tight[2] - tight[0], 1)
    piece = piece.resize((max(int(piece.width * scale), 4), max(int(piece.height * scale), 4)), Image.LANCZOS)

    # Match the brightness of the floor at the target spot.
    r = int(max(want_w, 20))
    around = frame.crop((x - r, y - r, x + r, y + r)).convert("L")
    target_floor = ImageStat.Stat(around).median[0]
    rgb = ImageEnhance.Brightness(piece.convert("RGB")).enhance(target_floor / max(src_floor, 1))
    if is_gray(frame):
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    a = piece.getchannel("A")
    left, top = x - piece.width // 2, y - piece.height // 2
    frame.paste(rgb, (left, top), a)
    tight = a.point(lambda v: 255 if v > 60 else 0).getbbox()
    W, H = frame.size
    return (max(left + tight[0], 0), max(top + tight[1], 0), min(left + tight[2], W), min(top + tight[3], H))


def paste_decoy(frame, x, y, want_w, source_dir, sources, rng):
    """A piece of floor from elsewhere pasted with a poop-shaped edge, so a
    pasted seam alone never means poop."""
    piece, _ = cutout(source_dir, sources, rng)
    piece = piece.rotate(rng.uniform(-35, 35), resample=Image.BICUBIC, expand=True)
    scale = want_w / max(piece.width * 0.6, 1)
    piece = piece.resize((max(int(piece.width * scale), 4), max(int(piece.height * scale), 4)), Image.LANCZOS)
    W, H = frame.size
    for _ in range(200):
        sx, sy = rng.uniform(0, 1), rng.uniform(0.3, 1)
        if inside(sx, sy, FLOOR) and abs(sx * W - x) > piece.width * 2:
            break
    sx, sy = int(sx * W), int(sy * H)
    floor = frame.crop((sx - piece.width // 2, sy - piece.height // 2,
                        sx - piece.width // 2 + piece.width, sy - piece.height // 2 + piece.height))
    frame.paste(floor, (x - piece.width // 2, y - piece.height // 2), piece.getchannel("A"))


def review_copy(frame, box, path, caption):
    small = frame.copy()
    small.thumbnail((768, 768))
    k = small.width / frame.width
    d = ImageDraw.Draw(small)
    if box:
        d.rectangle([v * k for v in box], outline=(255, 0, 0), width=2)
    d.rectangle((0, 0, small.width, 18), fill=(0, 0, 0))
    d.text((4, 3), caption[:110], fill=(255, 255, 255))
    small.save(path, quality=85)


def write_review_page(out):
    rows = list(csv.DictReader(open(out / "manifest.csv")))
    cards = "\n".join(
        f'<figure><img src="review/{r["name"]}.jpg" loading="lazy"><figcaption>{r["name"]} · {r["kind"]} · '
        f'{r["thing"]}</figcaption></figure>'
        for r in rows if r["status"] == "ok"
    )
    rejected = sum(r["status"] != "ok" for r in rows)
    (out / "review.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>Synthetic poop review</title>
<style>body{{font:14px system-ui;margin:16px;background:#111;color:#ddd}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}}
img{{width:100%}}figure{{margin:0}}</style>
<h1>Synthetic poop review</h1><p>{len(rows) - rejected} images, {rejected} rejected attempts (see manifest.csv).
Red box = labeled poop. No box = decoy, labeled clean.</p><main>{cards}</main>""")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=["paste", "openai", "gemini", "fake"], required=True)
    ap.add_argument("--count", type=int, required=True, help="images to make")
    ap.add_argument("--decoys", type=float, default=0.3, help="share of images that get a decoy")
    ap.add_argument("--frames", type=Path, default=HERE / "data/frames")
    ap.add_argument("--sources", type=Path, default=HERE / "poop_sources.json")
    ap.add_argument("--source-dir", type=Path, default=HERE / "data/sources")
    ap.add_argument("--out", type=Path, default=HERE / "data/out")
    ap.add_argument("--model", help="model id, default " + ", ".join(f"{k}: {v}" for k, v in DEFAULT_MODELS.items()))
    ap.add_argument("--quality", default="medium", help="OpenAI quality: low, medium or high")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--yes", action="store_true", help="needed for openai/gemini: confirms sending patches and paying")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    frames = sorted(args.frames.glob("*.jpg"))
    if not frames:
        sys.exit(f"no frames in {args.frames}")
    sources = json.loads(args.sources.read_text())
    api = args.provider in ("openai", "gemini")
    model = args.model or DEFAULT_MODELS.get(args.provider)
    key = None
    if api:
        key = load_keys().get("OPENAI_API_KEY" if args.provider == "openai" else "GEMINI_API_KEY")
        if not key:
            sys.exit(f"no API key for {args.provider}: set it in the environment or ~/.config/potty-synth/keys.env")
        if not args.yes:
            sys.exit(f"would send {args.count} floor patches to {args.provider} ({model}), each a paid call. "
                     "Add --yes to go ahead.")

    for sub in ("images", "labels", "review"):
        (args.out / sub).mkdir(parents=True, exist_ok=True)
    manifest = args.out / "manifest.csv"
    new_file = not manifest.exists()
    log = open(manifest, "a", newline="")
    writer = csv.writer(log)
    if new_file:
        writer.writerow(["name", "frame", "provider", "model", "kind", "thing", "box", "status"])

    made = 0
    attempt = 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    while made < args.count and attempt < args.count * 3:
        attempt += 1
        frame_path = rng.choice(frames)
        frame = Image.open(frame_path).convert("RGB")
        W, H = frame.size
        kind = "decoy" if rng.random() < args.decoys else "poop"
        thing = rng.choice(DECOYS if kind == "decoy" else POOP_SHAPES)
        name = f"{args.provider}-{stamp}-{attempt:04d}"
        box = None
        try:
            if args.provider == "paste":
                x, y, w, _ = pick_spot(rng, frame)
                if kind == "poop":
                    thing = "real poop cut-out"
                    box = paste_poop(frame, x, y, w, args.source_dir, sources, rng)
                else:
                    thing = "pasted floor patch"
                    paste_decoy(frame, x, y, w, args.source_dir, sources, rng)
            else:
                x, y, w, (px1, py1, px2, py2) = pick_spot(rng, frame, patch_factor=3)
                patch = frame.crop((px1, py1, px2, py2))
                side = px2 - px1
                k = API_SIZE / side
                prompt = prompt_for(kind, thing, is_gray(frame), w / side)
                if args.provider == "openai":
                    edited = call_openai(patch, prompt, int(w * 1.6 * k), key, model, args.quality)
                elif args.provider == "gemini":
                    edited = call_gemini(patch, prompt, key, model)
                else:
                    edited = call_fake(patch, kind, rng, w * 0.6 * k)
                new_patch, pbox = composite_edit(patch, edited, w)
                frame.paste(new_patch, (px1, py1))
                if kind == "poop":
                    box = (px1 + pbox[0], py1 + pbox[1], px1 + pbox[2], py1 + pbox[3])
        except Exception as exc:
            writer.writerow([name, frame_path.name, args.provider, model or "", kind, thing, "", f"rejected: {exc}"])
            log.flush()
            print(f"{name}: rejected, {exc}")
            continue

        frame.save(args.out / "images" / f"{name}.jpg", quality=92)
        label = ""
        if box:
            bx1, by1, bx2, by2 = box
            label = f"0 {(bx1 + bx2) / 2 / W:.6f} {(by1 + by2) / 2 / H:.6f} {(bx2 - bx1) / W:.6f} {(by2 - by1) / H:.6f}\n"
        (args.out / "labels" / f"{name}.txt").write_text(label)
        review_copy(frame, box, args.out / "review" / f"{name}.jpg", f"{name} {kind}: {thing}")
        writer.writerow([name, frame_path.name, args.provider, model or "", kind, thing, box or "", "ok"])
        log.flush()
        made += 1
        print(f"{name}: {kind} ({thing})", flush=True)

    log.close()
    write_review_page(args.out)
    print(f"made {made} images in {attempt} attempts; review: {args.out / 'review.html'}")


if __name__ == "__main__":
    main()
