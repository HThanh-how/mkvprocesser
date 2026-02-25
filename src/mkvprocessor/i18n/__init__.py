"""
Internationalization (i18n) support for MKV Processor.

Provides translation functionality with language switching support.
"""
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Default language
DEFAULT_LANGUAGE = "en"

# Supported languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
}

# Translation cache
_translations: Dict[str, Dict[str, str]] = {}
_current_language = DEFAULT_LANGUAGE

# Fallback translations (used when files can't be loaded)
FALLBACK_TRANSLATIONS = {
    "en": {
        "folders": {
            "vietnamese_audio": "Vietnamese Audio - Subtitles",
            "original": "Original",
            "subtitles": "Subtitles"
        },
        "messages": {
            "processing_file": "Processing file {current}/{total}: {filename}",
            "renamed_file": "Renamed file: {old} -> {new}"
        },
        "errors": {
            "ffmpeg_not_found": "FFmpeg not found. Please install FFmpeg."
        }
    },
    "vi": {
        "folders": {
            "vietnamese_audio": "Lồng Tiếng - Thuyết Minh",
            "original": "Original",
            "subtitles": "Subtitles"
        },
        "messages": {
            "processing_file": "Đang xử lý file {current}/{total}: {filename}",
            "renamed_file": "Đã đổi tên file: {old} -> {new}"
        },
        "errors": {
            "ffmpeg_not_found": "Không tìm thấy FFmpeg. Vui lòng cài đặt FFmpeg."
        }
    }
}


def get_translations_dir() -> Path:
    """Get the translations directory path.
    
    Returns:
        Path to translations directory
    """
    # Try to find translations in PyInstaller bundle first
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as compiled executable
        base_path = Path(sys._MEIPASS)
        # Try different possible paths
        possible_paths = [
            base_path / "mkvprocessor" / "i18n" / "translations",  # Direct bundle
            base_path / "src" / "mkvprocessor" / "i18n" / "translations",  # With src/
            base_path / "translations",  # Root level
        ]
        for translations_path in possible_paths:
            if translations_path.exists():
                return translations_path
    
    # Normal Python execution - use relative to this file
    return Path(__file__).parent / "translations"


def load_translations(language: str = DEFAULT_LANGUAGE) -> Dict[str, str]:
    """Load translations for a specific language.
    
    Args:
        language: Language code (e.g., 'en', 'vi')
    
    Returns:
        Dictionary of translations
    """
    if language in _translations:
        return _translations[language]
    
    translations_dir = get_translations_dir()
    translation_file = translations_dir / f"{language}.json"
    
    # Try to load from file
    if translation_file.exists():
        try:
            with open(translation_file, "r", encoding="utf-8") as f:
                translations = json.load(f)
            _translations[language] = translations
            return translations
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load translations for {language} from {translation_file}: {e}")
    else:
        logger.warning(f"Translation file not found: {translation_file}")
    
    # Use fallback translations if file can't be loaded
    if language in FALLBACK_TRANSLATIONS:
        logger.info(f"Using fallback translations for {language}")
        _translations[language] = FALLBACK_TRANSLATIONS[language]
        return FALLBACK_TRANSLATIONS[language]
    
    # If language not in fallback, try English
    if DEFAULT_LANGUAGE in FALLBACK_TRANSLATIONS:
        logger.info(f"Using fallback English translations")
        _translations[DEFAULT_LANGUAGE] = FALLBACK_TRANSLATIONS[DEFAULT_LANGUAGE]
        return FALLBACK_TRANSLATIONS[DEFAULT_LANGUAGE]
    
    return {}


def set_language(language: str) -> None:
    """Set the current language.
    
    Args:
        language: Language code (e.g., 'en', 'vi')
    """
    global _current_language
    if language not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language: {language}, using default")
        language = DEFAULT_LANGUAGE
    _current_language = language
    load_translations(language)


def get_language() -> str:
    """Get the current language code.
    
    Returns:
        Current language code
    """
    return _current_language


def t(key: str, **kwargs) -> str:
    """Translate a key to the current language.
    
    Args:
        key: Translation key (e.g., 'ui.start_processing' or 'folders.vietnamese_audio')
        **kwargs: Format arguments for the translation string
    
    Returns:
        Translated string, or key if translation not found
    """
    translations = load_translations(_current_language)
    
    # Handle nested keys (e.g., 'folders.vietnamese_audio')
    keys = key.split('.')
    text = translations
    for k in keys:
        if isinstance(text, dict):
            text = text.get(k)
            if text is None:
                # Key not found, return original key
                return key
        else:
            # Not a dict, can't continue
            return key
    
    # If text is still a dict, it means we didn't find the final value
    if isinstance(text, dict):
        return key
    
    # Format with kwargs if provided
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            logger.warning(f"Failed to format translation key '{key}' with kwargs {kwargs}")
    
    return text


def get_supported_languages() -> Dict[str, str]:
    """Get dictionary of supported languages.
    
    Returns:
        Dictionary mapping language codes to language names
    """
    return SUPPORTED_LANGUAGES.copy()

