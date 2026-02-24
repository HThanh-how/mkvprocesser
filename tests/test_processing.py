"""
Unit tests for VideoProcessingManager.
"""
import pytest
from mkvprocessor.processing_core import VideoProcessingManager

def test_manager_initialization():
    manager = VideoProcessingManager(settings={"language": "en"})
    assert manager.language == "en"
    assert "subtitles" in manager.subtitle_folder.lower()

def test_cache_dir_setup(tmp_path):
    manager = VideoProcessingManager(settings={
        "use_ssd_cache": True,
        "temp_cache_dir": str(tmp_path)
    })
    assert manager.cache_dir == str(tmp_path)

@pytest.mark.parametrize("lang, expected", [
    ("vi", "vi"),
    ("en", "en"),
])
def test_language_setting(lang, expected):
    manager = VideoProcessingManager(settings={"language": lang})
    assert manager.language == expected
