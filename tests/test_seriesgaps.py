import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import seriesgaps as SG  # noqa: E402


def test_parse_title():
    assert SG.parse_title("4K_JPN_2024_Detective Conan Movie 27") == ("2024", "Detective Conan Movie 27")
    assert SG.parse_title("HD_EN_2001_A saga 1") == ("2001", "A saga 1")
    assert SG.parse_title("Khong theo template") == (None, "Khong theo template")
    assert SG.parse_title("  ") == (None, "")


def _fake_tget(url):
    if "search/movie" in url:
        if "A%20saga%201" in url:
            return {"results": [{"id": 1, "title": "Part 1"}]}
        if "A%20saga%202" in url:
            return {"results": [{"id": 2, "title": "Part 2"}]}
        return {"results": []}                              # standalone -> unmatched
    if "/movie/1?" in url or "/movie/2?" in url:
        return {"belongs_to_collection": {"id": 99, "name": "A Saga"}}
    if "/collection/99?" in url:
        return {"parts": [
            {"id": 1, "title": "Part 1", "release_date": "2001-05-01"},
            {"id": 2, "title": "Part 2", "release_date": "2003-05-01"},
            {"id": 3, "title": "Part 3", "release_date": "2005-05-01"},   # THIEU
        ]}
    return {}


def test_analyze_finds_missing():
    titles = ["HD_EN_2001_A saga 1", "HD_EN_2003_A saga 2", "HD_EN_2020_Standalone"]
    cols, unmatched = SG.analyze(titles, "KEY", tget=_fake_tget, log=lambda *a: None)
    assert len(cols) == 1
    c = cols[0]
    assert c["name"] == "A Saga" and c["total"] == 3
    assert set(c["have"]) == {"Part 1", "Part 2"}
    assert c["missing"] == [{"title": "Part 3", "year": "2005"}]
    assert unmatched == ["HD_EN_2020_Standalone"]           # khong khop TMDB


def test_analyze_no_titles():
    cols, unmatched = SG.analyze([], "KEY", tget=_fake_tget, log=lambda *a: None)
    assert cols == [] and unmatched == []
