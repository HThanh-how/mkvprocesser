"""
Metadata extraction utilities for MKV Processor.

Handles video metadata extraction: resolution, year, language, etc.
"""
import logging
from typing import Optional, Tuple

import ffmpeg  # type: ignore

logger = logging.getLogger(__name__)


def get_video_resolution_label(file_path: str) -> str:
    """Get video resolution label (FHD, 4K, 2K, HD).
    
    Args:
        file_path: Path to video file
    
    Returns:
        Resolution label string (e.g., '4K', 'FHD', 'HD')
    """
    try:
        probe = ffmpeg.probe(file_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream and 'width' in video_stream and 'height' in video_stream:
            width = int(video_stream['width'])
            height = int(video_stream['height'])
            # 8k
            if width >= 7680 or height >= 4320:
                return "8K"
            # 4k
            elif width >= 3840 or height >= 2160:  # Includes 3840x1608
                return "4K"
            # 2k
            elif width >= 2560 or height >= 1440:
                return "2K"
            # FHD
            elif width >= 1920 or height >= 1080:
                return "FHD"
            # HD
            elif width >= 1280 or height >= 720:
                return "HD"
            # 480p
            elif width >= 720 or height >= 480:
                return "480p"
            else:
                return f"{width}p"
    except Exception as e:
        logger.error(f"Error getting resolution for {file_path}: {e}")
    return "unknown_resolution"


def get_movie_year(file_path: str) -> str:
    """Get movie year from metadata.
    
    Args:
        file_path: Path to video file
    
    Returns:
        Year string, or empty string if not found
    """
    try:
        probe = ffmpeg.probe(file_path)
        format_tags = probe.get("format", {}).get("tags", {})
        year = format_tags.get("year", "")
        return year.strip()
    except Exception as e:
        logger.error(f"Error getting year for {file_path}: {e}")
    return ""


def get_language_abbreviation(language_code: str) -> str:
    """Return language abbreviation based on language code.
    
    Args:
        language_code: ISO 639 language code (e.g., 'eng', 'vie', 'und')
    
    Returns:
        Language abbreviation (e.g., 'ENG', 'VIE', 'UNK')
    """
    language_map = {
        'eng': 'ENG',  # English
        'vie': 'VIE',  # Vietnamese
        'und': 'UNK',  # Undefined
        'chi': 'CHI',  # Chinese
        'zho': 'CHI',  # Chinese (alternative code)
        'jpn': 'JPN',  # Japanese
        'kor': 'KOR',  # Korean
        'fra': 'FRA',  # French
        'deu': 'DEU',  # German
        'spa': 'SPA',  # Spanish
        'ita': 'ITA',  # Italian
        'rus': 'RUS',  # Russian
        'tha': 'THA',  # Thai
        'ind': 'IND',  # Indonesian
        'msa': 'MSA',  # Malaysian
        'ara': 'ARA',  # Arabic
        'hin': 'HIN',  # Hindi
        'por': 'POR',  # Portuguese
        'nld': 'NLD',  # Dutch
        'pol': 'POL',  # Polish
        'tur': 'TUR',  # Turkish
        'swe': 'SWE',  # Swedish
        'nor': 'NOR',  # Norwegian
        'dan': 'DAN',  # Danish
        'fin': 'FIN',  # Finnish
        'ukr': 'UKR',  # Ukrainian
        'ces': 'CES',  # Czech
        'hun': 'HUN',  # Hungarian
        'ron': 'RON',  # Romanian
        'bul': 'BUL',  # Bulgarian
        'hrv': 'HRV',  # Croatian
        'srp': 'SRP',  # Serbian
        'slv': 'SLV',  # Slovenian
        'ell': 'ELL',  # Greek
        'heb': 'HEB',  # Hebrew
        'kat': 'KAT',  # Georgian
        'lat': 'LAT',  # Latin
        'vie-Nom': 'NOM',  # Nom script
        'cmn': 'CMN',  # Mandarin Chinese
        'yue': 'YUE',  # Cantonese
        'nan': 'NAN',  # Min Nan
        'khm': 'KHM',  # Khmer
        'lao': 'LAO',  # Lao
        'mya': 'MYA',  # Burmese
        'ben': 'BEN',  # Bengali
        'tam': 'TAM',  # Tamil
        'tel': 'TEL',  # Telugu
        'mal': 'MAL',  # Malayalam
        'kan': 'KAN',  # Kannada
        'mar': 'MAR',  # Marathi
        'pan': 'PAN',  # Punjabi
        'guj': 'GUJ',  # Gujarati
        'ori': 'ORI',  # Oriya
        'asm': 'ASM',  # Assamese
        'urd': 'URD',  # Urdu
        'fas': 'FAS',  # Persian
        'pus': 'PUS',  # Pashto
        'kur': 'KUR',  # Kurdish
    }
    return language_map.get(language_code, language_code.upper()[:3])


def get_subtitle_info(file_path: str) -> list[Tuple[int, str, str, str]]:
    """Get information about subtitle tracks in video file.
    
    Args:
        file_path: Path to video file
    
    Returns:
        List of tuples: (index, language, title, codec) for each subtitle track
    """
    try:
        probe = ffmpeg.probe(file_path)
        subtitle_tracks: list[Tuple[int, str, str, str]] = []
        for stream in probe['streams']:
            if stream['codec_type'] == 'subtitle':
                index = stream.get('index', -1)
                language = stream.get('tags', {}).get('language', 'und')
                title = stream.get('tags', {}).get('title', '')
                codec = stream.get('codec_name', '')
                
                logger.debug(f"Found subtitle track: index={index}, language={language}, codec={codec}")
                
                subtitle_tracks.append((index, language, title, codec))
        return subtitle_tracks
    except (OSError, IOError, KeyError, ValueError) as e:
        logger.error(f"Error getting subtitle info from {file_path}: {e}")
        return []

