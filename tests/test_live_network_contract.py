"""Live user can join Wi-Fi pre-install without a password (hornero#373).

Regression test: joining Wi-Fi in the live session prompted for a
root/hornero-live password. hornero-live is passwordless and in no
administrative group, so NetworkManager's default `auth_admin_keep`
for `org.freedesktop.NetworkManager.settings.modify.system` could
never be satisfied and the pre-install network step dead-ended.

The fix is a polkit rule shipped only in the archiso airootfs (the
live image). It grants `polkit.Result.YES` for exactly the
NetworkManager actions needed to scan for, create and activate a
Wi-Fi connection, scoped to user hornero-live in an active local
session. Installed systems are built from base.sqfs and never
receive the airootfs, so they keep NetworkManager's stock defaults;
the live sudoers grant must stay limited to hornero-installer-run.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHISO = ROOT / "image/archiso"
RULES = ARCHISO / "airootfs/etc/polkit-1/rules.d/10-hornero-live-network.rules"

# Actions needed to join Wi-Fi: radio/network on, scan, create or
# edit the connection profile (own + system), activate it.
JOIN_ACTIONS = {
    "org.freedesktop.NetworkManager.enable-disable-network",
    "org.freedesktop.NetworkManager.enable-disable-wifi",
    "org.freedesktop.NetworkManager.network-control",
    "org.freedesktop.NetworkManager.wifi.scan",
    "org.freedesktop.NetworkManager.settings.modify.own",
    "org.freedesktop.NetworkManager.settings.modify.system",
}

# General NetworkManager administration that must NOT be granted.
ADMIN_ACTIONS = {
    "org.freedesktop.NetworkManager.settings.modify.hostname",
    "org.freedesktop.NetworkManager.settings.modify.global-dns",
    "org.freedesktop.NetworkManager.reload",
    "org.freedesktop.NetworkManager.checkpoint-rollback",
    "org.freedesktop.NetworkManager.sleep-wake",
}


def _rules() -> str:
    return RULES.read_text(encoding="utf-8")


def test_live_network_rules_exist_and_scope_to_live_user() -> None:
    assert RULES.is_file(), "live-image polkit rules for NetworkManager are missing"
    rules = _rules()
    assert "polkit.addRule(function(action, subject)" in rules
    assert 'subject.user !== "hornero-live"' in rules, (
        "rule must be scoped to the hornero-live user only"
    )
    assert "subject.active" in rules and "subject.local" in rules, (
        "rule must require an active local session"
    )
    assert "polkit.Result.YES" in rules
    # No blanket grant: never authorize by prefix, group or action family.
    assert "indexOf" not in rules and "isInGroup" not in rules
    assert "auth_admin" not in rules.replace("`auth_admin_keep`", "")


def test_live_network_rules_grant_only_wifi_join_actions() -> None:
    rules = _rules()
    for action in JOIN_ACTIONS:
        assert f'case "{action}":' in rules, f"missing Wi-Fi join action {action}"
    for action in ADMIN_ACTIONS:
        assert action not in rules, f"rule must not grant admin action {action}"


def test_live_network_rules_registered_in_profiledef() -> None:
    profile = (ARCHISO / "profiledef.sh").read_text(encoding="utf-8")
    assert (
        '["/etc/polkit-1/rules.d/10-hornero-live-network.rules"]="0:0:644"' in profile
    ), "polkitd (not root) must be able to read the rules file in the image"


def test_live_network_packages_present() -> None:
    packages = {
        line.strip()
        for line in (ARCHISO / "packages.x86_64").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "networkmanager" in packages
    assert "polkit-gnome" in packages


def test_sudoers_still_grants_only_installer_runner() -> None:
    """The polkit rule must not widen into general live-user admin."""
    sudoers = (ARCHISO / "airootfs/etc/sudoers.d/hornero-live").read_text(
        encoding="utf-8"
    )
    grants = [
        line.strip()
        for line in sudoers.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        and not line.startswith("Defaults:")
    ]
    assert grants == [
        'hornero-live ALL=(root) NOPASSWD: /usr/local/bin/hornero-installer-run ""'
    ], f"live sudoers must grant ONLY hornero-installer-run, got {grants}"


def test_live_user_stays_passwordless_and_groupless() -> None:
    """Do not 'fix' #373 by giving hornero-live a password or wheel."""
    sysusers = (ARCHISO / "airootfs/etc/sysusers.d/hornero-live.conf").read_text(
        encoding="utf-8"
    )
    assert sysusers.strip() == (
        'u hornero-live - "HorneroOS live session" /home/hornero-live /bin/bash'
    )
    assert "wheel" not in sysusers and "network" not in sysusers
