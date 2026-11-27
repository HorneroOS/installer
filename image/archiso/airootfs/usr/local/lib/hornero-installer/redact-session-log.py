#!/usr/bin/env python3
"""Redact sensitive values from Calamares session logs before live-user export."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = (
    r"(?:root_?password|luks_?passphrase|passphrase|password|"
    r"wpa_?psk|wifi_?psk|pre_?shared_?key|psk|"
    r"client_?secret|secret|api_?key|access_?token|auth_?token|private_?key)"
)

# Qt QVariantMap debug output emitted by Calamares (-D6), e.g.:
#   ("luksPassphrase", QVariant(QString, "hunter2"))
_QVARIANT_RE = re.compile(
    rf'(["\']?{_SENSITIVE_KEY}["\']?\s*,\s*QVariant\([^,]+,\s*)(?:"[^"]*"|\'[^\']*\'|[^)]+)',
    re.IGNORECASE,
)

# JSON / YAML / INI / NetworkManager dotted key=value or key: value entries.
# Matches e.g. `"password": "abc"`, `802-11-wireless-security.psk: abc`, `psk="abc"`.
_KV_RE = re.compile(
    rf'(["\']?(?:[A-Za-z0-9_.-]*\.)?{_SENSITIVE_KEY}["\']?\s*[:=]\s*)'
    rf'(?:"[^"]*"|\'[^\']*\'|[^\s,;}}\])]+)',
    re.IGNORECASE,
)

# Crypt / PAM password hashes ($1$, $5$, $6$, $y$, $2a/b/y$, $argon2*).
_CRYPT_HASH_RE = re.compile(
    r'\$(?:1|5|6|y|2[aby]?|argon2(?:id|i|d))\$[^\s"\'`,;}\])]+'
)

# CLI flags carrying secrets inline (e.g. --password foo, --passphrase=bar, usermod -p ...).
_CLI_FLAG_RE = re.compile(
    r'(--(?:root-?password|luks-?passphrase|passphrase|password|psk|secret|token)(?:=|\s+))'
    r'(?:"[^"]*"|\'[^\']*\'|\S+)',
    re.IGNORECASE,
)
_USERMOD_P_RE = re.compile(
    r'(\busermod\b[^\n]*?\s-p\s+)(?:"[^"]*"|\'[^\']*\'|\S+)',
)

# Piped secrets into cryptsetup / chpasswd / passwd (echo/printf/herestring).
_PIPED_SECRET_RE = re.compile(
    r'(\b(?:echo|printf)\s+)(?:"[^"]*"|\'[^\']*\'|[^|;\n]+?)(\s*\|\s*(?:/usr/(?:s?bin)/)?(?:chpasswd|passwd|cryptsetup)\b)',
    re.IGNORECASE,
)
_HERESTRING_SECRET_RE = re.compile(
    r'(\b(?:chpasswd|passwd|cryptsetup)\b[^\n]*?<<<\s*)(?:"[^"]*"|\'[^\']*\'|\S+)',
    re.IGNORECASE,
)


def _replace_kv(match: re.Match[str]) -> str:
    prefix = match.group(1)
    full = match.group(0)
    value = full[len(prefix) :]
    if value.startswith('"') and value.endswith('"'):
        return f'{prefix}"{REDACTED}"'
    if value.startswith("'") and value.endswith("'"):
        return f"{prefix}'{REDACTED}'"
    return f"{prefix}{REDACTED}"


def redact_text(text: str) -> str:
    """Scrub passwords, passphrases, PSKs, tokens, and crypt hashes from *text*."""
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        line = _QVARIANT_RE.sub(rf'\1"{REDACTED}"', line)
        line = _KV_RE.sub(_replace_kv, line)
        line = _CRYPT_HASH_RE.sub(REDACTED, line)
        line = _CLI_FLAG_RE.sub(rf"\1{REDACTED}", line)
        line = _USERMOD_P_RE.sub(rf"\1{REDACTED}", line)
        line = _PIPED_SECRET_RE.sub(rf"\1{REDACTED}\2", line)
        line = _HERESTRING_SECRET_RE.sub(rf"\1{REDACTED}", line)
        lines.append(line)
    return "".join(lines)


def read_regular_nofollow(path: Path) -> str:
    """Read UTF-8 text from *path* while refusing symlinks and non-regular files."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"{path} is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Calamares session log path")
    args = parser.parse_args(argv)
    try:
        raw = read_regular_nofollow(args.source)
    except (OSError, ValueError) as exc:
        print(f"redact-session-log: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(redact_text(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
