"""Security hardening tests for hornero-installer-run and GitHub workflows."""

from __future__ import annotations

import importlib.util
import os
import pwd
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
GOVERNANCE_POLICY = ROOT / ".github" / "hornero-governance.yml"
RUNNER_PATH = ROOT / "image/archiso/airootfs/usr/local/bin/hornero-installer-run"
SUDOERS_PATH = ROOT / "image/archiso/airootfs/etc/sudoers.d/hornero-live"
REDACT_PATH = (
    ROOT / "image/archiso/airootfs/usr/local/lib/hornero-installer/redact-session-log.py"
)

SHA_PIN_RE = re.compile(
    r"uses:\s*[^\s#}]+@[0-9a-f]{40}\s+#\s*(?:v\d|governance-v\d)"
)


def _load_redact_module():
    spec = importlib.util.spec_from_file_location("redact_session_log", REDACT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflows_pin_all_external_actions_to_40_char_shas() -> None:
    workflows = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert workflows, "expected GitHub workflow files"
    for workflow in workflows:
        for lineno, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(), start=1
        ):
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("#") or "uses:" not in trimmed:
                continue
            ref = trimmed.split("uses:", 1)[1].strip().split()[0]
            if ref.startswith("./") or ref.startswith("docker://"):
                continue
            assert SHA_PIN_RE.search(trimmed), (
                f"{workflow.name}:{lineno}: external action {ref!r} must be pinned to a 40-char SHA with version comment"
            )


def test_workflows_enforce_least_privilege_concurrency_and_timeouts() -> None:
    workflows = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert len(workflows) >= 4
    for workflow in workflows:
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        assert isinstance(doc, dict)
        assert doc.get("permissions") == {"contents": "read"}, (
            f"{workflow.name} must declare top-level permissions: contents: read"
        )
        concurrency = doc.get("concurrency")
        assert isinstance(concurrency, dict) and concurrency.get("group"), (
            f"{workflow.name} must declare top-level concurrency group"
        )
        triggers = doc.get("on") or {}
        if "push" in triggers and "pull_request" in triggers:
            assert concurrency.get("cancel-in-progress") == "${{ github.event_name == 'pull_request' }}", (
                f"{workflow.name} must cancel in-progress runs only on PRs, never on main pushes"
            )
        for job_name, job in (doc.get("jobs") or {}).items():
            if "runs-on" in job:
                timeout = job.get("timeout-minutes")
                assert isinstance(timeout, int) and 0 < timeout <= 15, (
                    f"{workflow.name} job {job_name} must set timeout-minutes <= 15"
                )


def test_pr_governance_workflow_and_policy_onboarded() -> None:
    gov_wf = WORKFLOWS_DIR / "pr-governance.yml"
    assert gov_wf.is_file(), ".github/workflows/pr-governance.yml is missing"
    doc = yaml.safe_load(gov_wf.read_text(encoding="utf-8"))
    assert "pull_request" in (doc.get("on") or {})
    assert "pull_request_target" not in (doc.get("on") or {})
    job = doc["jobs"]["governance"]
    uses = job["uses"]
    assert uses.startswith("HorneroOS/.github/.github/workflows/pr-governance.yml@")
    sha = uses.split("@", 1)[1]
    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    assert job["with"]["engine-ref"] == sha
    assert job["permissions"] == {"contents": "read", "pull-requests": "write"}

    assert GOVERNANCE_POLICY.is_file(), ".github/hornero-governance.yml is missing"
    policy = yaml.safe_load(GOVERNANCE_POLICY.read_text(encoding="utf-8"))
    assert policy["version"] == 1
    assert policy["kind"] == "installer"
    risky = set(policy["policies"]["risky_paths"])
    assert ".github/workflows/**" in risky
    assert "image/archiso/airootfs/usr/local/bin/hornero-installer-run" in risky


def test_redact_session_log_scrubs_secrets_and_preserves_diagnostics() -> None:
    mod = _load_redact_module()
    sample = "\n".join(
        [
            '2026-11-27 [6]: QMap(("luksPassphrase", QVariant(QString, "MyLuksSecret!99"))("username", QVariant(QString, "alice")))',
            '2026-11-27 [6]: {"rootPassword": "RootSecret#42", "admin": true}',
            "2026-11-27 [6]: 802-11-wireless-security.psk: WifiPskSecret123",
            "2026-11-27 [6]: usermod -p $6$saltsalt$hashedpasswordvalue alice",
            '2026-11-27 [6]: echo "MyLuksSecret!99" | /usr/bin/cryptsetup luksFormat /dev/vda2',
            "2026-11-27 [6]: UsersModule: passwordRequirements minLength 12",
            "2026-11-27 [6]: Running /usr/bin/pacman -S --noconfirm linux",
        ]
    )
    redacted = mod.redact_text(sample)
    for secret in ("MyLuksSecret!99", "RootSecret#42", "WifiPskSecret123", "$6$saltsalt$hashedpasswordvalue"):
        assert secret not in redacted
    assert redacted.count("[REDACTED]") >= 5
    assert "passwordRequirements minLength 12" in redacted
    assert "Running /usr/bin/pacman -S --noconfirm linux" in redacted


def test_redact_session_log_rejects_symlinks(tmp_path: Path) -> None:
    mod = _load_redact_module()
    secret_file = tmp_path / "real-secret.txt"
    secret_file.write_text("password=topsecret\n", encoding="utf-8")
    link = tmp_path / "session.log"
    link.symlink_to(secret_file)
    with pytest.raises(OSError):
        mod.read_regular_nofollow(link)


def test_wrapper_static_hardening_invariants() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    sudoers = SUDOERS_PATH.read_text(encoding="utf-8")
    assert 'hornero-live ALL=(root) NOPASSWD: /usr/local/bin/hornero-installer-run ""' in sudoers
    assert "umask 0027" in runner
    assert '[[ -L "$offline_flag" ]]' in runner
    assert "os.O_NOFOLLOW" in runner
    assert "stat.S_ISREG" in runner
    assert "redact-session-log.py" in runner
    assert '[[ -L "$log_source" ]]' in runner


def _prepare_harness(
    tmp_path: Path, *, allow_current_user: bool
) -> tuple[Path, dict[str, Path]]:
    bin_dir = tmp_path / "bin"
    usr_lib = tmp_path / "usr-lib"
    local_lib = tmp_path / "local-lib"
    run_dir = tmp_path / "run"
    var_log = tmp_path / "varlog"
    root_cache = tmp_path / "root-cache"
    etc_calamares = tmp_path / "etc-calamares"
    for directory in (bin_dir, usr_lib, local_lib, var_log, root_cache, etc_calamares):
        directory.mkdir(parents=True)

    offline_flag = tmp_path / "hornero-installer-offline-accepted"
    gpu_log = tmp_path / "gpu-probe.log"

    # Minimal stubs for /usr/bin tools invoked by hornero-installer-run.
    for tool in ("logger", "chmod", "chown"):
        stub = bin_dir / tool
        stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    for sys_tool in ("rm", "install", "mktemp", "python3"):
        real_path = Path("/usr/bin") / sys_tool
        (bin_dir / sys_tool).symlink_to(real_path)

    # Custom install wrapper that ignores -o/-g when running unprivileged in tests.
    (bin_dir / "install").unlink()
    (bin_dir / "install").write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = []\n"
        "i = 1\n"
        "while i < len(sys.argv):\n"
        "    if sys.argv[i] in ('-o', '-g'):\n"
        "        i += 2\n"
        "        continue\n"
        "    args.append(sys.argv[i])\n"
        "    i += 1\n"
        "os.execv('/usr/bin/install', ['/usr/bin/install', *args])\n",
        encoding="utf-8",
    )
    (bin_dir / "install").chmod(0o755)

    calamares_log = root_cache / "session.log"
    calamares_stub = bin_dir / "calamares"
    calamares_stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'luksPassphrase="SecretPass123"\\nnormal line\\n\' > "{calamares_log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    calamares_stub.chmod(0o755)

    (usr_lib / "offline-repo.py").write_text(
        "import sys; sys.exit(0)\n", encoding="utf-8"
    )
    (local_lib / "cleanup-calamares-targets.py").write_text(
        "print('cleanup ok')\n", encoding="utf-8"
    )
    (local_lib / "redact-session-log.py").symlink_to(REDACT_PATH)

    script = RUNNER_PATH.read_text(encoding="utf-8")
    replacements = {
        "/tmp/hornero-installer-offline-accepted": str(offline_flag),
        "/run/hornero-installer": str(run_dir),
        "/var/log/hornero-installer-gpu-probe.log": str(gpu_log),
        "/var/log/hornero-installer": str(var_log),
        "/root/.cache/calamares/session.log": str(calamares_log),
        "/etc/calamares": str(etc_calamares),
        "/usr/lib/hornero-installer": str(usr_lib),
        "/usr/local/lib/hornero-installer": str(local_lib),
        "/usr/bin/": f"{bin_dir}/",
    }
    for old, new in replacements.items():
        script = script.replace(old, new)
    if allow_current_user:
        current_user = pwd.getpwuid(os.getuid()).pw_name
        script = script.replace('pwd.getpwnam("hornero-live")', f'pwd.getpwnam("{current_user}")')

    harness_runner = tmp_path / "hornero-installer-run"
    harness_runner.write_text(script, encoding="utf-8")
    harness_runner.chmod(0o755)
    return harness_runner, {
        "offline_flag": offline_flag,
        "run_dir": run_dir,
        "var_log": var_log,
        "calamares_log": calamares_log,
    }


def test_wrapper_rejects_symlinked_and_dangling_offline_flag(tmp_path: Path) -> None:
    runner, paths = _prepare_harness(tmp_path, allow_current_user=True)
    target = tmp_path / "secret-target"
    target.write_text("offline\n", encoding="utf-8")
    paths["offline_flag"].symlink_to(target)

    res = subprocess.run(["bash", str(runner)], check=False, capture_output=True, text=True)
    assert res.returncode == 1
    assert not paths["offline_flag"].is_symlink()
    assert target.read_text(encoding="utf-8") == "offline\n"
    assert not (paths["run_dir"] / "offline-mode").exists()

    # Dangling symlink must also be rejected and unlinked.
    paths["offline_flag"].symlink_to(tmp_path / "does-not-exist")
    res2 = subprocess.run(["bash", str(runner)], check=False, capture_output=True, text=True)
    assert res2.returncode == 1
    assert not paths["offline_flag"].is_symlink()


def test_wrapper_rejects_untrusted_offline_flag_owner(tmp_path: Path) -> None:
    if os.getuid() == 0:
        pytest.skip("requires non-root uid to simulate untrusted owner")
    runner, paths = _prepare_harness(tmp_path, allow_current_user=False)
    paths["offline_flag"].write_text("offline\n", encoding="utf-8")

    res = subprocess.run(["bash", str(runner)], check=False, capture_output=True, text=True)
    assert res.returncode == 1
    assert not paths["offline_flag"].exists()
    assert not (paths["run_dir"] / "offline-mode").exists()


def test_wrapper_redacts_session_log_and_sets_permissions(tmp_path: Path) -> None:
    runner, paths = _prepare_harness(tmp_path, allow_current_user=True)
    paths["offline_flag"].write_text("offline\n", encoding="utf-8")

    res = subprocess.run(["bash", str(runner)], check=False, capture_output=True, text=True)
    assert res.returncode == 0
    assert not paths["offline_flag"].exists()
    assert (paths["run_dir"] / "offline-mode").read_text(encoding="utf-8") == "offline\n"
    assert stat.S_IMODE((paths["run_dir"] / "offline-mode").stat().st_mode) == 0o600

    dest_log = paths["var_log"] / "session.log"
    assert dest_log.is_file() and not dest_log.is_symlink()
    assert stat.S_IMODE(dest_log.stat().st_mode) == 0o640
    content = dest_log.read_text(encoding="utf-8")
    assert "SecretPass123" not in content
    assert "[REDACTED]" in content
    assert "normal line" in content
    assert stat.S_IMODE(paths["var_log"].stat().st_mode) == 0o750
