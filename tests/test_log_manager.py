from pathlib import Path

from mkvprocessor import log_manager


def test_log_and_read_processed_files(tmp_path):
    log_file = tmp_path / "processed_files.log"

    # Reset globals to have deterministic behaviour
    log_manager.RUN_LOG_ENTRIES = []
    log_manager.set_remote_sync(None)

    log_manager.log_processed_file(
        log_file,
        "old_name.mkv",
        "new_name.mkv",
        signature="sig123",
        metadata={
            "category": "video",
            "output_path": str(tmp_path / "new_name.mkv"),
        },
    )

    assert log_file.exists()
    contents = log_file.read_text(encoding="utf-8").strip().split("|")
    assert contents[0] == "old_name.mkv"
    assert contents[1] == "new_name.mkv"

    files, signatures = log_manager.read_processed_files(log_file)
    assert files["old_name.mkv"]["new_name"] == "new_name.mkv"
    assert signatures["sig123"]["new_name"] == "new_name.mkv"

