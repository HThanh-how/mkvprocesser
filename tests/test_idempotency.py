import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import idempotency as I  # noqa: E402


def test_signature_stable_and_content_sensitive(tmp_path):
    a = tmp_path / "a.bin"
    a.write_bytes(b"hello world " * 1000)
    b = tmp_path / "b.bin"
    b.write_bytes(b"hello world " * 1000)   # cung noi dung
    c = tmp_path / "c.bin"
    c.write_bytes(b"different bytes " * 1000)
    sig_a = I.file_signature(str(a))
    assert sig_a == I.file_signature(str(a))      # on dinh khi goi lai
    assert I.file_signature(str(b)) == sig_a       # cung noi dung -> cung chu ky
    assert I.file_signature(str(c)) != sig_a       # khac noi dung -> khac chu ky


def test_signature_detects_tail_change(tmp_path):
    big = b"x" * (2 << 20)               # 2 MiB -> co doc ca dau lan cuoi
    p1 = tmp_path / "1.bin"
    p1.write_bytes(big + b"AAAA")
    p2 = tmp_path / "2.bin"
    p2.write_bytes(big + b"BBBB")        # chi khac duoi cuoi
    assert I.file_signature(str(p1)) != I.file_signature(str(p2))


def test_store_roundtrip_and_persistence(tmp_path):
    path = tmp_path / "state" / "processed.json"   # thu muc chua ton tai
    store = I.ProcessedStore(str(path))
    assert len(store) == 0 and not store.has("sig1")
    store.add("sig1", {"name": "movie.mkv"})
    assert store.has("sig1") and len(store) == 1
    assert os.path.exists(path)                     # da ghi xuong dia
    reloaded = I.ProcessedStore(str(path))          # nap lai tu dia
    assert reloaded.has("sig1") and len(reloaded) == 1


def test_store_tolerates_corrupt_file(tmp_path):
    path = tmp_path / "processed.json"
    path.write_text("{ this is not valid json")
    store = I.ProcessedStore(str(path))             # khong duoc nem loi
    assert len(store) == 0
    store.add("sig", {})                            # van ghi de duoc
    assert I.ProcessedStore(str(path)).has("sig")
