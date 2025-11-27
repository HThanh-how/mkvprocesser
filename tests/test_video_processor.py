from pathlib import Path

import mkvprocessor.video_processor as video_processor


def test_rename_simple_generates_expected_name(tmp_path, monkeypatch):
    file_path = tmp_path / "movie.mkv"
    file_path.write_text("dummy")

    monkeypatch.setattr(video_processor, "get_video_resolution_label", lambda _path: "4K")

    class DummyFFmpeg:
        @staticmethod
        def probe(_path):
            return {
                "streams": [
                    {"codec_type": "video", "width": 3840, "height": 2160},
                    {"codec_type": "audio", "tags": {"language": "vie", "title": "VIE"}},
                ]
            }

    monkeypatch.setattr(video_processor, "ffmpeg", DummyFFmpeg)

    new_path = video_processor.rename_simple(file_path)
    assert Path(new_path).name.startswith("4K_VIE_")
    assert Path(new_path).exists()

