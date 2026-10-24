"""Regression tests for cleanup after Calamares package transactions."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLEANUP_PACKAGE_SOURCE = (
    ROOT
    / "image/archiso/airootfs/usr/local/lib/hornero-installer/cleanup-package-source.py"
)
CLEANUP_TARGETS = (
    ROOT
    / "image/archiso/airootfs/usr/local/lib/hornero-installer/cleanup-calamares-targets.py"
)
TEMP_INCLUDES = (
    "Include = /etc/pacman.d/hornero-installer.conf",
    "Include = /etc/pacman.d/hornero-installer-mirrorlist.conf",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_calamares_target(temp_root: Path) -> Path:
    target = temp_root / "calamares-root-test"
    (target / "etc/pacman.d").mkdir(parents=True)
    (target / "usr/lib/hornero-installer").mkdir(parents=True)
    (target / "usr/share/hornero-installer/repo").mkdir(parents=True)
    (target / "etc/pacman.conf").write_text(
        "[options]\nArchitecture = auto\n"
        "[core]\n"
        f"{TEMP_INCLUDES[0]}\n"
        "[extra]\n"
        f"{TEMP_INCLUDES[1]}\n",
        encoding="utf-8",
    )
    for include in ("hornero-installer.conf", "hornero-installer-mirrorlist.conf"):
        (target / "etc/pacman.d" / include).write_text("# temporary\n", encoding="utf-8")
    (target / "usr/lib/hornero-installer/cleanup-package-source.py").write_text(
        "# installed cleanup helper\n", encoding="utf-8"
    )
    return target


def test_cleanup_is_configured_for_package_failure_and_cancellation() -> None:
    settings = yaml.safe_load(
        (ROOT / "image/calamares/settings.conf").read_text(encoding="utf-8")
    )
    modules = settings["sequence"][1]["exec"]
    assert "packages" in modules
    assert modules.index("packages") < modules.index("shellprocess@resolver-cleanup")
    assert modules.index("shellprocess@resolver-cleanup") < modules.index("shellprocess@cleanup")

    resolver_cleanup = yaml.safe_load(
        (ROOT / "image/calamares/modules/shellprocess-resolver-cleanup.conf").read_text(
            encoding="utf-8"
        )
    )
    package_cleanup = yaml.safe_load(
        (ROOT / "image/calamares/modules/shellprocess-cleanup.conf").read_text(
            encoding="utf-8"
        )
    )
    assert resolver_cleanup["emergency"] is True
    assert package_cleanup["emergency"] is True

    runner = (ROOT / "image/archiso/airootfs/usr/local/bin/hornero-installer-run").read_text(
        encoding="utf-8"
    )
    assert "cleanup-calamares-targets.py" in runner
    assert runner.index("/usr/bin/calamares -D6") < runner.index("cleanup-calamares-targets.py")


def test_post_exit_cleanup_restores_target_after_package_failure(tmp_path: Path) -> None:
    target = make_calamares_target(tmp_path)
    package_cleanup = load_module("cleanup_package_source", CLEANUP_PACKAGE_SOURCE)
    calamares_cleanup = load_module("cleanup_calamares_targets", CLEANUP_TARGETS)
    unmounted: list[Path] = []

    def unmount(path: Path) -> None:
        unmounted.append(path)

    # A failed package transaction still exits through the installer runner's
    # unconditional post-exit cleanup. Model the failed stage, then run the
    # same target cleanup implementation without invoking privileged umount.
    try:
        try:
            raise RuntimeError("simulated pacman failure")
        finally:
            failures, cleaned = calamares_cleanup.cleanup_targets(
                [target / "etc/pacman.conf"],
                package_cleanup,
                unmount,
                temp_root=tmp_path,
                owner_uid=os.geteuid(),
            )
    except RuntimeError as error:
        assert str(error) == "simulated pacman failure"

    assert failures == []
    assert cleaned == [target]
    restored = (target / "etc/pacman.conf").read_text(encoding="utf-8")
    assert all(include not in restored for include in TEMP_INCLUDES)
    assert restored.count("Include = /etc/pacman.d/mirrorlist") == 2
    assert not (target / "etc/pacman.d/hornero-installer.conf").exists()
    assert not (target / "etc/pacman.d/hornero-installer-mirrorlist.conf").exists()
    assert target / "etc/hosts" in unmounted
    assert target / "etc/resolv.conf" in unmounted
    assert target in unmounted


def test_post_exit_cleanup_reports_unmount_failure_but_attempts_all_targets(
    tmp_path: Path,
) -> None:
    target = make_calamares_target(tmp_path)
    package_cleanup = load_module("cleanup_package_source", CLEANUP_PACKAGE_SOURCE)
    calamares_cleanup = load_module("cleanup_calamres_targets", CLEANUP_TARGETS)
    unmounted: list[Path] = []

    def unmount(path: Path) -> None:
        unmounted.append(path)
        if path == target / "etc/resolv.conf":
            raise RuntimeError("simulated resolver unmount failure")

    failures, cleaned = calamares_cleanup.cleanup_targets(
        [target / "etc/pacman.conf"],
        package_cleanup,
        unmount,
        temp_root=tmp_path,
        owner_uid=os.geteuid(),
    )

    assert not cleaned
    assert len(failures) == 1
    assert "simulated resolver unmount failure" in failures[0]
    assert target in unmounted
    assert all(include not in (target / "etc/pacman.conf").read_text() for include in TEMP_INCLUDES)
