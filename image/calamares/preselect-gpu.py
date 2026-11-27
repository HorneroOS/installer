#!/usr/bin/env python3
"""Apply a GPU probe to the live netinstall config (pre-selection only).

Reads probe-gpu.py JSON and /etc/calamares/modules/netinstall.conf,
sets `selected: true` on the open-source GPU leaf whose vendor the
probe detected (AMD/Intel; the user can still untick it on the
netinstall page). The NVIDIA proprietary item and every other group
are never touched. Fail-closed: any missing/invalid input leaves the
config byte-identical and exits non-zero so the caller can log it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

VENDOR_LEAF_PREFIX = {"amd": "GPU — AMD", "intel": "GPU — Intel"}


def preselect(netinstall: dict, vendors: list[str]) -> list[str]:
    normalized = {
        v.strip().lower()
        for v in vendors
        if isinstance(v, str) and v.strip().lower() in VENDOR_LEAF_PREFIX
    }
    changed: list[str] = []

    def walk(items):
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            yield item
            yield from walk(item.get("subgroups"))

    for item in walk(netinstall.get("groups")):
        name = str(item.get("name", ""))
        for vendor, prefix in VENDOR_LEAF_PREFIX.items():
            if name.startswith(prefix) and not item.get("subgroups"):
                want = vendor in normalized
                if (item.get("selected") is True) != want:
                    item["selected"] = want
                    changed.append(name)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--netinstall", type=Path, required=True)
    args = parser.parse_args()
    try:
        probe_doc = json.loads(args.probe.read_text(encoding="utf-8"))
        if not isinstance(probe_doc, dict):
            raise ValueError("probe JSON must be an object")
        raw_vendors = probe_doc.get("vendors")
        if raw_vendors is None:
            vendors = []
        elif isinstance(raw_vendors, list):
            vendors = raw_vendors
        else:
            raise ValueError("probe vendors must be a list")
        doc = yaml.safe_load(args.netinstall.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("groups"), list):
            raise ValueError("netinstall config must be a mapping with a groups list")
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"preselect-gpu: {error}", file=sys.stderr)
        return 1
    changed = preselect(doc, vendors)
    if changed:
        args.netinstall.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    print(f"preselect-gpu: pre-selected {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
