"""scripts/lares_config.py: precedence (env > file > default) and bad-file handling."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("lares_config", Path(__file__).resolve().parents[2] / "scripts" / "lares_config.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)


def test_defaults_when_there_is_no_file():
    out = lc.exports({}, {})
    assert "export LARES_ASSISTANT_NAME=Roy" in out and "export LARES_PRODUCT=Lares" in out and "export LARES_COMMAND=roy" in out
    assert not any("ROYVA_" in line for line in out)                      # household values have no built-in default here


def test_file_values_override_defaults_and_lists_are_joined():
    cfg = {"brand": {"assistant_name": "Jarvis"}, "household": {"protected_devices": ["A B", "C"], "default_person": "alex"}}
    out = lc.exports(cfg, {})
    assert "export LARES_ASSISTANT_NAME=Jarvis" in out
    assert "export ROYVA_PROTECTED_DEVICES='A B,C'" in out and "export ROYVA_DEFAULT_PERSON=alex" in out


def test_an_already_set_environment_variable_wins():
    out = lc.exports({"brand": {"assistant_name": "Jarvis"}}, {"LARES_ASSISTANT_NAME": "Zed"})
    assert not any("LARES_ASSISTANT_NAME" in line for line in out)


def test_values_are_shell_quoted():
    out = lc.exports({"brand": {"assistant_name": "x; rm -rf /"}}, {})
    assert "export LARES_ASSISTANT_NAME='x; rm -rf /'" in out


def test_malformed_file_is_an_error(tmp_path, monkeypatch):
    bad = tmp_path / "lares.toml"
    bad.write_text("x = [")
    monkeypatch.setenv("LARES_CONFIG", str(bad))
    assert lc.main() == 2
