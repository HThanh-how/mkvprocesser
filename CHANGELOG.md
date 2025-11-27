# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Reorganized project structure following Python package standards
- Entry points at root for backward compatibility
- CONTRIBUTING.md and CODE_OF_CONDUCT.md documentation
- LICENSE file (MIT)
- GitHub issue and PR templates
- CI/CD workflow template

### Changed
- Moved core modules to `src/mkvprocessor/`
- Moved GUI modules to `src/gui/`
- Moved build scripts to `scripts/`
- Moved utility scripts to `tools/`
- Updated all documentation to English

## [2.0.0] - 2024-XX-XX

### Added
- PySide6 GUI with full feature set
- Automatic video metadata detection and processing
- Multi-language support (Vietnamese, English, Chinese, etc.)
- Automatic subtitle extraction
- Smart file naming with metadata
- GitHub sync integration
- Auto-commit subtitles

### Changed
- Improved processing performance
- Optimized memory usage
- Enhanced error handling

## [1.0.0] - 2024-XX-XX

### Added
- Core MKV processing functionality
- Basic GUI with tkinter
- FFmpeg integration
- File organization features
