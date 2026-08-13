# 🤝 Contributing Guide

Thank you for your interest in contributing to MKV Video Processing Toolkit!

## 📋 How to Contribute

### 🐛 Bug Reports

If you find a bug, please:
1. Check if the bug has already been reported in [Issues](https://github.com/your-repo/issues)
2. Create a new issue with:
   - Clear description of the bug
   - Steps to reproduce
   - Environment information (OS, Python version, FFmpeg version)
   - Log/error messages if available

### 💡 Feature Requests

We welcome all suggestions! Please:
1. Check if the feature has already been requested
2. Create an issue with label "enhancement"
3. Describe the feature and use case in detail

### 🔧 Contributing Code

#### Process

1. **Fork repository**
   ```bash
   git clone https://github.com/your-username/script-extract-video.git
   cd script-extract-video
   ```

2. **Create a new branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Set up development environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -e ".[all,dev]"
   ```

4. **Write code**
   - Follow style guide (PEP 8)
   - Add comments/docstrings for functions/classes
   - Write tests if possible

5. **Test code**
   ```bash
   ruff check src tests
   pytest
   ```

6. **Commit changes**
   ```bash
   git add .
   git commit -m "feat: add feature X"
   # or
   git commit -m "fix: fix bug Y"
   ```

7. **Push and create Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```

#### Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation update
- `style:` - Formatting, no logic change
- `refactor:` - Code refactoring
- `test:` - Add/update tests
- `chore:` - Build/dependency updates

#### Code Style

- Follow PEP 8
- Use type hints when possible
- Docstrings for public functions/classes
- Clear, meaningful variable/function names

#### Versioning — hai artifact, hai scheme (co chu y)

Repo nay xuat ban hai thu khac nhau, moi thu co so phien ban rieng. Day
**khong** phai loi lech version:

| Artifact | Nguon phien ban | Vi du | Ai doc |
|---|---|---|---|
| Package `mkvtools` (pip, CLI, web GUI) | `pyproject.toml` + `mkvtools.__version__` | `3.0.0` | SemVer, nguoi cai bang pip |
| `MKVProcessor.exe` (PySide6 desktop, legacy) | `version.txt`, sinh tu git tag khi build | `1.11.28.12` | Bo tu dong cap nhat trong exe |

`version.txt` do `scripts/build_complete.py` ghi de tu git tag luc build; ban
commit trong repo chi la fallback khi chay tu source. **Dung sua tay** de dong
bo hai con so — bo cap nhat cua exe so sanh `version.txt` voi tag GitHub
release, doi thanh `3.0.0` se lam moi ban exe dang chay tu cho la co ban moi.

### 📝 Updating Documentation

Improving README, adding examples, or writing tutorials are all welcome!

## ✅ Checklist Before Submitting PR

- [ ] Code has been tested
- [ ] No linter errors
- [ ] Documentation updated if needed
- [ ] Clear commit messages
- [ ] Code follows style guide

## 🙏 Thank You!

All contributions are greatly appreciated!
