#!/usr/bin/env python3
"""Lists what the potty camera saw, to find visits the flow missed. Reads only.

Run on the Pi:  python3 visit-report.py [stack folder] [days]
                (defaults: ~/orangepi-home, 2 days)

Prints every motion episode with how many dog and person sightings it had, then
Frigate's dog events and the checks. A long episode with no dog is worth a look
in Frigate's snapshots: if it was the dog, she was not recognized.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime

stack = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/orangepi-home")
days = float(sys.argv[2]) if len(sys.argv) > 2 else 2
since = time.time() - days * 86400


def t(ts):
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


db = sqlite3.connect(f"file:{stack}/homeassistant/home-assistant_v2.db?mode=ro", uri=True)


def changes(entity):
    return db.execute(
        "select s.state, s.last_updated_ts from states s join states_meta m"
        " on s.metadata_id = m.metadata_id where m.entity_id = ? and s.last_updated_ts > ?"
        " order by s.last_updated_ts", (entity, since)).fetchall()


def turned_on(entity):
    return [ts for state, ts in changes(entity) if state == "on"]


episodes, start = [], None
for state, ts in changes("binary_sensor.potty_cam_motion"):
    if state == "on" and start is None:
        start = ts
    elif state != "on" and start is not None:
        episodes.append((start, ts))
        start = None

dogs = turned_on("binary_sensor.potty_cam_dog_occupancy")
people = turned_on("binary_sensor.potty_cam_person_occupancy")

print("Motion episodes (Frigate adds 20 s after the last movement)")
for a, b in episodes:
    d = sum(a - 5 <= x <= b for x in dogs)
    p = sum(a - 5 <= x <= b for x in people)
    note = "" if d or p or b - a < 25 else "   <- no dog, no person"
    print(f"  {t(a)}  {b - a:5.0f} s  dog {d}  person {p}{note}")

print("\nFrigate dog events")
url = f"http://127.0.0.1:5000/api/events?label=dog&limit=200&after={since}"
for e in sorted(json.load(urllib.request.urlopen(url)), key=lambda e: e["start_time"]):
    print(f"  {t(e['start_time'])}  top score {(e.get('data') or {}).get('top_score', 0):.2f}  id {e['id']}")

print("\nChecks")
with open(f"{stack}/poop-checker/data/history.jsonl") as f:
    for line in f:
        r = json.loads(line)
        if r.get("event") == "check":
            ts = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").timestamp()
            if ts > since:
                print(f"  {r['time']}  {r['id']}")
