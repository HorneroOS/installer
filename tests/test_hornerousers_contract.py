"""HorneroUsers viewmodule contract (installer#111): page -> selection JSON.

The C++ page cannot run here (no local Calamares build, per the lightweight
gate), so these tests pin the contract statically and by feeding the exact
JSON shape the page emits to the real backend validator
(create-extra-users.py). The VM gate for the page itself is declared in
docs/calamares-provisional.md and the PR; nothing here claims it ran.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"
VIEWMODULE = CALAMARES / "viewmodules/hornerousers"
PASSWORD = "correct horse battery staple"

_spec = importlib.util.spec_from_file_location(
    "create_extra_users", CALAMARES / "create-extra-users.py"
)
backend = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backend)


def _text(name: str) -> str:
    return (VIEWMODULE / name).read_text(encoding="utf-8")


def _target(tmp_path: Path) -> Path:
    etc = tmp_path / "etc"
    etc.mkdir(parents=True)
    (etc / "passwd").write_text(
        "root:x:0:0::/root:/usr/bin/bash\n"
        "hornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n",
        encoding="utf-8",
    )
    (etc / "group").write_text(
        "wheel:x:998:hornero\nusers:x:984:\naudio:x:996:\nvideo:x:985:\n"
        "input:x:995:\nstorage:x:988:\nnetwork:x:90:\nlp:x:991:\nscanner:x:993:\n",
        encoding="utf-8",
    )
    return tmp_path


def test_viewmodule_registered_and_injected_before_cmake():
    cmake = _text("CMakeLists.txt")
    assert "calamares_add_plugin(hornerousers" in cmake
    assert "TYPE viewmodule" in cmake
    pkgbuild = (ROOT / "packaging/calamares/PKGBUILD").read_text(encoding="utf-8")
    injection = 'cp -a "$startdir/../../image/calamares/viewmodules/hornerousers" "$srcdir/calamares/src/modules/hornerousers"'
    assert injection in pkgbuild
    assert pkgbuild.index(injection) < pkgbuild.index("cmake -S")
    assert re.search(r"^pkgrel=2$", pkgbuild, re.MULTILINE)


def test_page_not_in_show_sequence_until_vm_gate():
    settings = yaml.safe_load((CALAMARES / "settings.conf").read_text(encoding="utf-8"))
    show = settings["sequence"][0]["show"]
    assert "hornerousers" not in show
    assert show.index("users") < show.index("packagechooser")


def test_config_matches_backend_contract():
    conf = yaml.safe_load((CALAMARES / "modules/hornerousers.conf").read_text(encoding="utf-8"))
    allowlist = yaml.safe_load((CALAMARES / "extra-users-allowlist.yaml").read_text(encoding="utf-8"))
    assert conf["groups"] == allowlist["groups"]
    assert "wheel" not in conf["groups"]
    assert conf["minPasswordLength"] == backend.MIN_PASSWORD_LENGTH == 12
    shellprocess = (CALAMARES / "modules/shellprocess-extra-users.conf").read_text(encoding="utf-8")
    assert conf["selectionPath"] == "/run/hornero-installer/extra-users.json"
    assert conf["selectionPath"] in shellprocess


def test_cpp_validation_rules_present():
    config = _text("HorneroUsersConfig.cpp")
    # Login regex identical to the backend's.
    assert "^[a-z_][a-z0-9_-]{0,31}$" in config
    assert backend.LOGIN_RE.pattern == "^[a-z_][a-z0-9_-]{0,31}$"
    # Root empty is valid; non-empty requires length + confirmation match.
    assert "m_rootPassword.isEmpty()" in config
    assert "m_rootPassword.size() < m_minPasswordLength" in config
    assert "m_rootPassword != m_rootPasswordConfirm" in config
    # Extra users always require a password; wheel only via admin.
    assert 'group == QStringLiteral( "wheel" )' in config
    assert '"admin"' in config or 'QStringLiteral( "admin" )' in config


def test_cpp_writes_0600_before_secrets_and_never_logs_payload():
    config = _text("HorneroUsersConfig.cpp")
    assert "O_CLOEXEC, 0600" in config
    assert config.index("0600") < config.index("file.write( payload )")
    assert "isEmptySelection()" in config and "return true" in config
    combined = "".join(
        _text(name)
        for name in ("HorneroUsersConfig.cpp", "HorneroUsersPage.cpp", "HorneroUsersViewStep.cpp")
    )
    # No logging/debug of selection contents anywhere in the module.
    assert "qDebug" not in combined
    for forbidden in ("cWarning", "cDebug", "qWarning"):
        assert forbidden not in combined


def test_cpp_json_keys_match_backend(tmp_path):
    """The JSON the page builds (keys in HorneroUsersConfig.cpp) validates."""
    config = _text("HorneroUsersConfig.cpp")
    for key in ("rootPassword", "users", "login", "fullname", "password", "groups", "admin"):
        assert f'QStringLiteral( "{key}" )' in config
    assert "primaryUser" not in config, "backend derives primary from the target"

    root = _target(tmp_path)
    allowlist = backend.load_allowlist(CALAMARES / "extra-users-allowlist.yaml")
    page_emitted = {
        "rootPassword": PASSWORD,
        "users": [
            {"login": "ana", "fullname": "Ana", "password": PASSWORD,
             "groups": ["audio"], "admin": True}
        ],
    }
    primary, users, root_password = backend.validate_selection(page_emitted, root, allowlist)
    assert primary == "hornero"
    assert users[0]["groups"] == ["audio", "wheel"]  # admin flag -> wheel in backend
    assert root_password == PASSWORD

    # Empty page emission (no rootPassword key, empty users) is a no-op shape.
    _, users, root_password = backend.validate_selection({"users": []}, root, allowlist)
    assert users == [] and root_password is None


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"rootPassword": "short", "users": []}, "at least 12"),
        ({"users": [{"login": "Bad Name", "password": PASSWORD, "groups": []}]}, "invalid login"),
        ({"users": [{"login": "ana", "password": PASSWORD, "groups": ["wheel"]}]}, "allowlist"),
        ({"users": [{"login": "ana", "password": "short", "groups": []}]}, "at least 12"),
    ],
)
def test_backend_rejects_what_page_must_block(tmp_path, payload, match):
    allowlist = backend.load_allowlist(CALAMARES / "extra-users-allowlist.yaml")
    with pytest.raises(ValueError, match=match):
        backend.validate_selection(payload, _target(tmp_path), allowlist)
