"""The ISO build gate that stops pre-Signal images (installer#101)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_signal_lock", ROOT / "scripts/check-signal-lock.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SIGNAL_LOCK = {"aur": {"packages": {
    "hornero-config": {"version": "0.4.0-1"},
    "hornero-shell": {"version": "1.3.0-2"},
    "hornero-greeter": {"version": "1.1.0-1"},
    "horneroctl-bin": {"version": "0.2.0_preview46-1"},
    "libcava": {"version": "1.0.0-1"},
}}}


def test_version_order_is_numeric_not_lexical():
    assert gate.version_key("1.10.0-1") > gate.version_key("1.3.0-1")
    assert gate.version_key("0.2.0_preview46-1") > gate.version_key("0.2.0_preview40-1")


def test_signal_lock_passes():
    assert gate.problems(SIGNAL_LOCK) == []


def test_stale_and_retired_pins_fail():
    stale = {"aur": {"packages": {
        **SIGNAL_LOCK["aur"]["packages"],
        "hornero-shell": {"version": "1.2.60-1"},
        "python-materialyoucolor": {"version": "3.0.2-1"},
    }}}
    found = gate.problems(stale)
    assert any("hornero-shell 1.2.60-1" in line for line in found)
    assert any("python-materialyoucolor" in line for line in found)


def test_missing_package_fails():
    lock = {"aur": {"packages": {"libcava": {"version": "1.0.0-1"}}}}
    assert len(gate.problems(lock)) == len(gate.SIGNAL_FLOOR)


def test_build_script_runs_the_gate_with_an_explicit_override():
    script = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert "check-signal-lock.py" in script
    assert "HORNEROS_ALLOW_PRE_SIGNAL_LOCK" in script
