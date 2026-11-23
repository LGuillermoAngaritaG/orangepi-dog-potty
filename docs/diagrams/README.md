# Diagrams

Each diagram is an editable draw.io file with a PNG export next to it.

| File | Made with |
| --- | --- |
| `architecture.drawio` | `architecture.make.py`, hand-placed coordinates |
| `visit-flow.drawio`, `rinse-safety.drawio`, `training-loop.drawio`, `storage-journey.drawio` | `*.gridgram.py`, placed on a grid by `gridgram.py` |

To change one: edit the script and run it with Python 3 from this folder, or open the
`.drawio` file in [draw.io](https://www.drawio.com) and edit it there (shapes stay connected).
Once a file has been saved in draw.io, edit that file rather than running the script again,
which would overwrite the manual edits (`gridgram.py` refuses to).

To export a PNG: in draw.io, File > Export as > PNG, or with the desktop app,
`drawio -x -f png -s 2 -o name.png name.drawio`.
