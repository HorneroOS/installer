"""Cancel during exec must stay disabled (installer#93).

Regression test: cancelling Calamares during the packages job did not
cancel the underlying pacman transaction — it completed after the UI
quit and the target booted as an installed system (preview32 QA run,
HorneroOS/qa `install-pairwise-negative/cancel-during-install` FAIL).
Until a deterministic mid-exec abort exists, `disable-cancel-during-exec`
must remain enabled so the UI never offers a cancellation it cannot
honour. Cancellation during the view steps stays available
(`disable-cancel: false`).
"""

from pathlib import Path

import yaml

CALAMARES = Path(__file__).resolve().parents[1] / "image" / "calamares"


def _settings() -> dict:
    return yaml.safe_load((CALAMARES / "settings.conf").read_text())


def test_cancel_disabled_during_exec_phase() -> None:
    settings = _settings()
    assert settings.get("disable-cancel-during-exec") is True, (
        "disable-cancel-during-exec must stay true: a mid-exec cancel does "
        "not stop the pacman transaction (installer#93)"
    )


def test_cancel_still_available_during_view_steps() -> None:
    settings = _settings()
    assert settings.get("disable-cancel") is False, (
        "cancelling before the exec phase (no disk writes yet) must remain possible"
    )
