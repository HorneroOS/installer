#!/usr/bin/env python3
"""Create additional target users and optionally set a separate root password.

This is the exec-side half of the installer user-choices contract
(HorneroOS/installer PR-A). It follows the proven shellprocess pattern of
``configure-user-defaults.py``: a ``dontChroot`` script that runs on the live
host against the installed target root after the stock Calamares ``users``
job has created the primary account.

Selection contract (written by a future installer page; no page ships yet,
see docs/calamares-provisional.md): a JSON file owned by root, mode 0600, on
the live tmpfs::

    {
      "primaryUser": "hornero",
      "rootPassword": "",
      "users": [
        {"login": "ana", "fullname": "Ana", "password": "...",
         "groups": ["audio", "video"], "admin": false}
      ]
    }

Safety rules enforced here, before anything touches the target:

- Logins must match ``^[a-z_][a-z0-9_-]{0,31}$`` and must not collide with
  the primary user, a system account, or each other.
- Groups come only from the versioned allowlist beside this script.
  ``wheel`` is never in the allowlist: an extra user joins ``wheel`` only
  when its own ``admin`` flag is explicitly true. The primary user stays
  the forced ``wheel`` admin created by the stock ``users`` module.
- Passwords need at least 12 characters (the ``users.conf`` policy). They
  are hashed in memory with SHA-512 crypt and applied via
  ``chpasswd -e`` fed on stdin, so hashes never appear in any argv
  (``/proc/<pid>/cmdline``). Plaintext and hashes are never printed,
  logged, or written anywhere; the selection file is unlinked as soon
  as it has been read.
- The selection file must be owned by the invoking user (root in the
  installer, so root-owned in production) with mode ``0600``; anything
  else is rejected and removed.
- An absent selection file, an empty user list, and an empty
  ``rootPassword`` are all no-ops: root stays locked (``!``) exactly as
  the stock ``users`` job leaves it today, and an untouched install is
  byte-identical to the current one.
- Idempotency: an extra login that already exists as a regular user only
  gets its groups reconciled; its password is never reset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

LOGIN_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024
SHELL = "/usr/bin/zsh"
# Never grantable through the groups list, not even by editing the
# selection file by hand: wheel requires the explicit per-user admin flag,
# and system groups are outside the contract entirely.
FORBIDDEN_GROUPS = frozenset(
    {"root", "wheel", "daemon", "bin", "sys", "adm", "disk", "kmem", "tty"}
)
RESERVED_LOGINS = frozenset({"root"})

_CRYPT_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def sha512_crypt(password: str, salt: str) -> str:
    """Return the SHA-512 crypt hash (``$6$``) for *password* and *salt*.

    Pure-Python implementation of the glibc SHA-crypt algorithm so the
    job does not depend on the ``crypt`` module (removed in Python 3.13)
    or on passing plaintext to an external command line.
    """
    if not salt or any(char not in _CRYPT_ALPHABET for char in salt):
        raise ValueError("salt must use the crypt base64 alphabet")
    salt = salt[:16]
    key = password.encode("utf-8")
    salt_bytes = salt.encode("ascii")

    digest_b = hashlib.sha512(key + salt_bytes + key).digest()

    ctx = hashlib.sha512(key + salt_bytes)
    remaining = len(key)
    while remaining > 64:
        ctx.update(digest_b)
        remaining -= 64
    ctx.update(digest_b[:remaining])
    count = len(key)
    while count:
        ctx.update(digest_b if count & 1 else key)
        count >>= 1
    digest_a = ctx.digest()

    ctx = hashlib.sha512()
    for _ in range(len(key)):
        ctx.update(key)
    digest_p = ctx.digest()
    p_bytes = (digest_p * (len(key) // 64 + 1))[: len(key)]

    ctx = hashlib.sha512()
    for _ in range(16 + digest_a[0]):
        ctx.update(salt_bytes)
    digest_s = ctx.digest()
    s_bytes = (digest_s * (len(salt_bytes) // 64 + 1))[: len(salt_bytes)]

    result = digest_a
    for round_ in range(5000):
        ctx = hashlib.sha512()
        ctx.update(p_bytes if round_ & 1 else result)
        if round_ % 3:
            ctx.update(s_bytes)
        if round_ % 7:
            ctx.update(p_bytes)
        ctx.update(result if round_ & 1 else p_bytes)
        result = ctx.digest()

    def encode(value: int, length: int) -> str:
        chars = []
        for _ in range(length):
            chars.append(_CRYPT_ALPHABET[value & 0x3F])
            value >>= 6
        return "".join(chars)

    order = [
        (0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4),
        (47, 5, 26), (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51),
        (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13),
        (56, 14, 35), (15, 36, 57), (37, 58, 16), (59, 17, 38),
        (18, 39, 60), (40, 61, 19), (62, 20, 41),
    ]
    encoded = "".join(
        encode(result[a] << 16 | result[b] << 8 | result[c], 4)
        for a, b, c in order
    )
    encoded += encode(result[63], 2)
    return f"$6${salt}${encoded}"


def hash_password(password: str) -> str:
    salt = "".join(secrets.choice(_CRYPT_ALPHABET) for _ in range(16))
    return sha512_crypt(password, salt)


def load_allowlist(path: Path) -> frozenset[str]:
    import yaml

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    groups = value.get("groups") if isinstance(value, dict) else None
    if not isinstance(groups, list) or not groups:
        raise ValueError(f"allowlist {path} must define a non-empty groups list")
    allowlist = frozenset(groups)
    bad = allowlist & FORBIDDEN_GROUPS
    if bad:
        raise ValueError(f"allowlist must never contain {sorted(bad)}")
    return allowlist


def _target_accounts(root: Path) -> dict[str, int]:
    accounts: dict[str, int] = {}
    passwd = root / "etc/passwd"
    if passwd.is_file():
        for line in passwd.read_text(encoding="utf-8", errors="replace").splitlines():
            fields = line.split(":")
            if len(fields) >= 3:
                try:
                    accounts[fields[0]] = int(fields[2])
                except ValueError:
                    continue
    return accounts


def _target_groups(root: Path) -> set[str]:
    groups: set[str] = set()
    group_file = root / "etc/group"
    if group_file.is_file():
        for line in group_file.read_text(encoding="utf-8", errors="replace").splitlines():
            name = line.split(":", 1)[0]
            if name:
                groups.add(name)
    return groups


def _check_password(password: object, owner: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError(f"{owner}: a password is required")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"{owner}: password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"{owner}: password is too long")
    return password


def validate_selection(
    selection: object, root: Path, allowlist: frozenset[str]
) -> tuple[str | None, list[dict], str | None]:
    """Validate *selection*; return (primary, users, root_password).

    ``users`` entries carry login, fullname, groups (with ``wheel`` already
    resolved from the explicit admin flag) and plaintext password. Passwords
    stay in memory only and are hashed by the caller at apply time.
    """
    if not isinstance(selection, dict):
        raise ValueError("selection must be a JSON object")
    accounts = _target_accounts(root)
    target_groups = _target_groups(root)

    primary = selection.get("primaryUser")
    if primary is not None and (
        not isinstance(primary, str) or not LOGIN_RE.fullmatch(primary)
    ):
        raise ValueError(f"invalid primary user: {primary!r}")
    if primary is None:
        regular = [name for name, uid in accounts.items() if uid >= 1000]
        primary = regular[0] if len(regular) == 1 else None

    root_password = selection.get("rootPassword") or None
    if root_password is not None:
        root_password = _check_password(root_password, "root")

    raw_users = selection.get("users", [])
    if not isinstance(raw_users, list):
        raise ValueError("selection users must be a list")
    users: list[dict] = []
    seen: set[str] = set()
    for entry in raw_users:
        if not isinstance(entry, dict):
            raise ValueError(f"invalid extra user entry: {entry!r}")
        login = entry.get("login")
        if not isinstance(login, str) or not LOGIN_RE.fullmatch(login):
            raise ValueError(f"invalid login: {login!r}")
        if login in RESERVED_LOGINS or login in seen:
            raise ValueError(f"duplicate or reserved login: {login}")
        if login == primary:
            raise ValueError(f"extra user duplicates the primary user: {login}")
        uid = accounts.get(login)
        if uid is not None and uid < 1000:
            raise ValueError(f"login collides with a system account: {login}")
        seen.add(login)

        fullname = entry.get("fullname", "")
        if not isinstance(fullname, str) or any(c in fullname for c in ":\n\r"):
            raise ValueError(f"{login}: invalid full name")
        if len(fullname) > 128:
            raise ValueError(f"{login}: full name is too long")

        groups = entry.get("groups", [])
        if not isinstance(groups, list) or any(
            not isinstance(group, str) for group in groups
        ):
            raise ValueError(f"{login}: groups must be a list of names")
        unknown = set(groups) - allowlist
        if unknown:
            raise ValueError(
                f"{login}: groups outside the allowlist: {sorted(unknown)}"
            )
        missing = set(groups) - target_groups
        if missing:
            raise ValueError(
                f"{login}: groups do not exist on the target: {sorted(missing)}"
            )
        resolved = list(dict.fromkeys(groups))
        admin = entry.get("admin", False)
        if not isinstance(admin, bool):
            raise ValueError(f"{login}: admin must be true or false")
        if admin:
            if "wheel" not in target_groups:
                raise ValueError(f"{login}: wheel does not exist on the target")
            resolved.append("wheel")

        existing = uid is not None
        password = None
        if not existing:
            password = _check_password(entry.get("password"), login)
        users.append(
            {
                "login": login,
                "fullname": fullname,
                "groups": resolved,
                "password": password,
                "existing": existing,
            }
        )
    return primary, users, root_password


class ChrootRunner:
    """Run account tools inside the target; argv lists only, never a shell."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, argv: list[str], stdin: str | None = None) -> None:
        completed = subprocess.run(
            ["/usr/bin/arch-chroot", str(self.root), *argv],
            input=stdin,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            # Never echo argv/stdin back: stdin may carry a password hash.
            raise RuntimeError(
                f"target command failed ({argv[0]}, rc={completed.returncode})"
            )


def apply_selection(
    root: Path,
    primary: str | None,
    users: list[dict],
    root_password: str | None,
    runner,
) -> list[str]:
    """Apply a validated selection; return the logins created or updated."""
    touched: list[str] = []
    for user in users:
        login = user["login"]
        if user["existing"]:
            if user["groups"]:
                runner(["/usr/sbin/usermod", "-aG", ",".join(user["groups"]), login])
        else:
            argv = [
                "/usr/sbin/useradd",
                "--create-home",
                "--shell",
                SHELL,
                "--user-group",
            ]
            if user["groups"]:
                argv += ["-G", ",".join(user["groups"])]
            if user["fullname"]:
                argv += ["--comment", user["fullname"]]
            argv.append(login)
            runner(argv)
            runner(
                ["/usr/sbin/chpasswd", "-e"],
                stdin=f"{login}:{hash_password(user['password'])}\n",
            )
        touched.append(login)
    if root_password is not None:
        runner(
            ["/usr/sbin/chpasswd", "-e"],
            stdin=f"root:{hash_password(root_password)}\n",
        )
    return touched


def create_extra_users(
    root: Path, selection_path: Path, allowlist_path: Path, runner=None
) -> list[str]:
    """Entry point mirroring configure-user-defaults.py; no-op by default."""
    root = root.resolve()
    if not selection_path.is_file():
        return []
    try:
        stat = selection_path.stat()
        if stat.st_uid != os.geteuid():
            raise ValueError("selection file must be owned by the invoking user")
        if stat.st_mode & 0o077:
            raise ValueError("selection file must have mode 0600")
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    finally:
        # Plaintext passwords live only in this file and in memory; remove
        # the file even when its contents turn out to be invalid.
        selection_path.unlink(missing_ok=True)
    allowlist = load_allowlist(allowlist_path)
    primary, users, root_password = validate_selection(selection, root, allowlist)
    if not users and root_password is None:
        return []
    if runner is None:
        runner = ChrootRunner(root)
    return apply_selection(root, primary, users, root_password, runner)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed target root")
    parser.add_argument("--selection", type=Path, required=True, help="selection JSON on the live host")
    parser.add_argument("--allowlist", type=Path, required=True, help="group allowlist YAML")
    args = parser.parse_args()
    try:
        touched = create_extra_users(args.root, args.selection, args.allowlist)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"create-extra-users: {error}", file=sys.stderr)
        return 1
    for login in touched:
        print(f"create-extra-users: configured extra user {login}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
