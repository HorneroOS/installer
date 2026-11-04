"""The encrypt initramfs hook must only ship on encrypted targets.

installer#65: on unencrypted installs the busybox `encrypt` hook (always
appended by initcpiocfg) falls back to opening the root device as if it
were LUKS and prints `ERROR: Failed to open encryption mapping ...` on
every boot. These tests pin the conditional-removal contract.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "configure_initcpio_encrypt", ROOT / "image/calamares/configure-initcpio-encrypt.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

HOOKS = "HOOKS=(base udev autodetect block keyboard consolefont encrypt filesystems fsck)\n"


def _target(tmp_path: Path, fstab: str | None, crypttab: str = "") -> Path:
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "mkinitcpio.conf").write_text(HOOKS, encoding="utf-8")
    if fstab is not None:
        (etc / "fstab").write_text(fstab, encoding="utf-8")
    (etc / "crypttab").write_text(crypttab, encoding="utf-8")
    return tmp_path


def _hooks(root: Path) -> str:
    return (root / "etc/mkinitcpio.conf").read_text(encoding="utf-8")


def test_unencrypted_target_loses_encrypt_hook(tmp_path):
    root = _target(tmp_path, "UUID=abc / btrfs rw,subvol=@ 0 0\n")
    mod.configure_initcpio_encrypt(root)
    assert " encrypt" not in _hooks(root)
    assert "filesystems fsck" in _hooks(root)


def test_luks_target_keeps_encrypt_hook(tmp_path):
    root = _target(tmp_path, "/dev/mapper/luks-abc / btrfs rw,subvol=@ 0 0\n")
    mod.configure_initcpio_encrypt(root)
    assert " encrypt " in _hooks(root)


def test_crypttab_entry_keeps_encrypt_hook(tmp_path):
    root = _target(
        tmp_path,
        "UUID=abc / btrfs rw 0 0\n",
        crypttab="cryptswap UUID=def none swap,discard\n",
    )
    mod.configure_initcpio_encrypt(root)
    assert " encrypt " in _hooks(root)


def test_missing_fstab_fails_safe_and_keeps_hook(tmp_path):
    root = _target(tmp_path, None)
    mod.configure_initcpio_encrypt(root)
    assert " encrypt " in _hooks(root)


def test_stock_comment_examples_do_not_shadow_real_hooks_line(tmp_path):
    # installer#88: the stock mkinitcpio.conf ships commented
    # `#    HOOKS=(...)` examples above the real assignment. The rewrite
    # must hit the real line, not the first comment that mentions HOOKS.
    root = _target(tmp_path, "UUID=abc / btrfs rw,subvol=@ 0 0\n")
    conf = root / "etc/mkinitcpio.conf"
    conf.write_text(
        "#    HOOKS=(base)\n"
        "#    HOOKS=(base udev microcode modconf keyboard keymap consolefont"
        " block mdadm_udev encrypt filesystems fsck)\n"
        + HOOKS,
        encoding="utf-8",
    )
    mod.configure_initcpio_encrypt(root)
    lines = _hooks(root).splitlines()
    real = [line for line in lines if line.startswith("HOOKS=(")]
    assert len(real) == 1
    assert " encrypt" not in real[0]
    # The commented examples are left untouched.
    assert "#    HOOKS=(base)" in lines[0]


def test_removal_is_idempotent(tmp_path):
    root = _target(tmp_path, "UUID=abc / btrfs rw,subvol=@ 0 0\n")
    mod.configure_initcpio_encrypt(root)
    first = _hooks(root)
    mod.configure_initcpio_encrypt(root)
    assert _hooks(root) == first
