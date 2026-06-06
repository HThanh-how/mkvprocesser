import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import titlematch as T  # noqa: E402


def test_reencodes_of_same_movie_share_key():
    a = "Avengers.Endgame.2019.1080p.BluRay.x264-GROUP.mkv"
    b = "Avengers Endgame (2019) 2160p WEB-DL HEVC DDP5 1.mp4"
    assert T.title_key(a) == T.title_key(b) == "avengers endgame|2019"


def test_parts_and_episodes_get_different_keys():
    # day la yeu cau cot loi: KHONG nham Phan 1/2/3
    assert T.title_key("Money.Heist.Part.1.2017.1080p.mkv") \
        != T.title_key("Money.Heist.Part.2.2017.1080p.mkv")
    assert T.title_key("Show.S01E01.1080p.WEB.mkv") \
        != T.title_key("Show.S01E02.1080p.WEB.mkv")


def test_year_separates_remakes():
    assert T.title_key("Dune.2021.2160p.mkv") != T.title_key("Dune.1984.1080p.mkv")


def test_parse_year_uses_last_occurrence():
    assert T.parse_year("Blade.Runner.2049.2017.1080p.mkv") == "2017"
    assert T.parse_year("Movie.mkv") == ""


def test_empty_key_when_only_junk():
    assert T.title_key("1080p.x264-GRP.mkv") == ""


def test_vietnamese_unicode_title():
    assert T.title_key("Bố.Già.2021.1080p.mkv") == "bố già|2021"


def test_resolution_rank():
    assert T.resolution_rank("Movie.2020.2160p.mkv") == 2160
    assert T.resolution_rank("Movie.2020.4K.BluRay.mkv") == 2160
    assert T.resolution_rank("Movie.2020.1080p.mkv") == 1080
    assert T.resolution_rank("Movie.2020.720p.mkv") == 720
    assert T.resolution_rank("Movie.2020.mkv") == 0           # khong ro
    assert T.resolution_rank("M.2160p.mkv") > T.resolution_rank("M.1080p.mkv")
