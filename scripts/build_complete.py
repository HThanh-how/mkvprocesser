"""
Script build HOÀN CHỈNH - Tự động tải FFmpeg và bundle vào package
Tạo ra 1 package duy nhất, không cần cài gì thêm!
"""
import os
import sys
import re
import importlib
import platform
import subprocess
import shutil
import urllib.request
import zipfile
from pathlib import Path


def ensure_utf8_output():
    """Đảm bảo stdout/stderr hỗ trợ UTF-8 (fix lỗi emoji trên Windows CI)."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass


ensure_utf8_output()


def get_build_version() -> str:
    """
    Get version following the same format as GitHub Actions workflow.
    
    Format:
    - If git tag v* exists: use tag (without v prefix)
    - If on main/master: (YEAR-2024).MM.DD.BUILD_NUMBER
    - Otherwise: (YEAR-2024).MM.DD.beta-BUILD_NUMBER
    
    Examples:
    - 2025.11.28 → 1.11.28.xx (2025 - 2024 = 1)
    - 2026.10.11 → 2.10.11.xx (2026 - 2024 = 2)
    
    Where:
    - YEAR-2024 = current year minus 2024
    - MM.DD = current month.day (UTC)
    - BUILD_NUMBER = from GITHUB_RUN_NUMBER env or 1
    """
    import subprocess
    import os
    from datetime import datetime
    
    project_root = Path(__file__).parent.parent
    
    # 1. Check if we're on a git tag (v*)
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_root
        )
        if result.returncode == 0:
            tag = result.stdout.strip().lstrip('vV')
            if tag:
                return tag
    except Exception:
        pass
    
    # 2. Check current git branch
    branch = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_root
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass
    
    # 3. Get build number from environment (GitHub Actions) or use 1
    build_number = os.environ.get("GITHUB_RUN_NUMBER", "1")
    try:
        build_number = str(int(build_number))
    except ValueError:
        build_number = "1"
    
    # 4. Get year segment (YEAR - 2024) and date segment (MM.DD in UTC)
    # Use timezone-aware datetime (replaces deprecated utcnow())
    from datetime import timezone
    now = datetime.now(timezone.utc)
    year_seg = now.year - 2024  # 2025 → 1, 2026 → 2, etc.
    date_seg = now.strftime("%m.%d")  # MM.DD
    
    # 5. Determine if main/master branch
    is_main = branch in ("main", "master")
    
    # 6. Create version: (YEAR-2024).MM.DD.BUILD_NUMBER
    if is_main:
        version = f"{year_seg}.{date_seg}.{build_number}"
    else:
        version = f"{year_seg}.{date_seg}.beta-{build_number}"
    
    return version


def get_platform_spec():
    """Lấy thông tin platform"""
    system = platform.system()
    machine = platform.machine().lower()
    
    if system == "Windows":
        # Kiểm tra architecture chính xác hơn
        if "64" in machine or "amd64" in machine or "x86_64" in machine:
            arch = "x64"
        else:
            arch = "x86"
        return "win", "exe", arch
    elif system == "Darwin":
        # macOS: kiểm tra architecture
        try:
            # Kiểm tra uname -m hoặc sysctl
            result = subprocess.run(['uname', '-m'], capture_output=True, text=True)
            if result.returncode == 0:
                uname_m = result.stdout.strip().lower()
                if 'arm' in uname_m or 'aarch64' in uname_m:
                    arch = "arm64"
                else:
                    arch = "x64"
            else:
                # Fallback: dựa vào machine
                if machine == "arm64" or "arm" in machine.lower():
                    arch = "arm64"
                else:
                    arch = "x64"
        except:
            # Fallback cuối cùng
            if machine == "arm64" or "arm" in machine.lower():
                arch = "arm64"
            else:
                arch = "x64"
        return "mac", "app", arch
    elif system == "Linux":
        if "arm" in machine or "aarch64" in machine:
            arch = "arm64"
        else:
            arch = "x64"
        return "linux", "bin", arch
    else:
        return "unknown", "bin", "unknown"


def download_ffmpeg_windows():
    """Tải FFmpeg cho Windows và giải nén"""
    print("\n📥 Đang tải FFmpeg cho Windows...")
    
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_path = Path("ffmpeg_temp.zip")
    ffmpeg_bin_dir = Path("ffmpeg_bin")
    
    try:
        print(f"Đang tải từ: {url}")
        urllib.request.urlretrieve(url, zip_path)
        print("✅ Đã tải xong!")
        
        # Giải nén
        print("📦 Đang giải nén...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Tìm và copy FFmpeg
        ffmpeg_dirs = [d for d in Path(".").iterdir() if d.is_dir() and "ffmpeg" in d.name.lower()]
        if ffmpeg_dirs:
            ffmpeg_dir = ffmpeg_dirs[0]
            bin_dir = ffmpeg_dir / "bin"
            
            # Tạo thư mục ffmpeg_bin
            if ffmpeg_bin_dir.exists():
                shutil.rmtree(ffmpeg_bin_dir)
            ffmpeg_bin_dir.mkdir()
            
            # Copy các file cần thiết
            for exe in ["ffmpeg.exe", "ffprobe.exe"]:
                src = bin_dir / exe
                if src.exists():
                    shutil.copy2(src, ffmpeg_bin_dir / exe)
                    print(f"✅ Đã copy {exe}")
            
            # Dọn dẹp
            zip_path.unlink()
            shutil.rmtree(ffmpeg_dir)
            
            print(f"✅ FFmpeg đã được tải và sẵn sàng tại: {ffmpeg_bin_dir.absolute()}")
            return True
        else:
            print("❌ Không tìm thấy FFmpeg sau khi giải nén")
            return False
            
    except Exception as e:
        print(f"❌ Lỗi khi tải FFmpeg: {e}")
        return False


def check_ffmpeg_local():
    """Kiểm tra FFmpeg đã có local chưa"""
    ffmpeg_bin_dir = Path(__file__).parent.parent / "ffmpeg_bin"
    system = platform.system()
    
    if system == "Windows":
        ffmpeg_exe = ffmpeg_bin_dir / "ffmpeg.exe"
    else:
        ffmpeg_exe = ffmpeg_bin_dir / "ffmpeg"
    
    return ffmpeg_exe.exists()


def remove_old_executable():
    """Xóa hoặc đổi tên file exe cũ nếu đang được sử dụng"""
    platform_name, ext, arch = get_platform_spec()
    exe_name = "MKVProcessor"
    if platform_name == "win":
        exe_name += ".exe"
    elif platform_name == "mac":
        exe_name += ".app"
    
    exe_path = Path("dist") / exe_name
    
    if not exe_path.exists():
        return True
    
    print(f"⚠️ Phát hiện file cũ: {exe_path}")
    
    # Thử xóa file
    try:
        exe_path.unlink()
        print(f"✅ Đã xóa file cũ: {exe_name}")
        return True
    except PermissionError:
        # File đang được sử dụng, thử đổi tên
        try:
            backup_name = f"{exe_name}.old"
            backup_path = Path("dist") / backup_name
            if backup_path.exists():
                backup_path.unlink()
            exe_path.rename(backup_path)
            print(f"✅ Đã đổi tên file cũ thành: {backup_name}")
            return True
        except Exception as e:
            print(f"❌ Không thể xóa hoặc đổi tên file cũ: {e}")
            print(f"💡 Vui lòng đóng ứng dụng {exe_name} nếu đang chạy và thử lại.")
            return False
    except Exception as e:
        print(f"❌ Lỗi khi xử lý file cũ: {e}")
        return False


def build_executable():
    """Build executable với PyInstaller"""
    platform_name, ext, arch = get_platform_spec()
    
    print(f"\n🔨 Bắt đầu build cho {platform_name} ({arch})...")
    
    # Xóa file exe cũ trước khi build
    if not remove_old_executable():
        print("❌ Không thể xóa file cũ. Build bị hủy.")
        return False
    
    output_name = "MKVProcessor"
    
    # Tùy chọn PyInstaller - sử dụng python -m PyInstaller để tránh lỗi PATH
    # KHÔNG dùng --add-data cho script.py và ffmpeg_helper.py vì chúng sẽ tự bundle khi import
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"
    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--name", output_name,
        "--onefile",  # 1 file duy nhất
        "--windowed",  # GUI mode
        "--additional-hooks-dir", str(project_root / "hooks"),  # Sử dụng hook files
        "--paths", str(src_dir),  # đảm bảo PyInstaller tìm được packages trong src
        "--paths", str(project_root),  # Thêm project root để tìm gui_pyside.py
    ]
    
    # Bundle FFmpeg vào executable (sẽ extract tự động khi chạy)
    if check_ffmpeg_local():
        ffmpeg_bin_dir = (Path(__file__).parent.parent / "ffmpeg_bin").absolute()
        # Bundle FFmpeg vào executable, sẽ extract vào thư mục tạm khi chạy
        if platform_name == "win":
            pyinstaller_args.extend([
                "--add-data", f"{ffmpeg_bin_dir}{os.pathsep}ffmpeg_bin"
            ])
        else:
            pyinstaller_args.extend([
                "--add-data", f"{ffmpeg_bin_dir}{os.pathsep}ffmpeg_bin"
            ])
        print("✅ Sẽ bundle FFmpeg vào executable (sẽ extract tự động khi chạy)")
    else:
        print("⚠️ Không tìm thấy FFmpeg local, sẽ cần cài đặt riêng")
    
    # Bundle Git portable nếu có
    git_portable_dir = (Path(__file__).parent.parent / "git_portable").absolute()
    git_exe = git_portable_dir / "bin" / ("git.exe" if platform_name == "win" else "git")
    if git_exe.exists():
        pyinstaller_args.extend([
            "--add-data", f"{git_portable_dir}{os.pathsep}git_portable"
        ])
        print("✅ Sẽ bundle Git portable vào executable (auto-commit không cần cài Git)")
    else:
        print("ℹ️ Không tìm thấy git_portable/. Bỏ qua bundle Git (auto-commit yêu cầu Git hệ thống).")

    # Hidden imports - đảm bảo bundle đầy đủ
    # QUAN TRỌNG: ffmpeg-python package được cài với tên "ffmpeg-python" nhưng import là "ffmpeg"
    hidden_imports = [
        # PySide6 - QUAN TRỌNG: Phải bundle PySide6 và các submodules chính
        "PySide6",
        "PySide6.QtCore", "PySide6.QtWidgets", "PySide6.QtGui",
        "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtQml",
        # ffmpeg-python package - bundle đầy đủ TẤT CẢ modules
        # Chỉ thêm các modules thực sự tồn tại (kiểm tra bằng python -c "import ffmpeg; print(dir(ffmpeg))")
        "ffmpeg",
        "ffmpeg._run", "ffmpeg._probe", "ffmpeg.nodes", "ffmpeg._ffmpeg",
        "ffmpeg._utils", "ffmpeg._filters", "ffmpeg._view", "ffmpeg.dag",
        # psutil package - bundle đầy đủ
        "psutil", "psutil._common", "psutil._pswindows", "psutil._psutil_windows",
        "psutil._psutil_linux", "psutil._psutil_osx",
        # tkinter - GUI
        "tkinter", "tkinter.ttk",
        "tkinter.filedialog", "tkinter.scrolledtext", "tkinter.messagebox",
        # Custom modules
        "legacy_cli_entry", "mkvprocessor.legacy_api", "mkvprocessor.ffmpeg_helper",
        # GUI package - Explicitly include to avoid shadowing issues
        "gui", "gui.gui_pyside_app", "gui.gui_pyside_app.main_window",
    ]
    for imp in hidden_imports:
        pyinstaller_args.extend(["--hidden-import", imp])
    
    # Collect-submodules để bundle TẤT CẢ submodules (QUAN TRỌNG!)
    # Điều này đảm bảo bundle đầy đủ các module con của ffmpeg, psutil và PySide6
    pyinstaller_args.extend(["--collect-submodules", "ffmpeg"])
    pyinstaller_args.extend(["--collect-submodules", "psutil"])
    pyinstaller_args.extend(["--collect-submodules", "PySide6"])  # QUAN TRỌNG: Bundle PySide6 submodules
    
    # Collect-all để bundle toàn bộ package (có thể có warnings nhưng không sao)
    # Warnings về "not a package" là bình thường, PyInstaller vẫn bundle qua hidden-import
    # QUAN TRỌNG: PySide6 cần collect-all để bundle cả binaries (DLLs trên Windows)
    pyinstaller_args.extend(["--collect-all", "ffmpeg"])
    pyinstaller_args.extend(["--collect-all", "psutil"])
    pyinstaller_args.extend(["--collect-all", "PySide6"])  # QUAN TRỌNG: Bundle PySide6 + binaries
    
    # QUAN TRỌNG: Bundle gui package
    # PyInstaller sẽ tự động bundle khi thấy import trong gui_pyside.py
    # Với --paths src/, PyInstaller sẽ tìm được package gui trong src/gui
    # Chỉ dùng --collect-submodules, KHÔNG dùng --collect-all vì gây warnings
    # Package sẽ được bundle qua --add-data (dòng 389-391)
    pyinstaller_args.extend(["--collect-submodules", "gui"])
    
    # QUAN TRỌNG: Đảm bảo import ffmpeg ngay từ đầu trong gui.py
    # PyInstaller sẽ tự động bundle nếu thấy import statement
    
    # macOS specific
    if platform_name == "mac":
        pyinstaller_args.extend([
            "--osx-bundle-identifier", "com.mkvprocessor.app"
        ])
    
    # Đảm bảo legacy_cli_entry.py được copy dưới dạng data để fallback
    script_path = Path(__file__).parent.parent / "legacy_cli_entry.py"
    if script_path.exists():
        pyinstaller_args.extend(["--add-data", f"{script_path.absolute()}{os.pathsep}."])

    # Tạo file version.txt với version từ git tag hoặc GitHub
    version = get_build_version()
    version_file = Path(__file__).parent.parent / "version.txt"
    version_file.write_text(version, encoding='utf-8')
    print(f"📝 Version: {version}")
    # Bundle version.txt vào executable
    pyinstaller_args.extend(["--add-data", f"{version_file.absolute()}{os.pathsep}."])

    # QUAN TRỌNG: Bundle toàn bộ src/gui package bằng --add-data
    # PyInstaller có thể không tự động bundle package trong src/
    gui_package_dir = project_root / "src" / "gui"
    if gui_package_dir.exists():
        # Bundle toàn bộ gui package
        pyinstaller_args.extend([
            "--add-data", f"{gui_package_dir.absolute()}{os.pathsep}gui"
        ])
        print("✅ Sẽ bundle gui package vào executable")
    
    # QUAN TRỌNG: Bundle translation files
    translations_dir = project_root / "src" / "mkvprocessor" / "i18n" / "translations"
    if translations_dir.exists():
        # Bundle translation files
        pyinstaller_args.extend([
            "--add-data", f"{translations_dir.absolute()}{os.pathsep}mkvprocessor/i18n/translations"
        ])
        print("✅ Sẽ bundle translation files vào executable")
    
    # Dùng GUI PySide6 mới
    gui_pyside_path = Path(__file__).parent.parent / "gui_pyside.py"
    pyinstaller_args.append(str(gui_pyside_path))
    
    try:
        print(f"\nChạy PyInstaller...")
        subprocess.check_call(pyinstaller_args)
        print("\n✅ Build thành công!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Lỗi khi build: {e}")
        return False


def create_portable_package():
    """Tạo package - CHỈ 1 FILE EXE DUY NHẤT"""
    platform_name, ext, arch = get_platform_spec()
    
    print("\n📦 Tạo package - CHỈ 1 FILE DUY NHẤT...")
    print("   (FFmpeg đã được bundle vào trong executable)")
    
    # Tìm executable
    exe_name = "MKVProcessor"
    if platform_name == "win":
        exe_name += ".exe"
    elif platform_name == "mac":
        exe_name += ".app"
    
    exe_path = Path("dist") / exe_name
    if not exe_path.exists():
        # Thử tìm file khác trong dist
        dist_files = list(Path("dist").glob("MKVProcessor*"))
        if dist_files:
            exe_path = dist_files[0]
    
    if not exe_path.exists():
        print(f"❌ Không tìm thấy executable tại {exe_path}")
        return False
    
    # Tính kích thước
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    
    print(f"\n✅ Đã tạo 1 FILE DUY NHẤT!")
    print(f"   📁 File: {exe_path.absolute()}")
    print(f"   📦 Kích thước: {size_mb:.2f} MB")
    print(f"\n💡 Bạn có thể:")
    print(f"   1. Copy file {exe_name} vào bất kỳ đâu")
    print(f"   2. Chạy trực tiếp - KHÔNG CẦN FILE NÀO KHÁC!")
    print(f"   3. FFmpeg đã được bundle bên trong, sẽ extract tự động khi chạy")
    
    return True
    
    # Tạo README
    readme_content = f"""# 🎬 MKV Processor - Portable Package

## ✨ Package hoàn chỉnh - Không cần cài đặt gì!

### 🚀 Cách sử dụng:

1. **Giải nén** package này vào bất kỳ đâu
2. **Chạy file** {exe_name}
3. **Chọn thư mục** chứa file MKV
4. **Bắt đầu xử lý** - XONG!

### ✅ Đã bao gồm:

- ✅ Executable (đã bundle Python và dependencies)
- ✅ FFmpeg (không cần cài đặt)
- ✅ Tất cả thư viện cần thiết

### 💡 Lưu ý:

- Không cần cài Python
- Không cần cài FFmpeg
- Không cần cài dependencies
- Chỉ cần double-click và chạy!

### 📋 Yêu cầu hệ thống:

- RAM: Tối thiểu 4GB (khuyến nghị 8GB+)
- Ổ đĩa: Dung lượng trống >= 2x kích thước file video lớn nhất
- OS: {platform_name} {arch}

### 🐛 Xử lý lỗi:

Nếu gặp lỗi, kiểm tra:
1. Đủ dung lượng ổ đĩa
2. Đủ RAM
3. File MKV hợp lệ

---
Platform: {platform_name}
Architecture: {arch}
Build date: {platform.system()} {platform.release()}
"""
    
    readme_path = package_dir / "README.txt"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    # Tính kích thước
    total_size = sum(f.stat().st_size for f in package_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)
    
    print(f"\n✅ Package hoàn chỉnh đã được tạo!")
    print(f"   📁 Vị trí: {package_dir.absolute()}")
    print(f"   📦 Kích thước: {size_mb:.2f} MB")
    print(f"\n💡 Bạn có thể:")
    print(f"   1. Copy thư mục {package_name} vào USB")
    print(f"   2. Chia sẻ cho người khác")
    print(f"   3. Chạy trên bất kỳ máy {platform_name} nào (không cần cài đặt!)")
    
    return True


IMPORT_MAP = {
    "ffmpeg-python": "ffmpeg",
    "pyside6": "PySide6",
    "pyinstaller": "PyInstaller",
}


def parse_requirements():
    reqs = []
    req_file = Path(__file__).parent.parent / "requirements.txt"
    if not req_file.exists():
        return reqs
    for line in req_file.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        pkg = re.split(r"[<>=!~]", line)[0].strip()
        if pkg and pkg not in reqs:
            reqs.append(pkg)
    return reqs


def check_dependency(pkg_name):
    module_name = IMPORT_MAP.get(pkg_name.lower(), pkg_name)
    if not module_name:
        module_name = pkg_name
    try:
        importlib.import_module(module_name)
        print(f"✅ {pkg_name}: OK")
        return True
    except ImportError:
        print(f"❌ {pkg_name}: NOT FOUND")
        return False


def main():
    """Hàm main"""
    print("=" * 70)
    print("🔨 MKV Processor - Build Complete Package")
    print("=" * 70)
    print("\n✨ Tạo package HOÀN CHỈNH - Không cần cài đặt gì!")
    print("   (Bao gồm: Executable + FFmpeg + Dependencies)\n")
    
    platform_name, ext, arch = get_platform_spec()
    print(f"🖥️  Platform: {platform_name} ({arch})")
    
    # Kiểm tra xem đang chạy trong CI/CD không (không có stdin)
    is_ci = os.getenv('CI') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true'
    
    # Kiểm tra dependencies trước khi build
    print("\n🔍 Kiểm tra dependencies...")
    missing_deps = []
    
    required_packages = parse_requirements()
    dependencies = []
    for pkg in required_packages:
        dependencies.append(pkg)
    if "pyinstaller" not in [pkg.lower() for pkg in dependencies]:
        dependencies.append("pyinstaller")

    missing_deps = []
    checked = set()
    for pkg in dependencies:
        key = pkg.lower()
        if key in checked:
            continue
        checked.add(key)
        if not check_dependency(pkg):
            missing_deps.append(pkg)
    
    # Nếu thiếu dependencies, cài đặt hoặc thoát
    if missing_deps:
        print(f"\n⚠️ Thiếu {len(missing_deps)} dependencies: {', '.join(missing_deps)}")
        if is_ci:
            print("Đang tự động cài đặt...")
            for dep in missing_deps:
                subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
        else:
            response = input("Tự động cài đặt? (y/n): ")
            if response.lower() == 'y':
                for dep in missing_deps:
                    print(f"Đang cài đặt {dep}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            else:
                print("❌ Cần cài đặt dependencies trước khi build. Thoát.")
                print("   Chạy: pip install -r requirements.txt")
                return
    
    # Tải FFmpeg nếu chưa có
    if not check_ffmpeg_local():
        print("\n📥 FFmpeg chưa có local.")
        if platform_name == "win":
            if is_ci:
                print("Đang tự động tải FFmpeg cho Windows...")
                if not download_ffmpeg_windows():
                    print("❌ Không thể tải FFmpeg. Thoát.")
                    return
            else:
                response = input("Tự động tải FFmpeg cho Windows? (y/n): ")
                if response.lower() == 'y':
                    if not download_ffmpeg_windows():
                        print("⚠️ Không thể tải FFmpeg. Bạn có thể:")
                        print("   1. Chạy python download_ffmpeg.py trước")
                        print("   2. Hoặc cài FFmpeg thủ công")
                        response = input("Tiếp tục build không? (y/n): ")
                        if response.lower() != 'y':
                            return
        else:
            if is_ci:
                print(f"⚠️ FFmpeg cần được cài đặt trong CI cho {platform_name}")
                print("   (Nên được cài trong workflow)")
            else:
                print(f"⚠️ FFmpeg cần được cài đặt thủ công cho {platform_name}")
                print("   Hoặc copy vào thư mục ffmpeg_bin/")
                response = input("Tiếp tục build không? (y/n): ")
                if response.lower() != 'y':
                    return
    
    # Build executable
    if build_executable():
        # Tìm file exe đã build
        exe_name = "MKVProcessor"
        if platform_name == "win":
            exe_name += ".exe"
        elif platform_name == "mac":
            exe_name += ".app"
        
        exe_path = Path("dist") / exe_name
        if not exe_path.exists():
            # Thử tìm file khác trong dist
            dist_files = list(Path("dist").glob("MKVProcessor*"))
            if dist_files:
                exe_path = dist_files[0]
                exe_name = exe_path.name
        
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print("\n" + "=" * 70)
            print("✅ HOÀN THÀNH!")
            print("=" * 70)
            print("\n🎉 Bạn đã có 1 FILE EXE DUY NHẤT!")
            print(f"   📁 File: {exe_path.absolute()}")
            print(f"   📦 Kích thước: {size_mb:.2f} MB")
            print("\n💡 Chỉ cần copy file này và chia sẻ.")
            print("✅ Người dùng chỉ cần double-click - KHÔNG CẦN CÀI ĐẶT GÌ!")
            print("✅ FFmpeg đã được bundle bên trong, extract tự động khi chạy")
            
            # Đề xuất test
            print("\n" + "=" * 70)
            print("🧪 TEST EXECUTABLE")
            print("=" * 70)
            print("💡 Để test executable, chạy:")
            print("   python test_build.py")
            print("\n   Hoặc test thủ công:")
            print(f"   1. Chạy: {exe_path.name}")
            print("   2. Kiểm tra GUI có mở được không")
            print("   3. Kiểm tra 'FFmpeg: OK' và 'RAM: OK'")
            print("   4. Test xử lý file MKV thật")
        else:
            print("\n⚠️ Build executable thành công nhưng không tìm thấy file output.")
    else:
        print("\n❌ Build thất bại.")


if __name__ == "__main__":
    main()

