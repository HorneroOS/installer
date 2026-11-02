#!/usr/bin/env python3
"""Resolve a composable selection into a deterministic plan (contract).

NOT wired into settings.conf yet: the pinned catalogue does not ship
kernels/bootloaders/capabilities maps and Calamares 3.4.3 GlobalStorage
keys for instanced packagechoosers are unverified. Wiring this as a
Calamares job before those land would risk an unbootable install.
The CLI below is the tested contract the job will call:

    resolve-installation.py --catalogue catalogue.yaml \
        --selection selection.json --output plan.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

try:
    import installation_plan
except ImportError:  # when copied beside the scripts dir in the ISO
    installation_plan = None  # type: ignore[assignment]


def resolve(catalogue: dict, selection: dict) -> dict:
    if installation_plan is None:
        raise RuntimeError("installation_plan module is unavailable")
    return installation_plan.build_plan(catalogue, selection)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    import yaml

    catalogue = yaml.safe_load(args.catalogue.read_text(encoding="utf-8"))
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    try:
        plan = resolve(catalogue, selection)
    except ValueError as error:
        print(f"resolve-installation: {error}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(installation_plan.summary_text(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
