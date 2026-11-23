import gridgram
from gridgram import Diagram

# The left column is the rinse itself, top to bottom. The right column holds
# what stops it: the two skips, and the three safety nets that close the hose.

gridgram.STATUS["guard"] = ("#FBE4E4", "#B42318")
d = Diagram(canvas="readme", cols=[1.15, 1], rows=7, row_h=64, row_gap=26, col_gap=90,
            title="Rinse: when the hose may open, and what closes it")
d.header(0, "The rinse")
d.header(1, "Skips and safety nets")
asked = d.box(0, 0, "Rinse asked", "model said clean, a Clean answer,\nor the Rinse now button", "live")
paused = d.box(0, 1, "Hose paused?", "Settings switch; Rinse now ignores it", "live")
clear = d.box(0, 2, "Patio clear?", "no dog, no person, no motion;\nwaits up to 5 minutes", "live")
opened = d.box(0, 3, "Hose open", "for the rinse length, 30 s;\nnoted in History", "live", rowspan=3, valign="middle")
closed = d.box(0, 6, "Hose closed", "History shows Rinsed", "live")
skip1 = d.box(1, 1, "Skipped", "noted, phone told", "plain")
skip2 = d.box(1, 2, "Skipped", "noted, phone told", "plain")
walkin = d.box(1, 3, "Walk-in stop", "dog or person appears:\nclosed at once", "guard")
safety = d.box(1, 4, "Safety close", "any open hose, Alexa too:\nclosed after 2 minutes", "guard")
timer = d.box(1, 5, "Timer's own limit", "the valve closes itself after\n30 s, even with no Pi or cloud", "guard")

d.arrow(asked, paused)
d.arrow(paused, clear, label="no")
d.arrow(paused, skip1, label="yes")
d.arrow(clear, opened, label="yes")
d.arrow(clear, skip2, label="no")
d.arrow(opened, closed)
d.arrow(walkin, opened, dashed=True)
d.arrow(safety, opened, dashed=True)
d.arrow(timer, opened, dashed=True)
d.legend({"live": "Rinse steps", "guard": "Closes the hose on its own", "plain": "Rinse skipped"})
d.save("rinse-safety.drawio")
