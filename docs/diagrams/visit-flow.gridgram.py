from gridgram import Diagram

# Rows are the stages of one visit, top to bottom. Columns are the three
# verdicts of the poop model; the main line runs down the middle column.

d = Diagram(canvas="readme", cols=[1, 1, 1], rows=6, row_h=70, row_gap=36, col_gap=50,
            title="One dog visit, from sighting to rinse")
seen = d.box(1, 0, "Dog in view", "Frigate on the NPU opens a visit", "live")
gone = d.box(1, 1, "Dog gone, patio still", "no dog for 20 s and no motion,\nor 3 minutes at most", "live")
photo = d.box(1, 2, "Check photo", "floor cropped to 640 px,\nfull frame kept too", "live")
model = d.box(0, 3, "Poop model", "YOLO11n classifier, ONNX on the CPU: poop probability", "built", colspan=3)
poop = d.box(0, 4, "Poop, 0.5 or more", "phone alert and Alexa;\nhose stays off", "built")
clean = d.box(1, 4, "Clean, 0.05 or less", "rinse right away", "built")
ask = d.box(2, 4, "Not sure, or no model", "phone: Clean or Poop?", "live")
rinse = d.box(1, 5, "Rinse", "only on an empty patio\n(next diagram)", "live")
answer = d.box(2, 5, "Your answer", "labels the photo; Clean for the\nnewest one, within 15 min, rinses", "live")

d.arrow(seen, gone)
d.arrow(gone, photo)
d.arrow(photo, model)
d.arrow(model, poop)
d.arrow(model, clean)
d.arrow(model, ask)
d.arrow(clean, rinse)
d.arrow(ask, answer)
d.arrow(answer, rinse)
d.legend({"live": "Running today", "built": "Built, waits for a trained model"})
d.save("visit-flow.drawio")
