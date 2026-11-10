"""machine door: refusals, sandbox arguments, remote quoting, and (when bwrap exists) the real read-only guarantee. No ssh connection is ever made."""
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("machine", Path(__file__).resolve().parents[2] / "mcp" / "machine" / "machine.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
needs_bwrap = pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap not installed")


class Fake:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0, b"out", b"")


@pytest.fixture(autouse=True)
def quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "LOG", tmp_path / "machine.log")
    monkeypatch.setattr(m, "DRY_FLAG", tmp_path / "no_dry")
    monkeypatch.delenv("ROYVA_DRY_RUN", raising=False)


def test_refusals():
    assert "root" in m.refuse("sudo ls") and "root" in m.refuse("echo hi; su -")
    assert m.refuse("ls") is None and m.refuse("echo pseudo") is None and m.refuse("ls /usr/sudoers.d") is None
    assert "review" in m.refuse("x" * 3001) and m.refuse("") and m.refuse("a\x00b")


def test_local_run_is_sandboxed_and_passes_the_command_as_one_argument():
    f = Fake()
    out = m.run({"command": "ls; echo 'x y'"}, runner=f)
    argv, kw = f.calls[0]
    assert argv[0] == "bwrap" and argv[-4:] == ["--", "sh", "-c", "ls; echo 'x y'"] and "--unshare-net" in argv and "--unshare-pid" in argv
    assert argv[argv.index("--ro-bind") + 1:argv.index("--ro-bind") + 3] == ["/", "/"]
    assert set(kw["env"]) <= {"PATH", "HOME", "LANG", "USER", "XDG_RUNTIME_DIR"} and out["sandbox"] is True


def test_secret_paths_are_hidden_only_when_they_exist(tmp_path):
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".netrc").write_text("x")
    a = m.sandbox_argv(tmp_path)
    assert str(tmp_path / ".ssh") in a and str(tmp_path / ".netrc") in a and str(tmp_path / ".gnupg") not in a


def test_exact_trusted_commands_run_unsandboxed_nothing_else():
    f = Fake()
    assert m.run({"command": "crontab -l"}, runner=f)["sandbox"] is False and f.calls[0][0] == ["crontab", "-l"]
    f2 = Fake()
    m.run({"command": "crontab -l; rm -rf x"}, runner=f2)
    m.run({"command": "crontab -r"}, runner=f2)
    assert all(c[0][0] == "bwrap" for c in f2.calls)


def test_write_failure_points_to_the_approved_tool():
    r = {"exit_code": 1, "stderr": "touch: cannot touch 'x': Read-only file system"}
    assert "run_approved" in m._with_hint(r, "run_approved")["hint"]
    assert "hint" not in m._with_hint({"exit_code": 0, "stderr": ""}, "run_approved")


def test_approved_run_is_real_but_honours_dry_run(monkeypatch):
    f = Fake()
    m.run_approved({"command": "echo hi"}, runner=f)
    assert f.calls[0][0] == ["/bin/bash", "-c", "echo hi"]
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    f2 = Fake()
    assert m.run_approved({"command": "echo hi"}, runner=f2)["dry_run"] and not f2.calls


def test_remote_only_to_allowed_hosts_and_never_connects_here(monkeypatch):
    monkeypatch.setenv("ROYVA_REMOTE_HOSTS", "somdutta@box.local")
    f = Fake()
    assert "not allowed" in m.remote_run({"host": "evil@x", "command": "ls"}, runner=f)["error"] and not f.calls
    m.remote_run({"host": "somdutta@box.local", "command": "free -m"}, runner=f)
    argv = f.calls[0][0]
    assert argv[0] == "ssh" and "BatchMode=yes" in argv and argv[-2] == "somdutta@box.local" and argv[-1] == m.remote_command("free -m", True)


@needs_bwrap
def test_remote_quoting_survives_the_remote_shell_and_stays_read_only(tmp_path):
    """Run the exact string ssh would hand to the remote login shell through a local shell: quotes and ; must stay inside the command."""
    probe = Path("/var/tmp") / f"royva_probe_{os.getpid()}"
    nasty = f"echo \"it's\"; echo 'a;b'; touch {probe}; echo done"
    out = subprocess.run(["sh", "-c", m.remote_command(nasty, True)], capture_output=True, text=True, timeout=30)
    assert "it's" in out.stdout and "a;b" in out.stdout and "done" in out.stdout
    assert "Read-only" in out.stderr and not probe.exists()
    ok = subprocess.run(["sh", "-c", m.remote_command("echo $HOME; env | wc -l", True)], capture_output=True, text=True, timeout=30)
    assert ok.stdout.splitlines()[0] == os.path.expanduser("~")


@needs_bwrap
def test_real_sandbox_reads_but_cannot_write_or_see_secrets(monkeypatch):
    monkeypatch.setenv("ROYVA_FAKE_SECRET", "hunter2")
    victim = Path.home() / f".royva_probe_{os.getpid()}"
    r = m.run({"command": f"touch {victim}; echo rc=$?; free -m | head -1; env; cat /proc/1/environ | tr '\\0' '\\n'; ls /run | wc -l"})
    assert not victim.exists() and "Read-only" in r["stderr"] and "total" in r["stdout"]
    assert "hunter2" not in r["stdout"] and r["stdout"].count("PATH=") >= 1
    assert "hint" in r and "run_approved" in r["hint"]
    net = m.run({"command": "cat /proc/net/dev | wc -l"})
    assert int(net["stdout"].strip()) <= 3                                                    # loopback only: no network interfaces
