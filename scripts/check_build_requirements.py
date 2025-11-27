"""
Script kiểm tra requirements trước khi build
"""
import sys
import subprocess

def check_package(package_name, import_name=None):
    """Kiểm tra package có được cài đặt không"""
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        print(f"✅ {package_name} ({import_name}): OK")
        return True
    except ImportError:
        print(f"❌ {package_name} ({import_name}): NOT FOUND")
        return False

def install_package(package_name):
    """Cài đặt package"""
    print(f"📦 Đang cài đặt {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ Đã cài đặt {package_name}")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ Không thể cài đặt {package_name}")
        return False

def main():
    """Kiểm tra tất cả requirements"""
    print("=" * 60)
    print("🔍 Kiểm tra Requirements cho Build")
    print("=" * 60)
    print()
    
    # Danh sách packages cần kiểm tra
    packages = [
        ("ffmpeg-python", "ffmpeg"),  # Package name, import name
        ("psutil", "psutil"),
        ("pyinstaller", "PyInstaller"),
    ]
    
    all_ok = True
    for package_name, import_name in packages:
        if not check_package(package_name, import_name):
            all_ok = False
            response = input(f"Cài đặt {package_name}? (y/n): ")
            if response.lower() == 'y':
                if not install_package(package_name):
                    all_ok = False
            else:
                all_ok = False
    
    print()
    print("=" * 60)
    if all_ok:
        print("✅ TẤT CẢ REQUIREMENTS ĐÃ SẴN SÀNG!")
        print("   Bạn có thể chạy: python build_complete.py")
    else:
        print("❌ THIẾU REQUIREMENTS!")
        print("   Vui lòng cài đặt các package còn thiếu trước khi build")
    print("=" * 60)

if __name__ == "__main__":
    main()

