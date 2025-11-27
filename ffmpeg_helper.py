"""
Helper để tìm và sử dụng FFmpeg - ưu tiên FFmpeg bundle local
"""
import os
import sys
import subprocess
import platform
from pathlib import Path

# Windows: ẩn cửa sổ CMD khi chạy subprocess
SUBPROCESS_FLAGS = 0
if platform.system() == "Windows":
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW


def get_bundle_dir():
    """Lấy thư mục chứa executable (khi chạy từ PyInstaller)"""
    if getattr(sys, 'frozen', False):
        # Chạy từ executable (PyInstaller)
        # PyInstaller tạo thư mục _MEIPASS tạm thời để extract data files
        if hasattr(sys, '_MEIPASS'):
            # Khi chạy từ PyInstaller, data files được extract vào _MEIPASS
            # FFmpeg sẽ ở trong _MEIPASS/ffmpeg_bin/
            bundle_path = Path(sys._MEIPASS)
            # Debug: In ra để kiểm tra
            if os.getenv('DEBUG_FFMPEG'):
                print(f"[DEBUG] Bundle dir: {bundle_path}")
                print(f"[DEBUG] FFmpeg bin dir: {bundle_path / 'ffmpeg_bin'}")
            return bundle_path
        else:
            # Fallback: thư mục chứa executable
            return Path(sys.executable).parent
    else:
        # Chạy từ source code
        return Path(__file__).parent


def find_ffmpeg_binary():
    """Tìm FFmpeg binary - ưu tiên bundle local"""
    bundle_dir = get_bundle_dir()
    system = platform.system()
    
    # Tên file FFmpeg theo OS
    if system == "Windows":
        ffmpeg_name = "ffmpeg.exe"
        ffprobe_name = "ffprobe.exe"
    else:
        ffmpeg_name = "ffmpeg"
        ffprobe_name = "ffprobe"
    
    # 1. Tìm trong thư mục bundle/ffmpeg_bin
    local_ffmpeg = bundle_dir / "ffmpeg_bin" / ffmpeg_name
    if local_ffmpeg.exists():
        ffmpeg_path = str(local_ffmpeg.absolute())
        if os.getenv('DEBUG_FFMPEG'):
            print(f"[DEBUG] Found FFmpeg at: {ffmpeg_path}")
        return ffmpeg_path
    
    # 2. Tìm trong thư mục bundle (cùng thư mục với exe)
    local_ffmpeg = bundle_dir / ffmpeg_name
    if local_ffmpeg.exists():
        ffmpeg_path = str(local_ffmpeg.absolute())
        if os.getenv('DEBUG_FFMPEG'):
            print(f"[DEBUG] Found FFmpeg at: {ffmpeg_path}")
        return ffmpeg_path
    
    # 3. Tìm trong PATH (system FFmpeg)
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            check=True,
            timeout=5,
            creationflags=SUBPROCESS_FLAGS
        )
        if os.getenv('DEBUG_FFMPEG'):
            print("[DEBUG] Using system FFmpeg from PATH")
        return 'ffmpeg'  # Sử dụng system FFmpeg
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    if os.getenv('DEBUG_FFMPEG'):
        print(f"[DEBUG] FFmpeg not found in: {bundle_dir / 'ffmpeg_bin'}")
        print(f"[DEBUG] FFmpeg not found in: {bundle_dir}")
    
    return None


def find_ffprobe_binary():
    """Tìm FFprobe binary - ưu tiên bundle local"""
    bundle_dir = get_bundle_dir()
    system = platform.system()
    
    if system == "Windows":
        ffprobe_name = "ffprobe.exe"
    else:
        ffprobe_name = "ffprobe"
    
    # 1. Tìm trong thư mục bundle/ffmpeg_bin
    local_ffprobe = bundle_dir / "ffmpeg_bin" / ffprobe_name
    if local_ffprobe.exists():
        return str(local_ffprobe.absolute())
    
    # 2. Tìm trong thư mục bundle
    local_ffprobe = bundle_dir / ffprobe_name
    if local_ffprobe.exists():
        return str(local_ffprobe.absolute())
    
    # 3. Tìm trong PATH
    try:
        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            check=True,
            creationflags=SUBPROCESS_FLAGS
        )
        return 'ffprobe'
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return None


def check_ffmpeg_available():
    """Kiểm tra FFmpeg có sẵn - sử dụng local nếu có"""
    ffmpeg_path = find_ffmpeg_binary()
    if ffmpeg_path is None:
        return False
    
    try:
        subprocess.run(
            [ffmpeg_path, '-version'],
            capture_output=True,
            check=True,
            creationflags=SUBPROCESS_FLAGS
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_ffmpeg_command(cmd):
    """Thay thế 'ffmpeg' trong command bằng path thực tế"""
    ffmpeg_path = find_ffmpeg_binary()
    if ffmpeg_path is None:
        return cmd  # Fallback về command gốc
    
    # Thay thế 'ffmpeg' và 'ffprobe' trong command
    if isinstance(cmd, list):
        new_cmd = []
        for arg in cmd:
            if arg == 'ffmpeg':
                new_cmd.append(ffmpeg_path)
            elif arg == 'ffprobe':
                ffprobe_path = find_ffprobe_binary()
                if ffprobe_path:
                    new_cmd.append(ffprobe_path)
                else:
                    new_cmd.append(arg)
            else:
                new_cmd.append(arg)
        return new_cmd
    elif isinstance(cmd, str):
        return cmd.replace('ffmpeg', ffmpeg_path).replace('ffprobe', find_ffprobe_binary() or 'ffprobe')
    
    return cmd


def probe_file(file_path: str) -> dict:
    """
    Probe file với ffprobe, ẩn console window trên Windows.
    Thay thế cho ffmpeg.probe() để không hiện CMD.
    """
    import json
    import os
    
    # Kiểm tra file tồn tại
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    ffprobe_path = find_ffprobe_binary() or 'ffprobe'
    
    cmd = [
        ffprobe_path,
        '-v', 'error',  # Hiển thị lỗi để debug
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        file_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            creationflags=SUBPROCESS_FLAGS,
            timeout=30  # Timeout 30 giây
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='replace').strip()
            if not error_msg:
                error_msg = f"ffprobe returned code {result.returncode}"
            raise RuntimeError(f"ffprobe error: {error_msg}")
        
        output = result.stdout.decode('utf-8')
        if not output.strip():
            raise RuntimeError("ffprobe returned empty output")
        
        return json.loads(output)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timeout for: {file_path}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ffprobe JSON parse error: {e}")

