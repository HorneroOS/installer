"""Regression tests for fresh Arch cloud-image ISO builder fixes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_ISO_SCRIPT = ROOT / "scripts" / "build-iso.sh"
BUILD_REPO_SCRIPT = ROOT / "scripts" / "build-package-repository.sh"


def test_builder_user_created_before_first_runuser() -> None:
    """builder must exist before importing the release GPG key on fresh cloud images."""
    script = BUILD_REPO_SCRIPT.read_text(encoding="utf-8")
    useradd_cmd = "getent passwd builder >/dev/null || useradd --create-home --shell /bin/bash builder"
    gpg_import_cmd = 'runuser -u builder -- gpg --batch --quiet --import "$release_pubkey"'

    assert useradd_cmd in script
    assert gpg_import_cmd in script

    useradd_pos = script.index(useradd_cmd)
    first_runuser_pos = script.index("runuser -u builder")
    gpg_import_pos = script.index(gpg_import_cmd)

    assert useradd_pos < first_runuser_pos
    assert useradd_pos < gpg_import_pos


def test_openssl_3_removed_before_snapshot_downgrade() -> None:
    """openssl-3 on OpenSSL 4.x cloud images must be removed before -Syyuu downgrade."""
    script = BUILD_REPO_SCRIPT.read_text(encoding="utf-8")
    check_cmd = "pacman -Q openssl-3 >/dev/null 2>&1"
    remove_cmd = "pacman -Rdd --noconfirm openssl-3"
    downgrade_cmd = 'pacman --config "$pacman_conf" -Syyuu --noconfirm'

    assert check_cmd in script
    assert remove_cmd in script
    assert downgrade_cmd in script

    check_pos = script.index(check_cmd)
    remove_pos = script.index(remove_cmd)
    downgrade_pos = script.index(downgrade_cmd)

    assert check_pos < remove_pos < downgrade_pos


def test_build_iso_exports_pythondontwritebytecode_before_python() -> None:
    """build-iso.sh must disable bytecode caching before any python3 invocation."""
    script = BUILD_ISO_SCRIPT.read_text(encoding="utf-8")
    export_stmt = "export PYTHONDONTWRITEBYTECODE=1"

    assert export_stmt in script
    export_pos = script.index(export_stmt)
    first_python_pos = script.index("python3")

    assert export_pos < first_python_pos


def test_iso_and_repo_build_scripts_syntax_and_shellcheck() -> None:
    """Both build scripts must pass bash -n and shellcheck."""
    for script in (BUILD_ISO_SCRIPT, BUILD_REPO_SCRIPT):
        syntax = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert syntax.returncode == 0, f"bash -n failed on {script}: {syntax.stderr}"

    shellcheck = shutil.which("shellcheck")
    if shellcheck:
        for script in (BUILD_ISO_SCRIPT, BUILD_REPO_SCRIPT):
            lint = subprocess.run(
                [shellcheck, str(script)],
                check=False,
                capture_output=True,
                text=True,
            )
            assert lint.returncode == 0, (
                f"shellcheck failed on {script}:\n{lint.stdout}\n{lint.stderr}"
            )
