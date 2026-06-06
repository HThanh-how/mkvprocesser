import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import config  # noqa: E402


def test_ui_settings_override_and_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ui_settings_path", lambda: str(tmp_path / "ui_settings.json"))
    config.save_ui_settings({"privacy": "unlisted", "min_free_gb": 12.5})
    c = config.load()
    assert c["privacy"] == "unlisted" and c["min_free_gb"] == 12.5    # ui ghi de config.yaml
    config.save_ui_settings({"master_playlist": "All"})              # luu them -> merge
    c2 = config.load()
    assert c2["privacy"] == "unlisted" and c2["master_playlist"] == "All"


def test_env_still_wins_over_ui(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ui_settings_path", lambda: str(tmp_path / "ui_settings.json"))
    config.save_ui_settings({"privacy": "unlisted"})
    monkeypatch.setenv("MKV_PRIVACY", "private")
    assert config.load()["privacy"] == "private"                    # env (ha tang) > ui
