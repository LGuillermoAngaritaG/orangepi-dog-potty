# Synthetic training images

`make_synthetic.py` adds poop, or a harmless decoy, to real frames of the empty patio and
writes YOLO-format images and labels. It runs on a PC (Python 3, `pip install pillow requests`).

```bash
python3 make_synthetic.py --provider paste --count 30
python3 make_synthetic.py --provider openai --count 10 --yes
```

| Provider | What it does | Cost |
| --- | --- | --- |
| `paste` | Real poop cut-outs from labeled photos, scaled by distance, matched in brightness, grayscale at night | Free, local |
| `openai` | Image edit API on a square floor patch around the spot | Paid, needs `--yes` |
| `gemini` | Gemini image model on the same patch | Paid, needs `--yes` |
| `fake` | A dark blob, to test the compositing | Free |

Inputs, all under `data/` (not in git):

- `data/frames/`: empty-patio frames, saved on the Pi by the poop checker every 30 minutes
  (`poop-checker/data/frames/`). Check them for the dog before use.
- `data/sources/` and `poop_sources.json`: for `paste`, the photos with real poop and a box
  around it. See `poop_sources.example.json`.

The floor outline (`FLOOR`) and the size-by-distance constants at the top of the script are
fitted to one camera view. Change them for another camera.

API keys come from `OPENAI_API_KEY` / `GEMINI_API_KEY` or `~/.config/potty-synth/keys.env`,
and are never printed. Only the floor patch is sent, never a whole frame.

Output in `data/out/`: `images/`, `labels/`, `review/` (small copies with the box drawn),
`manifest.csv`, and `review.html` to check everything by eye.
