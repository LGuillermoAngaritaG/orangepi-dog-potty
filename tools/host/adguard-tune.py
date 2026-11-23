#!/usr/bin/env python3
"""Applies the agreed AdGuard Home improvements to AdGuardHome.yaml.

Run on the Pi as root while the adguardhome container is stopped:
    python3 adguard-tune.py <stack folder>/adguard/conf/AdGuardHome.yaml

Changes:
  - blocklist: adds "OISD Blocklist Big" next to the default AdGuard DNS filter
  - upstream: Quad9 filtered plus Cloudflare security, instead of Quad9 unfiltered
  - plain fallback servers, a larger cache, and optimistic caching
  - query log kept 7 days instead of 90

Each edit replaces an exact piece of the stock configuration. A piece that is
already in its new form is skipped, so running this twice is harmless. If a
piece is in neither form the script stops without writing anything.
"""

import sys

import yaml

EDITS = [
    (
        "upstream servers",
        "  upstream_dns:\n    - https://dns10.quad9.net/dns-query\n",
        "  upstream_dns:\n    - https://dns.quad9.net/dns-query\n    - https://security.cloudflare-dns.com/dns-query\n",
    ),
    (
        "bootstrap servers",
        "  bootstrap_dns:\n    - 9.9.9.10\n    - 149.112.112.10\n    - 2620:fe::10\n    - 2620:fe::fe:10\n",
        "  bootstrap_dns:\n    - 9.9.9.9\n    - 149.112.112.112\n    - 1.1.1.2\n    - 1.0.0.2\n",
    ),
    (
        "fallback servers",
        "  fallback_dns: []\n",
        "  fallback_dns:\n    - 9.9.9.9\n    - 1.1.1.2\n",
    ),
    ("cache size", "  cache_size: 4194304\n", "  cache_size: 16777216\n"),
    ("optimistic cache", "  cache_optimistic: false\n", "  cache_optimistic: true\n"),
    ("query log retention", "  interval: 90d\n", "  interval: 168h\n"),
    (
        "OISD blocklist",
        "    name: AdAway Default Blocklist\n    id: 2\nwhitelist_filters:",
        "    name: AdAway Default Blocklist\n    id: 2\n"
        "  - enabled: true\n"
        "    url: https://adguardteam.github.io/HostlistsRegistry/assets/filter_27.txt\n"
        "    name: OISD Blocklist Big\n"
        "    id: 27\n"
        "whitelist_filters:",
    ),
]


def main(path):
    text = open(path).read()
    for name, old, new in EDITS:
        if new in text:
            print(f"already set: {name}")
        elif text.count(old) == 1:
            text = text.replace(old, new)
            print(f"changed:     {name}")
        else:
            sys.exit(f"STOP: '{name}' is not in its expected form; nothing written.")

    # The result must still be valid YAML with the values we meant to set.
    conf = yaml.safe_load(text)
    assert len(conf["dns"]["upstream_dns"]) == 2
    assert conf["dns"]["cache_optimistic"] is True
    assert any(f["id"] == 27 and f["enabled"] for f in conf["filters"])
    assert conf["users"], "admin account missing"

    open(path, "w").write(text)
    print("written")


if __name__ == "__main__":
    main(sys.argv[1])
