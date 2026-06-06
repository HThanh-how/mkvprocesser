import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import config  # noqa: E402


def test_defaults_present():
    c = config.load()
    for k in ("skip_processed", "state_file", "min_free_gb_factor", "privacy", "container"):
        assert k in c


def test_env_coercion(monkeypatch):
    monkeypatch.setenv("MKV_UPLOAD", "false")
    monkeypatch.setenv("MKV_POLL_SECONDS", "5")
    monkeypatch.setenv("MKV_MIN_FREE_GB_FACTOR", "2.5")
    monkeypatch.setenv("MKV_SKIP_PROCESSED", "no")
    c = config.load()
    assert c["upload"] is False              # bool, khong phai chuoi "false"
    assert c["poll_seconds"] == 5            # int
    assert c["min_free_gb_factor"] == 2.5    # float
    assert c["skip_processed"] is False


def test_validate_accepts_defaults():
    assert config.validate(dict(config._DEFAULTS)) is not None


def test_validate_rejects_bad_privacy(monkeypatch):
    monkeypatch.setenv("MKV_PRIVACY", "secret")
    with pytest.raises(ValueError):
        config.load()


def test_validate_rejects_bad_poll(monkeypatch):
    monkeypatch.setenv("MKV_POLL_SECONDS", "0")
    with pytest.raises(ValueError):
        config.load()


def test_find_config_via_env(tmp_path, monkeypatch):
    p = tmp_path / "custom.yaml"
    p.write_text("privacy: unlisted\nupload: false\n", encoding="utf-8")
    monkeypatch.setenv("MKV_CONFIG", str(p))
    c = config.load()
    assert c["privacy"] == "unlisted" and c["upload"] is False


def test_find_config_prefers_explicit_arg(tmp_path):
    p = tmp_path / "explicit.yaml"
    p.write_text("container: mkv\n", encoding="utf-8")
    assert config.load(str(p))["container"] == "mkv"
