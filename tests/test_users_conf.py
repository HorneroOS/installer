"""Pin the stock users contract: hostname stays stock, root stays locked."""

from pathlib import Path

import yaml

CALAMARES = Path(__file__).resolve().parents[1] / "image" / "calamares"


def _users_conf() -> dict:
    return yaml.safe_load((CALAMARES / "modules/users.conf").read_text())


def test_primary_user_contract_unchanged() -> None:
    conf = _users_conf()
    assert conf["setRootPassword"] is False, (
        "stock Calamares blocks Next on an empty root password under the "
        "minLength policy; a separate root password goes through "
        "shellprocess@extra-users instead"
    )
    assert conf["doReusePassword"] is False
    assert conf["displayAutologin"] is False
    assert conf["user"]["shell"] == "/usr/bin/zsh"
    assert conf["user"]["home_permissions"] == "750"
    assert conf["passwordRequirements"]["minLength"] >= 12
    groups = [
        entry["name"] if isinstance(entry, dict) else entry
        for entry in conf["defaultGroups"]
    ]
    assert groups == ["users", "wheel"], "primary user stays the forced wheel admin"


def test_hostname_not_duplicated() -> None:
    # Hostname is already editable on the stock users page (EtcFile
    # default writes /etc/hostname). Pinning any hostname block here
    # could disable or duplicate it; assert none is introduced.
    conf = _users_conf()
    assert "hostname" not in conf


def test_extra_users_wiring() -> None:
    settings = yaml.safe_load((CALAMARES / "settings.conf").read_text())
    instances = {(e["module"], e["id"]): e["config"] for e in settings["instances"]}
    assert instances[("shellprocess", "extra-users")] == "shellprocess-extra-users.conf"
    assert (CALAMARES / "modules/shellprocess-extra-users.conf").is_file()
    exec_steps = settings["sequence"][1]["exec"]
    assert exec_steps.index("users") < exec_steps.index("shellprocess@extra-users")
    assert exec_steps.index("shellprocess@extra-users") < exec_steps.index(
        "shellprocess@user-defaults"
    )
    show_steps = settings["sequence"][0]["show"]
    assert show_steps == [
        "welcome", "locale", "keyboard", "partition", "users",
        "packagechooser", "summary",
    ], "no new page ships until a viewmodule can be built and VM-tested"
