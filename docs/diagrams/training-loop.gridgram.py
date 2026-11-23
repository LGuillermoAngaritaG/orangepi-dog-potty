from gridgram import Diagram

# Columns are the stages from camera to model. The top row is real photos
# labeled by hand, the bottom row synthetic images made on a PC.

d = Diagram(canvas="readme", cols=[1, 1, 1, 1], rows=2, row_h=80, row_gap=30, col_gap=46,
            title="Training data: from answers to a model")
for col, name in enumerate(["Collect", "Label", "Train", "Use"]):
    d.header(col, name)
photos = d.box(0, 0, "Check photos", "one per visit: crop\nand full frame", "live")
frames = d.box(0, 1, "Empty patio frames", "every 30 min,\nday and night", "live")
answers = d.box(1, 0, "Your answers", "Clean or Poop, from the\nphone or History tab", "live")
synth = d.box(1, 1, "Synthetic images", "real poop cut-outs, or an\nimage model on a floor patch", "built")
train = d.box(2, 0, "train.py on a PC", "YOLO11n classifier, 320 px;\nneeds 20 poop photos", "built", rowspan=2)
model = d.box(3, 0, "model.onnx", "copied to the Pi, used\nfrom the next check", "prop", rowspan=2)

d.arrow(photos, answers)
d.arrow(frames, synth)
d.arrow(answers, train, label="dataset/")
d.arrow(synth, train, dashed=True, label="not yet")
d.arrow(train, model)
d.legend({"live": "Running", "built": "Built and tested", "prop": "Not trained yet"})
d.save("training-loop.drawio")
