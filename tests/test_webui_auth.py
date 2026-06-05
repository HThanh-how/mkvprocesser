import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import webui  # noqa: E402  (can extra [web]: fastapi)


def test_token_ok_disabled_when_no_token():
    # khong dat MKV_GUI_TOKEN -> khong chan (giu hanh vi localhost cu)
    assert webui.token_ok("", "anything") is True
    assert webui.token_ok("", None) is True


def test_token_ok_enforced_when_token_set():
    assert webui.token_ok("s3cret", "s3cret") is True
    assert webui.token_ok("s3cret", "wrong") is False
    assert webui.token_ok("s3cret", None) is False
