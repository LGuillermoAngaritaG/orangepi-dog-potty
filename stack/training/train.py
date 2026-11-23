"""Trains the poop classifier and exports model.onnx for the poop-checker.

Run on a PC or in Google Colab, not on the Orange Pi:

    pip install ultralytics onnx
    python train.py path/to/dataset

The dataset folder holds the clean/ and poop/ folders copied from
poop-checker/data/dataset on the Pi. The script writes model.onnx next to
where you run it and prints how the potty thresholds would behave.
"""

import random
import shutil
import sys
import tempfile
from pathlib import Path

from ultralytics import YOLO

IMG_SIZE = 320
VAL_SHARE = 0.2
MIN_POOP = 20

# Same values as potty_visit_end in dog_potty.yaml.
POOP_ALERT = 0.5
RINSE_MAX = 0.05


def split(src, dst):
    random.seed(0)
    val_files = {}
    for label in ("clean", "poop"):
        files = sorted((src / label).glob("*.jpg"))
        random.shuffle(files)
        n_val = max(1, int(len(files) * VAL_SHARE))
        val_files[label] = files[:n_val]
        for i, f in enumerate(files):
            out = dst / ("val" if i < n_val else "train") / label
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, out / f.name)
    return val_files


def report(model, val_files):
    poop_index = list(model.names.values()).index("poop")
    for label, files in val_files.items():
        probs = [
            float(model.predict(str(f), imgsz=IMG_SIZE, verbose=False)[0].probs.data[poop_index])
            for f in files
        ]
        rinsed = sum(p <= RINSE_MAX for p in probs)
        alerted = sum(p >= POOP_ALERT for p in probs)
        asked = len(probs) - rinsed - alerted
        print(f"{label:5} photos: {len(probs):3}  rinsed {rinsed:3}  alerted {alerted:3}  asked {asked:3}")
    print("A poop photo in the 'rinsed' column means the hose would spray poop. Keep that at 0.")


def main():
    src = Path(sys.argv[1])
    n_poop = len(list((src / "poop").glob("*.jpg")))
    if n_poop < MIN_POOP:
        sys.exit(f"Only {n_poop} poop photos. Collect at least {MIN_POOP} before training.")

    work = Path(tempfile.mkdtemp())
    val_files = split(src, work)

    # Poop fills a small part of the photo. Random erasing and aggressive crops
    # can cut it out while the label still says poop, so both are turned down.
    trainer = YOLO("yolo11n-cls.pt")
    trainer.train(
        data=str(work),
        imgsz=IMG_SIZE,
        epochs=60,
        erasing=0.0,
        scale=0.1,
        fliplr=0.5,
        flipud=0.5,
        project=str(work / "runs"),
        name="poop",
    )

    best = YOLO(trainer.trainer.best)
    onnx_path = best.export(format="onnx", imgsz=IMG_SIZE)
    shutil.copy(onnx_path, "model.onnx")
    print("Wrote model.onnx")
    report(best, val_files)


if __name__ == "__main__":
    main()
