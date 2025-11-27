"""
Script test executable sau khi build
Kiểm tra xem executable có chạy được và có đầy đủ dependencies không
"""
import sys
import os
import subprocess
import time
from pathlib import Path
import platform


def get_platform_exe_name():
    """Lấy tên file exe theo platform"""
    system = platform.system().lower()
    if system == "windows":
        return "MKVProcessor.exe"
    elif system == "darwin":
        return "MKVProcessor.app"
    else:
        return "MKVProcessor"


def find_executable():
    """Tìm file executable"""
    exe_name = get_platform_exe_name()
    
    # Tìm trong dist/
    dist_path = Path("dist") / exe_name
    if dist_path.exists():
        return dist_path
    
    # Tìm bất kỳ file nào trong dist/
    dist_dir = Path("dist")
    if dist_dir.exists():
        files = list(dist_dir.glob("MKVProcessor*"))
        if files:
            return files[0]
    
    return None


def check_file_exists(exe_path):
    """Kiểm tra file có tồn tại không"""
    print("=" * 70)
    print("📁 Kiểm tra File Executable")
    print("=" * 70)
    
    if exe_path and exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"✅ Tìm thấy file: {exe_path}")
        print(f"   📦 Kích thước: {size_mb:.2f} MB")
        
        if size_mb < 30:
            print("   ⚠️ File quá nhỏ - có thể thiếu dependencies")
            return False
        elif size_mb > 200:
            print("   ⚠️ File quá lớn - có thể bundle thừa")
        else:
            print("   ✅ Kích thước hợp lý (30-200MB)")
        
        return True
    else:
        print(f"❌ Không tìm thấy file executable!")
        print(f"   Đã tìm trong: dist/")
        return False


def test_imports_in_exe(exe_path):
    """Test xem executable có import được dependencies không"""
    print("\n" + "=" * 70)
    print("🧪 Test Import Dependencies trong Executable")
    print("=" * 70)
    
    # Tạo script test đơn giản
    test_script = """
import sys
import os

# Test import ffmpeg
try:
    import ffmpeg
    print("✅ ffmpeg: OK")
except ImportError as e:
    print(f"❌ ffmpeg: FAILED - {e}")
    sys.exit(1)

# Test import psutil
try:
    import psutil
    print("✅ psutil: OK")
except ImportError as e:
    print(f"❌ psutil: FAILED - {e}")
    sys.exit(1)

# Test import script
try:
    from script import main
    print("✅ script: OK")
except ImportError as e:
    print(f"❌ script: FAILED - {e}")
    sys.exit(1)

# Test import ffmpeg_helper
try:
    from ffmpeg_helper import check_ffmpeg_available
    print("✅ ffmpeg_helper: OK")
except ImportError as e:
    print(f"❌ ffmpeg_helper: FAILED - {e}")
    sys.exit(1)

print("\\n✅ TẤT CẢ IMPORTS THÀNH CÔNG!")
"""
    
    # Lưu script test tạm thời
    test_file = Path("test_imports_temp.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_script)
    
    try:
        # Chạy executable với script test
        # Lưu ý: Executable là GUI, không thể chạy script trực tiếp
        # Nên chỉ test xem có chạy được không
        print("⚠️ Không thể test import trực tiếp trong GUI executable")
        print("   (Executable là GUI, không có console mode)")
        print("   → Sẽ test bằng cách chạy executable và xem có lỗi không")
        return True
    finally:
        # Xóa file test
        if test_file.exists():
            test_file.unlink()


def test_executable_run(exe_path):
    """Test xem executable có chạy được không"""
    print("\n" + "=" * 70)
    print("🚀 Test Chạy Executable")
    print("=" * 70)
    
    system = platform.system().lower()
    
    try:
        if system == "windows":
            # Windows: Chạy và đợi một chút rồi kill
            print(f"Đang chạy: {exe_path}")
            print("   (Sẽ tự động đóng sau 3 giây để test)")
            
            process = subprocess.Popen(
                [str(exe_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # Đợi một chút
            time.sleep(3)
            
            # Kiểm tra process còn chạy không
            if process.poll() is None:
                print("✅ Executable đã khởi động thành công!")
                print("   (Process đang chạy - không có lỗi khởi động)")
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
                return True
            else:
                # Process đã thoát
                stdout, stderr = process.communicate()
                if stderr:
                    error_msg = stderr.decode('utf-8', errors='ignore')
                    print(f"❌ Executable đã thoát với lỗi:")
                    print(f"   {error_msg[:500]}")
                    return False
                else:
                    print("⚠️ Executable đã thoát (có thể là bình thường nếu không có GUI)")
                    return True
        else:
            # Linux/Mac: Tương tự
            print(f"Đang chạy: {exe_path}")
            process = subprocess.Popen(
                [str(exe_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            time.sleep(3)
            
            if process.poll() is None:
                print("✅ Executable đã khởi động thành công!")
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
                return True
            else:
                stdout, stderr = process.communicate()
                if stderr:
                    error_msg = stderr.decode('utf-8', errors='ignore')
                    print(f"❌ Executable đã thoát với lỗi:")
                    print(f"   {error_msg[:500]}")
                    return False
                else:
                    print("⚠️ Executable đã thoát")
                    return True
                    
    except Exception as e:
        print(f"❌ Lỗi khi chạy executable: {e}")
        return False


def test_gui_opens():
    """Test xem GUI có mở được không (manual check)"""
    print("\n" + "=" * 70)
    print("🖥️  Test GUI")
    print("=" * 70)
    print("⚠️ Không thể test GUI tự động")
    print("   → Bạn cần chạy thủ công và kiểm tra:")
    print("   1. GUI có mở được không?")
    print("   2. Có hiển thị 'FFmpeg: OK' không?")
    print("   3. Có hiển thị 'RAM: OK' không?")
    print("   4. Có thể chọn thư mục không?")
    print("   5. Có thể bắt đầu xử lý không?")
    print()
    print("💡 Để test:")
    print(f"   Double-click vào: dist/{get_platform_exe_name()}")
    print("   Hoặc chạy từ terminal")


def check_ffmpeg_bundled(exe_path):
    """Kiểm tra xem FFmpeg có được bundle không"""
    print("\n" + "=" * 70)
    print("🎬 Kiểm tra FFmpeg Bundle")
    print("=" * 70)
    
    # Kiểm tra thư mục ffmpeg_bin có tồn tại không
    ffmpeg_bin = Path("ffmpeg_bin")
    if ffmpeg_bin.exists():
        print("✅ Thư mục ffmpeg_bin/ tồn tại")
        
        # Kiểm tra file FFmpeg
        if platform.system().lower() == "windows":
            ffmpeg_exe = ffmpeg_bin / "ffmpeg.exe"
            ffprobe_exe = ffmpeg_bin / "ffprobe.exe"
        else:
            ffmpeg_exe = ffmpeg_bin / "ffmpeg"
            ffprobe_exe = ffmpeg_bin / "ffprobe"
        
        if ffmpeg_exe.exists():
            print(f"✅ Tìm thấy: {ffmpeg_exe}")
        else:
            print(f"⚠️ Không tìm thấy: {ffmpeg_exe}")
        
        if ffprobe_exe.exists():
            print(f"✅ Tìm thấy: {ffprobe_exe}")
        else:
            print(f"⚠️ Không tìm thấy: {ffprobe_exe}")
        
        print("\n💡 FFmpeg sẽ được bundle vào executable")
        print("   Khi chạy, FFmpeg sẽ được extract tự động vào thư mục tạm")
    else:
        print("⚠️ Không tìm thấy thư mục ffmpeg_bin/")
        print("   FFmpeg có thể không được bundle")


def main():
    """Hàm main"""
    print("=" * 70)
    print("🧪 TEST EXECUTABLE SAU KHI BUILD")
    print("=" * 70)
    print()
    
    # Tìm executable
    exe_path = find_executable()
    
    if not exe_path:
        print("❌ Không tìm thấy executable!")
        print("   Vui lòng build trước: python build_complete.py")
        return False
    
    # Test 1: Kiểm tra file
    if not check_file_exists(exe_path):
        return False
    
    # Test 2: Kiểm tra FFmpeg bundle
    check_ffmpeg_bundled(exe_path)
    
    # Test 3: Test import (không thể test trực tiếp với GUI)
    test_imports_in_exe(exe_path)
    
    # Test 4: Test chạy executable
    run_ok = test_executable_run(exe_path)
    
    # Test 5: Hướng dẫn test GUI thủ công
    test_gui_opens()
    
    # Tổng kết
    print("\n" + "=" * 70)
    print("📊 TỔNG KẾT")
    print("=" * 70)
    
    if run_ok:
        print("✅ Executable có vẻ OK!")
        print("   → Cần test thủ công GUI để chắc chắn")
    else:
        print("❌ Executable có vấn đề!")
        print("   → Kiểm tra log build và thử build lại")
    
    print("\n💡 Để test đầy đủ:")
    print(f"   1. Chạy: {exe_path}")
    print("   2. Kiểm tra GUI có mở được không")
    print("   3. Kiểm tra 'FFmpeg: OK' và 'RAM: OK'")
    print("   4. Test xử lý file MKV thật")
    
    return run_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

