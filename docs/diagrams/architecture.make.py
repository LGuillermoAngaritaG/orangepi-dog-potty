"""Writes architecture.drawio. Hand-placed coordinates (drawio-skill), so edit
the numbers here and run again, or open the .drawio in draw.io and edit there."""
import html

cells, n = [], [1]
def nid():
    n[0] += 1
    return f"c{n[0]}"

BLUE = "fillColor=#dae8fc;strokeColor=#6c8ebf;"
GREEN = "fillColor=#d5e8d4;strokeColor=#82b366;"
YELLOW = "fillColor=#fff2cc;strokeColor=#d6b656;"
ORANGE = "fillColor=#ffe6cc;strokeColor=#d79b00;"
GREY = "fillColor=#f5f5f5;strokeColor=#666666;"
PURPLE = "fillColor=#e1d5e7;strokeColor=#9673a6;"

def label(title, sub=None):
    v = f"<b>{html.escape(title)}</b>"
    if sub:
        v += '<br><font style="font-size:11px" color="#444444">' + "<br>".join(html.escape(s) for s in sub.split("\n")) + "</font>"
    return v

def box(x, y, w, h, title, sub, color, parent="1", extra=""):
    i = nid()
    cells.append(f'<mxCell id="{i}" value="{html.escape(label(title, sub))}" style="rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=14;{color}{extra}" vertex="1" parent="{parent}"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i

def text(x, y, w, h, value, size=12, extra=""):
    i = nid()
    cells.append(f'<mxCell id="{i}" value="{html.escape(value)}" style="text;html=1;whiteSpace=wrap;fontSize={size};{extra}" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

def edge(s, t, lab="", ex=None, en=None, dashed=False, both=False, lx=0, ly=0, pts=None):
    i = nid()
    st = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#333333;strokeWidth=1.5;endArrow=block;endFill=1;fontSize=11;labelBackgroundColor=#ffffff;"
    if ex: st += f"exitX={ex[0]};exitY={ex[1]};exitDx=0;exitDy=0;"
    if en: st += f"entryX={en[0]};entryY={en[1]};entryDx=0;entryDy=0;"
    if dashed: st += "dashed=1;"
    if both: st += "startArrow=block;startFill=1;"
    geo = '<mxGeometry relative="1" as="geometry">'
    if lx or ly: geo = f'<mxGeometry x="{lx}" y="{ly}" relative="1" as="geometry"><mxPoint as="offset"/>'
    if pts: geo += "<Array as=\"points\">" + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in pts) + "</Array>"
    geo += "</mxGeometry>"
    cells.append(f'<mxCell id="{i}" value="{html.escape(lab)}" style="{st}" edge="1" parent="1" source="{s}" target="{t}">{geo}</mxCell>')

text(40, 10, 1600, 30, "<b>Dog potty monitor on an Orange Pi 5: architecture</b>", 20)

# Phone and voice, top row.
phone = box(820, 60, 260, 80, "iPhone, Home Assistant app", "notification, Potty page,\nClean / Poop answers", PURPLE)
echo = box(1440, 60, 240, 80, "Amazon Echo", "\"open the faucet\"\nby voice", PURPLE)

# The Pi.
pi = nid()
cells.append(f'<mxCell id="{pi}" value="{html.escape("<b>Orange Pi 5</b> (RK3588S, 8 GB RAM, 6 TOPS NPU) · Armbian · Docker Compose, host network<br><font style=\"font-size:12px\" color=\"#555555\">System on a USB 3 SSD, started from a microSD card (docs/hardware.md)</font>")}" style="rounded=1;whiteSpace=wrap;html=1;arcSize=3;fontSize=14;verticalAlign=top;align=left;spacingLeft=12;spacingTop=6;fillColor=#f8f9fb;strokeColor=#4a6fa5;strokeWidth=2;container=1;pointerEvents=0;" vertex="1" parent="1"><mxGeometry x="40" y="190" width="1300" height="440" as="geometry"/></mxCell>')
frigate = box(40, 80, 240, 110, "Frigate 0.18", "dog, person and motion\nYOLOv9-tiny on the NPU,\nabout 40 ms per frame", BLUE, pi)
mqtt = box(440, 80, 180, 110, "Mosquitto", "MQTT broker,\nlocal only", BLUE, pi)
ha = box(780, 80, 260, 110, "Home Assistant", "dog_potty package: visit,\nrinse, safety, answers\nPotty page and History card", BLUE, pi)
go2rtc = box(40, 280, 240, 110, "go2rtc (inside Frigate)", "one camera connection,\nrestreamed on :8554", BLUE, pi)
checker = box(780, 280, 260, 110, "Poop checker", "Python, :8099 local only\ncrops the floor, ONNX model\non the CPU, keeps photos", GREEN, pi)
adguard = box(1090, 280, 190, 110, "AdGuard Home", "ad blocking DNS\nfor the whole house", ORANGE, pi)

# Hose chain, right column.
tuya = box(1440, 270, 240, 110, "Tuya cloud", "Smart Life account", GREY)
gateway = box(1440, 470, 240, 110, "Sub-GHz gateway", "Wi-Fi to RF bridge", YELLOW)
timer = box(1440, 700, 240, 100, "RF water timer", "the hose valve, with its\nown shut-off time", YELLOW)

# Home network, bottom row.
camera = box(80, 700, 240, 100, "Tapo camera", "looks at the patio floor", YELLOW)
minipc = box(820, 700, 260, 100, "PC", "trains the model, makes\nsynthetic images, deploys", GREY)
router = box(1130, 700, 190, 100, "Router", "hands out the Pi as DNS", GREY)

edge(camera, go2rtc, "RTSP", ex=(0.5, 0), en=(0.5, 1))
edge(go2rtc, frigate, "sub stream, 5 fps", ex=(0.5, 0), en=(0.5, 1))
edge(frigate, mqtt, "dog / person / motion", ex=(1, 0.5), en=(0, 0.5), ly=-14)
edge(mqtt, ha, "sensors", ex=(1, 0.5), en=(0, 0.5), ly=-14)
edge(ha, checker, "check, label, note,\nhistory (HTTP)", ex=(0.5, 1), en=(0.5, 0), lx=0, ly=0)
edge(checker, go2rtc, "one frame per check", ex=(0, 0.5), en=(1, 0.5), ly=-14)
edge(ha, tuya, "open / close", ex=(1, 0.5), en=(0, 0.5), ly=-14)
edge(phone, ha, "push / answers", ex=(0.5, 1), en=(0.5, 0), both=True)
edge(echo, tuya, "Smart Life skill", ex=(0.5, 1), en=(0.5, 0))
edge(tuya, gateway, "", ex=(0.5, 1), en=(0.5, 0))
edge(gateway, timer, "RF", ex=(0.5, 1), en=(0.5, 0))
edge(minipc, checker, "model.onnx, deploy.sh (SSH)", ex=(0.5, 0), en=(0.5, 1), dashed=True)
edge(router, adguard, "DNS", ex=(0.5, 0), en=(0.5, 1))

xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="drawio-skill" version="26.0.0"><diagram name="Architecture" id="arch">'
       '<mxGraphModel dx="1600" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" math="0" background="#ffffff">'
       '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>\n")
open("architecture.drawio", "w", encoding="utf-8").write(xml)
print("wrote architecture.drawio", len(cells), "cells")
