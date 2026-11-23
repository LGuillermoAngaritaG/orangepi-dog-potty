#!/usr/bin/env bash

# Looks for silently damaged files on the system disk. Reads only. Written after
# an unbranded microSD card returned stale data without any I/O error.
#  1. Every Docker image layer is re-read and its sha256 compared with its name.
#  2. Every file installed from a Debian package is compared with the package's checksum.
#  3. Every Python bytecode file written inside the Home Assistant container is test-loaded.

export LC_ALL=C
echo "START $(date +%T)"

echo "== 1. Docker image layers"
for img in $(docker images --format '{{.Repository}}:{{.Tag}}'); do
  docker save "$img" | python3 -c '
import sys, tarfile, hashlib
ok = bad = 0
t = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
for m in t:
    if m.isfile() and m.name.startswith("blobs/sha256/"):
        h = hashlib.sha256(); f = t.extractfile(m)
        while True:
            b = f.read(1 << 20)
            if not b: break
            h.update(b)
        if h.hexdigest() == m.name.rsplit("/", 1)[1]: ok += 1
        else: bad += 1; print("   DAMAGED blob", m.name[13:25], m.size, "bytes")
print("   blobs intact:", ok, "damaged:", bad)
' 2>&1 | sed "s|^|$img |"
done

echo "== 2. Debian package files"
dpkg -V 2>/dev/null | grep -vE "^\?\?5\?\?\?\?\?\? c " | head -40
echo "   packaged files that differ, config files excluded: $(dpkg -V 2>/dev/null | grep -vcE " c /")"

echo "== 3. Python bytecode written by Home Assistant"
docker exec -i homeassistant python - <<'PY'
import marshal, os
bad = []; n = 0
for root in ("/usr/local/lib/python3.14", "/usr/src/homeassistant", "/config"):
    for d, _, files in os.walk(root):
        for f in files:
            if f.endswith(".pyc"):
                n += 1
                try:
                    data = open(os.path.join(d, f), "rb").read()
                    marshal.loads(data[16:])
                except Exception:
                    bad.append(os.path.join(d, f))
print("   bytecode files checked:", n, "damaged:", len(bad))
for b in bad[:20]: print("   DAMAGED", b)
PY
echo "DONE $(date +%T)"
