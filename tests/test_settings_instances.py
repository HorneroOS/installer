"""Every sequenced Calamares `module@instance` must be declared.

Regression test: `shellprocess@recovery` was added to the exec sequence
without an `instances:` entry, so Calamares fell back to its bundled
example shellprocess config (`/usr/local/bin/slowloris`) and the install
failed mid-exec in the recovery-candidate VM proof.
"""

from pathlib import Path

import yaml

CALAMARES = Path(__file__).resolve().parents[1] / "image" / "calamares"


def _settings() -> dict:
    return yaml.safe_load((CALAMARES / "settings.conf").read_text())


def test_sequenced_instances_are_declared_with_existing_configs() -> None:
    settings = _settings()
    instances = {
        (entry["module"], entry["id"]): entry["config"]
        for entry in settings.get("instances", [])
    }
    sequenced = [
        step
        for phase in settings["sequence"]
        for step in next(iter(phase.values()))
    ]
    instanced = [step for step in sequenced if "@" in step]
    assert instanced, "expected instanced modules in the sequence"
    for step in instanced:
        module, instance = step.split("@", 1)
        assert (module, instance) in instances, f"{step} not declared in instances:"
        config = CALAMARES / "modules" / instances[(module, instance)]
        assert config.is_file(), f"{step} config {config.name} missing"


def test_recovery_instance_points_at_recovery_config() -> None:
    settings = _settings()
    instances = {
        (entry["module"], entry["id"]): entry["config"]
        for entry in settings.get("instances", [])
    }
    assert instances[("shellprocess", "recovery")] == "shellprocess-recovery.conf"
