"""The installed target must identify as HorneroOS, not plain Arch."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "configure_os_identity", ROOT / "image/calamares/configure-os-identity.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _target(tmp_path: Path, os_release: str | None, symlink: bool = False) -> Path:
    etc = tmp_path / "etc"
    etc.mkdir()
    if symlink:
        lib = tmp_path / "usr/lib"
        lib.mkdir(parents=True)
        (lib / "os-release").write_text(os_release or "", encoding="utf-8")
        (etc / "os-release").symlink_to("../usr/lib/os-release")
    elif os_release is not None:
        (etc / "os-release").write_text(os_release, encoding="utf-8")
    return tmp_path


def test_arch_symlink_is_replaced_with_hornero_identity(tmp_path):
    root = _target(tmp_path, 'NAME="Arch Linux"\nID=arch\n', symlink=True)
    mod.configure_os_identity(root)
    dest = root / "etc/os-release"
    assert not dest.is_symlink()
    text = dest.read_text(encoding="utf-8")
    assert "ID=horneroos" in text and "ID_LIKE=arch" in text
    # The packaged /usr/lib/os-release stays untouched.
    assert "ID=arch" in (root / "usr/lib/os-release").read_text(encoding="utf-8")


def test_missing_os_release_is_created(tmp_path):
    root = _target(tmp_path, None)
    mod.configure_os_identity(root)
    assert "ID=horneroos" in (root / "etc/os-release").read_text(encoding="utf-8")


def test_existing_non_arch_identity_is_preserved(tmp_path):
    root = _target(tmp_path, 'NAME="Custom"\nID=custom\n')
    mod.configure_os_identity(root)
    assert "ID=custom" in (root / "etc/os-release").read_text(encoding="utf-8")


def test_idempotent(tmp_path):
    root = _target(tmp_path, "ID=arch\n", symlink=True)
    mod.configure_os_identity(root)
    first = (root / "etc/os-release").read_text(encoding="utf-8")
    mod.configure_os_identity(root)
    assert (root / "etc/os-release").read_text(encoding="utf-8") == first


def test_wiring():
    settings = (ROOT / "image/calamares/settings.conf").read_text(encoding="utf-8")
    assert "shellprocess@os-identity" in settings
    conf = ROOT / "image/calamares/modules/shellprocess-os-identity.conf"
    assert "configure-os-identity.py" in conf.read_text(encoding="utf-8")
    builder = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert "configure-os-identity.py" in builder
