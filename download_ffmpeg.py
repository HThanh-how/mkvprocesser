"""
Script tự động tải và cài đặt FFmpeg
Hỗ trợ Windows, macOS, và Linux
"""
import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil
from pathlib import Path

# Cấu hình encoding UTF-8 cho stdout/stderr để tránh lỗi Unicode trên Windows
if sys.platform == "win32":
    try:
        # Thử cấu hình UTF-8
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # Fallback: dùng environment variable
        os.environ['PYTHONIOENCODING'] = 'utf-8'

# Map emoji sang text thay thế (fallback)
EMOJI_MAP = {
    "📥": "[Download]",
    "✅": "[OK]",
    "❌": "[ERROR]",
    "💡": "[TIP]",
    "🖥️": "[OS]",
    "⚠️": "[WARNING]",
    "📦": "[Extract]",
}

def safe_print(*args, **kwargs):
    """In text an toàn, thay thế emoji nếu không thể encode"""
    # Thay thế emoji trước khi in
    safe_args = []
    for arg in args:
        text = str(arg)
        for emoji, replacement in EMOJI_MAP.items():
            text = text.replace(emoji, replacement)
        safe_args.append(text)
    print(*safe_args, **kwargs)


def get_platform_info():
    """Lấy thông tin platform"""
    system = platform.system()
    machine = platform.machine()
    
    if system == "Windows":
        return "windows", "win64" if "64" in machine else "win32", ".zip"
    elif system == "Darwin":
        return "macos", "macos" + ("-arm64" if machine == "arm64" else "-intel"), ".zip"
    elif system == "Linux":
        return "linux", "linux64", ".tar.xz"
    else:
        return None, None, None


def download_ffmpeg_windows():
    """Tải FFmpeg cho Windows"""
    safe_print("📥 Đang tải FFmpeg cho Windows...")
    
    # URL FFmpeg Windows (build từ BtbN)
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    
    zip_path = Path("ffmpeg.zip")
    
    try:
        print(f"Đang tải từ: {url}")
        urllib.request.urlretrieve(url, zip_path)
        safe_print("✅ Đã tải xong!")
        
        # Giải nén
        safe_print("📦 Đang giải nén...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Tìm thư mục ffmpeg
        ffmpeg_dirs = [d for d in Path(".").iterdir() if d.is_dir() and "ffmpeg" in d.name.lower()]
        if ffmpeg_dirs:
            ffmpeg_dir = ffmpeg_dirs[0]
            bin_dir = ffmpeg_dir / "bin"
            
            # Copy vào thư mục local
            local_bin = Path("ffmpeg_bin")
            if local_bin.exists():
                shutil.rmtree(local_bin)
            local_bin.mkdir()
            
            # Copy các file cần thiết
            for exe in ["ffmpeg.exe", "ffprobe.exe"]:
                src = bin_dir / exe
                if src.exists():
                    shutil.copy2(src, local_bin / exe)
                    safe_print(f"✅ Đã copy {exe}")
            
            # Xóa file zip và thư mục giải nén
            zip_path.unlink()
            shutil.rmtree(ffmpeg_dir)
            
            safe_print(f"\n✅ FFmpeg đã được cài đặt tại: {local_bin.absolute()}")
            safe_print(f"\n💡 Để sử dụng, thêm vào PATH hoặc copy vào thư mục hệ thống:")
            print(f"   {local_bin.absolute()}")
            
            return True
        else:
            safe_print("❌ Không tìm thấy thư mục FFmpeg sau khi giải nén")
            return False
            
    except Exception as e:
        safe_print(f"❌ Lỗi khi tải/cài đặt FFmpeg: {e}")
        return False


def download_ffmpeg_linux():
    """Hướng dẫn cài FFmpeg cho Linux"""
    safe_print("📥 Hướng dẫn cài đặt FFmpeg cho Linux:")
    print("\nUbuntu/Debian:")
    print("  sudo apt update")
    print("  sudo apt install -y ffmpeg")
    print("\nFedora/RHEL:")
    print("  sudo dnf install -y ffmpeg")
    print("\nHoặc sử dụng snap:")
    print("  sudo snap install ffmpeg")
    
    # Thử cài tự động nếu có quyền
    response = input("\nBạn có muốn thử cài đặt tự động không? (y/n): ")
    if response.lower() == 'y':
        try:
            # Thử với apt
            if shutil.which("apt"):
                print("Đang cài đặt với apt...")
                subprocess.check_call(["sudo", "apt", "update"])
                subprocess.check_call(["sudo", "apt", "install", "-y", "ffmpeg"])
                safe_print("✅ Đã cài đặt FFmpeg thành công!")
                return True
            # Thử với dnf
            elif shutil.which("dnf"):
                print("Đang cài đặt với dnf...")
                subprocess.check_call(["sudo", "dnf", "install", "-y", "ffmpeg"])
                safe_print("✅ Đã cài đặt FFmpeg thành công!")
                return True
            else:
                safe_print("⚠️ Không tìm thấy package manager. Vui lòng cài đặt thủ công.")
                return False
        except subprocess.CalledProcessError:
            safe_print("❌ Không thể cài đặt tự động. Vui lòng cài đặt thủ công.")
            return False
    return False


def download_ffmpeg_macos():
    """Hướng dẫn cài FFmpeg cho macOS"""
    safe_print("📥 Hướng dẫn cài đặt FFmpeg cho macOS:")
    print("\nSử dụng Homebrew:")
    print("  brew install ffmpeg")
    
    # Thử cài tự động nếu có Homebrew
    if shutil.which("brew"):
        response = input("\nBạn có muốn thử cài đặt tự động với Homebrew không? (y/n): ")
        if response.lower() == 'y':
            try:
                print("Đang cài đặt với Homebrew...")
                subprocess.check_call(["brew", "install", "ffmpeg"])
                safe_print("✅ Đã cài đặt FFmpeg thành công!")
                return True
            except subprocess.CalledProcessError:
                safe_print("❌ Không thể cài đặt tự động. Vui lòng chạy: brew install ffmpeg")
                return False
    else:
        safe_print("\n⚠️ Homebrew chưa được cài đặt.")
        print("Cài đặt Homebrew:")
        print('  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
        return False


def add_to_path_windows(ffmpeg_path):
    """Thêm FFmpeg vào PATH trên Windows"""
    safe_print("\n💡 Để thêm FFmpeg vào PATH trên Windows:")
    print("1. Mở System Properties > Environment Variables")
    print(f"2. Thêm {ffmpeg_path} vào PATH")
    print("\nHoặc chạy lệnh PowerShell (với quyền Admin):")
    print(f'  [Environment]::SetEnvironmentVariable("Path", $env:Path + ";{ffmpeg_path}", "User")')


def main():
    """Hàm main"""
    print("=" * 60)
    safe_print("📥 FFmpeg Download & Install Script")
    print("=" * 60)
    
    system = platform.system()
    safe_print(f"\n🖥️  Hệ điều hành: {system}")
    print(f"   Architecture: {platform.machine()}\n")
    
    success = False
    
    if system == "Windows":
        success = download_ffmpeg_windows()
        if success:
            add_to_path_windows(Path("ffmpeg_bin").absolute())
    elif system == "Linux":
        success = download_ffmpeg_linux()
    elif system == "Darwin":
        success = download_ffmpeg_macos()
    else:
        safe_print(f"❌ Hệ điều hành {system} chưa được hỗ trợ tự động.")
        print("Vui lòng cài đặt FFmpeg thủ công từ: https://ffmpeg.org/download.html")
    
    if success:
        safe_print("\n✅ Hoàn thành!")
        print("\nKiểm tra FFmpeg:")
        print("  ffmpeg -version")
    else:
        safe_print("\n⚠️ Vui lòng cài đặt FFmpeg thủ công.")
        print("Xem hướng dẫn tại: https://ffmpeg.org/download.html")


if __name__ == "__main__":
    main()

