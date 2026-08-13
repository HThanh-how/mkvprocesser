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



def test_process_video_accepts_mux_kwargs_from_its_only_caller():
    """Hoi quy: extract_video_with_audio() goi process_video() kem
    mux_subtitles=/mux_subtitle_indices= o ca 3 nhanh, nhung chu ky
    process_video() lai khong co hai tham so do -> moi lan xu ly video deu
    TypeError, bi `except Exception` nuot thanh mot dong log chung chung nen
    khong ai thay. Giu test nay de chu ky hai ham khong lech nhau lan nua.
    """
    import inspect

    callee = inspect.signature(video_processor.process_video).parameters
    caller = inspect.signature(video_processor.extract_video_with_audio).parameters
    for name in ("mux_subtitles", "mux_subtitle_indices"):
        assert name in caller, f"caller mat tham so {name}"
        assert name in callee, f"process_video khong nhan {name} (se TypeError)"


def test_process_video_defaults_subtitle_indices_to_empty_list(tmp_path, monkeypatch):
    """mux_subtitle_indices=None phai thanh [] chu khong duoc lam vo vong lap."""
    captured = {}

    def fake_probe(_path):
        return {"streams": [{"codec_type": "audio", "index": 1, "channels": 2,
                             "tags": {"language": "vie"}}]}

    monkeypatch.setattr(video_processor, "ffmpeg", type("F", (), {"probe": staticmethod(fake_probe)}))
    monkeypatch.setattr(video_processor, "get_file_size_gb", lambda _p: 0.01)

    def fake_run(cmd, **_kw):
        captured["cmd"] = cmd
        raise RuntimeError("dung o day - chi can biet cmd dung duoc dung")

    monkeypatch.setattr(video_processor, "run_ffmpeg_command", fake_run)
    src = tmp_path / "phim.mkv"
    src.write_text("x")
    video_processor.process_video(
        src, str(tmp_path / "out"), (1, 2, "vie", "VIE"), str(tmp_path / "log.json"),
        fake_probe(src), mux_subtitles=True, mux_subtitle_indices=None)
    assert "cmd" in captured        # den duoc buoc dung ffmpeg, khong no TypeError
