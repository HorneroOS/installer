"""Extra-users job: allowlist, validation, hashing, idempotency, no-op default."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "create_extra_users", ROOT / "image/calamares/create-extra-users.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

ALLOWLIST = ROOT / "image/calamares/extra-users-allowlist.yaml"
PASSWORD = "correct horse battery staple"


def _target(tmp_path: Path) -> Path:
    etc = tmp_path / "etc"
    etc.mkdir(parents=True)
    (etc / "passwd").write_text(
        "root:x:0:0::/root:/usr/bin/bash\n"
        "daemon:x:1:1::/:/usr/bin/nologin\n"
        "hornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n",
        encoding="utf-8",
    )
    (etc / "group").write_text(
        "root:x:0:\nwheel:x:998:hornero\nusers:x:984:\naudio:x:996:\n"
        "video:x:985:\ninput:x:995:\nstorage:x:988:\nnetwork:x:90:\n"
        "lp:x:991:\nscanner:x:993:\n",
        encoding="utf-8",
    )
    return tmp_path


def _selection(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "extra-users.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


class Recorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []

    def __call__(self, argv: list[str], stdin: str | None = None) -> None:
        self.calls.append(list(argv))
        self.stdins.append(stdin)


def test_sha512_crypt_matches_openssl_vector() -> None:
    assert mod.sha512_crypt("Hello world!", "saltstring") == (
        "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1"
    )


def test_missing_selection_is_noop(tmp_path) -> None:
    recorder = Recorder()
    assert mod.create_extra_users(_target(tmp_path), tmp_path / "absent.json", ALLOWLIST, recorder) == []
    assert recorder.calls == []


def test_empty_selection_is_noop_and_defaults_unchanged(tmp_path) -> None:
    root = _target(tmp_path)
    before = (root / "etc/passwd").read_text() + (root / "etc/group").read_text()
    recorder = Recorder()
    selection = _selection(tmp_path, {"primaryUser": "hornero", "rootPassword": "", "users": []})
    assert mod.create_extra_users(root, selection, ALLOWLIST, recorder) == []
    assert recorder.calls == []
    assert (root / "etc/passwd").read_text() + (root / "etc/group").read_text() == before
    assert not selection.exists(), "selection file must be removed after reading"


def test_creates_user_with_allowlisted_groups_and_hashed_password(tmp_path, capsys) -> None:
    root = _target(tmp_path)
    recorder = Recorder()
    selection = _selection(
        tmp_path,
        {"users": [{"login": "ana", "fullname": "Ana", "password": PASSWORD,
                    "groups": ["audio", "video"], "admin": False}]},
    )
    assert mod.create_extra_users(root, selection, ALLOWLIST, recorder) == ["ana"]
    useradd, chpasswd = recorder.calls
    assert useradd[:2] == ["/usr/sbin/useradd", "--create-home"]
    assert useradd[useradd.index("-G") + 1] == "audio,video"
    assert "wheel" not in useradd
    assert chpasswd == ["/usr/sbin/chpasswd", "-e"]
    assert all("$6$" not in arg for call in recorder.calls for arg in call), "hash must never be in argv"
    hashed = recorder.stdins[1].split(":", 1)[1].strip()
    assert recorder.stdins[1].startswith("ana:")
    assert hashed.startswith("$6$") and PASSWORD not in hashed
    assert mod.sha512_crypt(PASSWORD, hashed.split("$")[2]) == hashed
    assert PASSWORD not in capsys.readouterr().out
    assert not selection.exists()


def test_wheel_only_with_explicit_admin_flag(tmp_path) -> None:
    root = _target(tmp_path)
    allowlist = mod.load_allowlist(ALLOWLIST)
    assert "wheel" not in allowlist
    _, users, _ = mod.validate_selection(
        {"users": [{"login": "bob", "password": PASSWORD, "groups": [], "admin": True}]},
        root, allowlist,
    )
    assert users[0]["groups"] == ["wheel"]
    with pytest.raises(ValueError, match="allowlist"):
        mod.validate_selection(
            {"users": [{"login": "bob", "password": PASSWORD, "groups": ["wheel"]}]},
            root, allowlist,
        )


@pytest.mark.parametrize("login", ["Root", "1ana", "ana maria", "ana;rm", "a" * 33, "root"])
def test_invalid_or_reserved_logins_rejected(tmp_path, login) -> None:
    allowlist = mod.load_allowlist(ALLOWLIST)
    with pytest.raises(ValueError):
        mod.validate_selection(
            {"users": [{"login": login, "password": PASSWORD, "groups": []}]},
            _target(tmp_path), allowlist,
        )


def test_primary_and_system_collisions_rejected(tmp_path) -> None:
    allowlist = mod.load_allowlist(ALLOWLIST)
    root = _target(tmp_path)
    for login in ("hornero", "daemon"):
        with pytest.raises(ValueError):
            mod.validate_selection(
                {"users": [{"login": login, "password": PASSWORD, "groups": []}]},
                root, allowlist,
            )


def test_short_password_and_unknown_group_rejected(tmp_path) -> None:
    allowlist = mod.load_allowlist(ALLOWLIST)
    root = _target(tmp_path)
    with pytest.raises(ValueError, match="at least 12"):
        mod.validate_selection(
            {"users": [{"login": "ana", "password": "short", "groups": []}]}, root, allowlist
        )
    with pytest.raises(ValueError, match="allowlist"):
        mod.validate_selection(
            {"users": [{"login": "ana", "password": PASSWORD, "groups": ["disk"]}]},
            root, allowlist,
        )


def test_existing_user_only_reconciles_groups(tmp_path) -> None:
    root = _target(tmp_path)
    with (root / "etc/passwd").open("a", encoding="utf-8") as handle:
        handle.write("ana:x:1001:1001::/home/ana:/usr/bin/zsh\n")
    recorder = Recorder()
    selection = _selection(
        tmp_path, {"users": [{"login": "ana", "groups": ["audio"], "admin": False}]}
    )
    assert mod.create_extra_users(root, selection, ALLOWLIST, recorder) == ["ana"]
    assert recorder.calls == [["/usr/sbin/usermod", "-aG", "audio", "ana"]]


def test_root_password_optional_and_separate(tmp_path) -> None:
    root = _target(tmp_path)
    recorder = Recorder()
    selection = _selection(tmp_path, {"rootPassword": PASSWORD, "users": []})
    assert mod.create_extra_users(root, selection, ALLOWLIST, recorder) == []
    (call,) = recorder.calls
    assert call == ["/usr/sbin/chpasswd", "-e"]
    assert all("$6$" not in arg for arg in call)
    hashed = recorder.stdins[0].split(":", 1)[1].strip()
    assert recorder.stdins[0].startswith("root:") and hashed.startswith("$6$")
    assert mod.sha512_crypt(PASSWORD, hashed.split("$")[2]) == hashed


def test_runner_errors_never_echo_password_hash(tmp_path) -> None:
    def failing(argv: list[str], stdin: str | None = None) -> None:
        raise RuntimeError(f"target command failed ({argv[0]}, rc=1)")

    with pytest.raises(RuntimeError) as excinfo:
        mod.apply_selection(_target(tmp_path), "hornero", [], PASSWORD, failing)
    assert PASSWORD not in str(excinfo.value) and "$6$" not in str(excinfo.value)


def test_selection_file_with_loose_mode_rejected_and_removed(tmp_path) -> None:
    root = _target(tmp_path)
    recorder = Recorder()
    selection = _selection(tmp_path, {"rootPassword": PASSWORD, "users": []})
    selection.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        mod.create_extra_users(root, selection, ALLOWLIST, recorder)
    assert recorder.calls == []
    assert not selection.exists()
