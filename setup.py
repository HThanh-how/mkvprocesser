"""
Script setup tự động - Cài đặt tất cả dependencies một lần
"""
import os
import sys
import subprocess
import platform


def check_python_version():
    """Kiểm tra phiên bản Python"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Cần Python 3.8 trở lên!")
        print(f"   Phiên bản hiện tại: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def install_python_packages():
    """Cài đặt các package Python"""
    print("\n📦 Đang cài đặt các package Python...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--upgrade"
        ])
        print("✅ Đã cài đặt các package Python thành công!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi khi cài đặt: {e}")
        return False


def check_ffmpeg():
    """Kiểm tra FFmpeg"""
    print("\n🔍 Đang kiểm tra FFmpeg...")
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg đã được cài đặt: {version_line}")
            return True
        else:
            print("❌ FFmpeg chưa được cài đặt")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg chưa được cài đặt")
        return False


def main():
    """Hàm main"""
    print("=" * 60)
    print("🔧 MKV Processor - Setup Script")
    print("=" * 60)
    
    # Kiểm tra Python
    if not check_python_version():
        return
    
    # Cài đặt Python packages
    if not install_python_packages():
        print("\n❌ Không thể cài đặt packages. Vui lòng kiểm tra kết nối internet.")
        return
    
    # Kiểm tra FFmpeg
    ffmpeg_installed = check_ffmpeg()
    
    if not ffmpeg_installed:
        print("\n⚠️ FFmpeg chưa được cài đặt!")
        print("\nBạn có 2 lựa chọn:")
        print("1. Chạy script tự động tải FFmpeg:")
        print("   python download_ffmpeg.py")
        print("\n2. Cài đặt thủ công:")
        system = platform.system()
        if system == "Windows":
            print("   - Tải từ: https://ffmpeg.org/download.html")
            print("   - Hoặc: choco install ffmpeg")
        elif system == "Darwin":
            print("   - brew install ffmpeg")
        elif system == "Linux":
            print("   - sudo apt install ffmpeg")
            print("   - hoặc: sudo dnf install ffmpeg")
    
    print("\n" + "=" * 60)
    print("✅ Setup hoàn tất!")
    print("=" * 60)
    print("\nBạn có thể:")
    print("1. Chạy GUI: python gui.py")
    print("2. Chạy command line: python script.py")
    print("3. Build executable: python build.py")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

