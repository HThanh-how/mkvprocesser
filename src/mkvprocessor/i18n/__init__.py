"""
Internationalization (i18n) support for MKV Processor.

Provides translation functionality with language switching support.
"""
import json
import logging
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


def get_translations_dir() -> Path:
    """Get the translations directory path.
    
    Returns:
        Path to translations directory
    """
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
    
    if not translation_file.exists():
        logger.warning(f"Translation file not found: {translation_file}, using English")
        language = DEFAULT_LANGUAGE
        translation_file = translations_dir / f"{language}.json"
    
    try:
        with open(translation_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
        _translations[language] = translations
        return translations
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load translations for {language}: {e}")
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

