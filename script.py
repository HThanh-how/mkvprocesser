import os
import sys
import json
import subprocess
import platform
import re
import datetime
import tempfile
import io
import shutil
import zipfile
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import requests
import argparse

from config_manager import load_user_config, get_config_dir
from github_sync import build_auto_push_config, RemoteSyncManager

REMOTE_SYNC = None  # Sẽ được khởi tạo trong main nếu có config
RUN_LOG_ENTRIES: List[Dict[str, Any]] = []
GIT_CACHED_PATH: Optional[str] = None
GIT_RELEASE_API = "https://api.github.com/repos/git-for-windows/git/releases/latest"

# Windows flag để ẩn console window
if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


def run_git_command(git_cmd: str, args: List[str], **kwargs):
    """Chạy git command với console window ẩn trên Windows."""
    kwargs.setdefault('capture_output', True)
    if platform.system() == "Windows":
        kwargs.setdefault('creationflags', CREATE_NO_WINDOW)
    return subprocess.run([git_cmd] + args, **kwargs)


def find_git_executable() -> Optional[str]:
    """Tìm đường dẫn git (portable hoặc hệ thống)."""
    git_env = os.getenv("GIT_PORTABLE_PATH")
    if git_env:
        git_env_path = Path(git_env)
        if git_env_path.is_dir():
            git_env_path = git_env_path / "bin" / ("git.exe" if os.name == "nt" else "git")
        if git_env_path.exists():
            return str(git_env_path)

    # Kiểm tra git portable đã tải về trong config dir (QUAN TRỌNG!)
    config_git_dir = get_config_dir() / "git_portable"
    possible_paths = [
        config_git_dir / "cmd" / "git.exe",
        config_git_dir / "bin" / "git.exe",
        config_git_dir / "mingw64" / "bin" / "git.exe",
    ]
    for candidate in possible_paths:
        if candidate.exists():
            return str(candidate)

    # Kiểm tra git portable trong executable (nếu có bundle)
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    portable_git = base_dir / "git_portable" / "bin" / ("git.exe" if os.name == "nt" else "git")
    if portable_git.exists():
        return str(portable_git)

    # Cuối cùng kiểm tra system git
    system_git = shutil.which("git")
    if system_git:
        return system_git
    return None


def download_git_portable() -> Optional[str]:
    """Tải MinGit (64-bit) về thư mục cấu hình và trả về đường dẫn git.exe."""
    if os.name != "nt":
        return None
    tools_dir = get_config_dir() / "git_portable"
    git_exe = tools_dir / "bin" / "git.exe"
    if git_exe.exists():
        return str(git_exe)

    try:
        print("[AUTO-COMMIT] Đang tải Git portable...")
        response = requests.get(GIT_RELEASE_API, timeout=30)
        response.raise_for_status()
        release = response.json()
        assets = release.get("assets", [])
        mingit_asset = None
        for asset in assets:
            name = asset.get("name", "")
            if (
                "MinGit" in name
                and "64-bit" in name
                and name.endswith(".zip")
            ):
                mingit_asset = asset
                break
        if not mingit_asset:
            print("[AUTO-COMMIT] Không tìm thấy asset MinGit 64-bit trong release mới nhất.")
            return None

        download_url = mingit_asset.get("browser_download_url")
        if not download_url:
            return None

        tools_dir.mkdir(parents=True, exist_ok=True)
        tmp_zip = tools_dir / "mingit.zip"
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        temp_extract = tools_dir / "_tmp_extract"
        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        with zipfile.ZipFile(tmp_zip, "r") as zip_ref:
            zip_ref.extractall(temp_extract)
        tmp_zip.unlink(missing_ok=True)

        # Một số bản MinGit có thư mục gốc bao bọc, di chuyển nội dung lên trên
        candidates = list(temp_extract.iterdir())
        if len(candidates) == 1 and candidates[0].is_dir():
            src_root = candidates[0]
        else:
            src_root = temp_extract

        for item in src_root.iterdir():
            dest = tools_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), dest)
        shutil.rmtree(temp_extract, ignore_errors=True)

        # Kiểm tra nhiều vị trí khả thi của git.exe (cmd/, bin/, mingw64/bin/)
        possible_paths = [
            tools_dir / "cmd" / "git.exe",
            tools_dir / "bin" / "git.exe",
            tools_dir / "mingw64" / "bin" / "git.exe",
        ]
        for candidate in possible_paths:
            if candidate.exists():
                print("[AUTO-COMMIT] Đã tải Git portable thành công.")
                return str(candidate)

        print("[AUTO-COMMIT] Không tìm thấy git.exe sau khi giải nén.")
        return None
    except Exception as exc:
        print(f"[AUTO-COMMIT] Không thể tải Git portable: {exc}")
        return None

# QUAN TRỌNG: Set FFmpeg binary path TRƯỚC KHI import ffmpeg
# ffmpeg-python library sẽ sử dụng các biến môi trường này
try:
    from ffmpeg_helper import find_ffmpeg_binary, find_ffprobe_binary
    ffmpeg_path = find_ffmpeg_binary()
    ffprobe_path = find_ffprobe_binary()
    
    if ffmpeg_path:
        os.environ['FFMPEG_BINARY'] = ffmpeg_path
        # Thêm vào PATH để ffmpeg-python tìm được
        ffmpeg_dir = os.path.dirname(ffmpeg_path)
        if ffmpeg_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
    
    if ffprobe_path:
        os.environ['FFPROBE_BINARY'] = ffprobe_path
        # Thêm vào PATH
        ffprobe_dir = os.path.dirname(ffprobe_path)
        if ffprobe_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = ffprobe_dir + os.pathsep + os.environ.get('PATH', '')
except ImportError:
    pass  # Nếu không import được, sẽ dùng system FFmpeg

# Helper để chạy FFmpeg với path local nếu có
def run_ffmpeg_command(cmd, **kwargs):
    """Wrapper cho subprocess.run để tự động sử dụng FFmpeg local nếu có và ẩn console"""
    try:
        from ffmpeg_helper import get_ffmpeg_command
        cmd = get_ffmpeg_command(cmd)
    except ImportError:
        pass  # Fallback về command gốc
    # Ẩn console window trên Windows
    if platform.system() == "Windows":
        kwargs.setdefault('creationflags', CREATE_NO_WINDOW)
    return subprocess.run(cmd, **kwargs)

# Kiểm tra và hướng dẫn cài đặt các package cần thiết
if __name__ == '__main__':
    try:
        # Thử import các module cần thiết
        try:
            import ffmpeg  # type: ignore
            import psutil  # type: ignore
            # Nếu import thành công, tiếp tục chạy script
            print("Đã tìm thấy các thư viện cần thiết.")
        except ImportError as e:
            # Nếu không import được, hiển thị hướng dẫn cài đặt
            print(f"\n{'='*50}")
            print("HƯỚNG DẪN CÀI ĐẶT THƯ VIỆN".center(50))
            print(f"{'='*50}")
            print(f"\nKhông thể tìm thấy thư viện: {e}")
            print("\nVui lòng cài đặt các thư viện cần thiết bằng một trong các cách sau:")
            
            # Hướng dẫn cài đặt trên hệ thống Linux
            if platform.system() == "Linux":
                print("\n--- CHO UBUNTU/DEBIAN ---")
                print("1. Cài đặt python3-pip và ffmpeg:")
                print("   sudo apt update")
                print("   sudo apt install -y python3-pip ffmpeg")
                print("\n2. Cài đặt các thư viện Python:")
                print("   python3 -m pip install ffmpeg-python psutil --user")
                
                print("\n--- CHO FEDORA/RHEL ---")
                print("1. Cài đặt python3-pip và ffmpeg:")
                print("   sudo dnf install -y python3-pip ffmpeg")
                print("\n2. Cài đặt các thư viện Python:")
                print("   python3 -m pip install ffmpeg-python psutil --user")
                
                print("\n--- SỬ DỤNG SNAP (NẾU CÓ) ---")
                print("1. Cài đặt ffmpeg qua snap:")
                print("   sudo snap install ffmpeg")
            
            # Hướng dẫn cài đặt trên MacOS
            elif platform.system() == "Darwin":
                print("\n--- CHO MACOS ---")
                print("1. Cài đặt Homebrew (nếu chưa có):")
                print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                print("\n2. Cài đặt ffmpeg:")
                print("   brew install ffmpeg")
                print("\n3. Cài đặt các thư viện Python:")
                print("   pip3 install ffmpeg-python psutil")
            
            # Hướng dẫn cài đặt trên Windows
            elif platform.system() == "Windows":
                print("\n--- CHO WINDOWS ---")
                print("1. Tải và cài đặt FFmpeg từ trang chủ:")
                print("   https://ffmpeg.org/download.html")
                print("\n2. Thêm đường dẫn FFmpeg vào biến môi trường PATH")
                print("\n3. Cài đặt các thư viện Python:")
                print("   pip install ffmpeg-python psutil")
            
            # Hướng dẫn chung
            print("\n--- CÁCH NHANH NHẤT (TẤT CẢ HỆ ĐIỀU HÀNH) ---")
            print("Sử dụng môi trường ảo (khuyến nghị):")
            print("1. Tạo môi trường ảo:")
            print("   python3 -m venv venv")
            print("\n2. Kích hoạt môi trường ảo:")
            print("   - Linux/MacOS: source venv/bin/activate")
            print("   - Windows: venv\\Scripts\\activate")
            print("\n3. Cài đặt các thư viện:")
            print("   pip install ffmpeg-python psutil")
            print("\n4. Chạy script trong môi trường ảo:")
            print("   python script.py")
            
            print(f"\n{'='*50}")
            print("LƯU Ý: Script này cần FFmpeg để xử lý video.")
            print("Vui lòng đảm bảo FFmpeg đã được cài đặt và có sẵn trong PATH")
            
            sys.exit(1)
            
        # Kiểm tra FFmpeg đã được cài đặt chưa
        try:
            # Sử dụng helper để tìm FFmpeg local
            try:
                from ffmpeg_helper import find_ffmpeg_binary
                ffmpeg_path = find_ffmpeg_binary()
                if ffmpeg_path:
                    subprocess.check_call([ffmpeg_path, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.check_call(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except ImportError:
                subprocess.check_call(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("Đã tìm thấy FFmpeg trên hệ thống.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("\nCẢNH BÁO: Không tìm thấy FFmpeg trên hệ thống!")
            print("Script này yêu cầu FFmpeg để xử lý video.")
            
            print("\nHướng dẫn cài đặt FFmpeg:")
            if platform.system() == "Linux":
                print("- Ubuntu/Debian: sudo add-apt-repository universe && sudo apt update && sudo apt install -y ffmpeg")
                print("- Fedora/RHEL: sudo dnf install -y ffmpeg")
                print("- Sử dụng snap: sudo snap install ffmpeg")
            elif platform.system() == "Darwin":
                print("- macOS: brew install ffmpeg")
            elif platform.system() == "Windows":
                print("- Windows: Tải từ https://ffmpeg.org/download.html và thêm vào PATH")
            
            response = input("\nBạn có muốn tiếp tục mà không có FFmpeg không? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
                
        # Nếu mọi thứ đã sẵn sàng, tiếp tục thực hiện script
        print("\nMọi thư viện đã sẵn sàng. Bắt đầu xử lý...")
        
    except Exception as e:
        print(f"Lỗi: {e}")
        sys.exit(1)

# Import các thư viện cần thiết
import ffmpeg  # type: ignore
import psutil  # type: ignore

import re
import datetime
import tempfile
import io
import shutil
from contextlib import contextmanager

def create_folder(folder_name):
    """Tạo folder nếu chưa tồn tại."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

def log_processed_file(
    log_file,
    old_name,
    new_name,
    *,
    signature=None,
    metadata=None,
):
    """Ghi lại log file đã được xử lý và đồng bộ lên GitHub nếu cần."""
    global RUN_LOG_ENTRIES
    metadata = metadata or {}
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if signature is None:
        signature = metadata.get("signature")
    source_path = metadata.get("source_path")
    if signature is None and source_path and os.path.exists(source_path):
        signature = get_file_signature(source_path)

    file_path = os.path.join(".", old_name)
    fallback_signature = ""
    if signature:
        fallback_signature = signature
    elif os.path.exists(file_path):
        fallback_signature = get_file_signature(file_path) or ""

    with open(log_file, "a", encoding='utf-8') as f:
        f.write(f"{old_name}|{new_name}|{current_time}|{fallback_signature}\n")

    # Đồng bộ lên GitHub nếu được cấu hình
    remote_entry = {
        "old_name": old_name,
        "new_name": new_name,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "signature": signature or fallback_signature,
        "category": metadata.get("category", "video"),
        "output_path": metadata.get("output_path"),
        "language": metadata.get("language"),
        "notes": metadata.get("notes"),
    }
    RUN_LOG_ENTRIES.append(remote_entry)

    if REMOTE_SYNC:
        local_path = metadata.get("local_path") or metadata.get("output_path")
        try:
            REMOTE_SYNC.record_entry(remote_entry, local_path=local_path)
        except Exception as sync_err:
            print(f"[AUTO PUSH] Không thể ghi log lên GitHub: {sync_err}")

def read_processed_files(log_file):
    """Đọc danh sách các file đã xử lý từ log."""
    processed_files = {}
    processed_signatures = {}
    if os.path.exists(log_file):
        with open(log_file, "r", encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    old_name = parts[0]
                    new_name = parts[1]
                    time_processed = parts[2] if len(parts) > 2 else ""
                    signature = parts[3] if len(parts) > 3 else ""
                    
                    info = {"new_name": new_name, "time": time_processed, "signature": signature}
                    processed_files[old_name] = info
                    processed_files[new_name] = info
                    if signature:
                        processed_signatures[signature] = info
    return processed_files, processed_signatures


def convert_legacy_log_file(log_path: Path, logs_dir: Path) -> Optional[Path]:
    """Chuyển file processed_files.log cũ sang JSON và xóa file cũ."""
    if not log_path.exists():
        return None

    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        print(f"[LOG] Không thể đọc {log_path}: {exc}")
        return None

    entries = []
    for line in lines:
        parts = line.strip().split("|")
        if len(parts) < 2:
            continue
        entries.append(
            {
                "old_name": parts[0],
                "new_name": parts[1],
                "timestamp": parts[2] if len(parts) > 2 else datetime.datetime.utcnow().isoformat(),
                "signature": parts[3] if len(parts) > 3 else "",
                "category": "video",
            }
        )

    if not entries:
        return None

    logs_dir.mkdir(parents=True, exist_ok=True)
    new_file = logs_dir / f"legacy_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    new_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    log_path.unlink(missing_ok=True)
    print(f"[LOG] Đã chuyển {log_path} thành {new_file}")

    if REMOTE_SYNC:
        for entry in entries:
            try:
                REMOTE_SYNC.record_entry(entry, local_path=None)
            except Exception as exc:
                print(f"[AUTO PUSH] Không thể đồng bộ entry legacy: {exc}")

    return new_file


def write_run_log_snapshot(logs_dir: Path, prefix: str = "run") -> Optional[Path]:
    global RUN_LOG_ENTRIES
    if not RUN_LOG_ENTRIES:
        return None
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_path = logs_dir / f"{prefix}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    file_path.write_text(json.dumps(RUN_LOG_ENTRIES, ensure_ascii=False, indent=2), encoding="utf-8")
    if REMOTE_SYNC:
        REMOTE_SYNC.upload_log_snapshot(RUN_LOG_ENTRIES, filename_prefix=prefix)
    RUN_LOG_ENTRIES = []
    print(f"[LOG] Đã lưu log phiên làm việc tại {file_path}")
    return file_path

def sanitize_filename(name):
    """Loại bỏ các ký tự không hợp lệ trong tên tệp để tránh lỗi FFmpeg."""
    # Thay thế các ký tự không hợp lệ bằng dấu gạch dưới
    return re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)

def get_video_resolution_label(file_path):
    """Lấy tên độ phân giải video (FHD, 4K, 2K, HD)."""
    try:
        probe = ffmpeg.probe(file_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream and 'width' in video_stream and 'height' in video_stream:
            width = int(video_stream['width'])
            height = int(video_stream['height'])
            # 8k
            if width >= 7680 or height >= 4320:
                return "8K"
            # 4k
            elif width >= 3840 or height >= 2160:  # Bao gồm cả 3840x1608
                return "4K"
            # 2k
            elif width >= 2560 or height >= 1440:
                return "2K"
            # FHD
            elif width >= 1920 or height >= 1080:
                return "FHD"
            # HD
            elif width >= 1280 or height >= 720:
                return "HD"
            # 480p
            elif width >= 720 or height >= 480:
                return "480p"
            else:
                return f"{width}p"
    except Exception as e:
        print(f"Error getting resolution for {file_path}: {e}")
    return "unknown_resolution"

def get_movie_year(file_path):
    """Lấy năm của phim từ metadata."""
    try:
        probe = ffmpeg.probe(file_path)
        format_tags = probe.get("format", {}).get("tags", {})
        year = format_tags.get("year", "")
        return year.strip()
    except Exception as e:
        print(f"Error getting year for {file_path}: {e}")
    return ""

def get_language_abbreviation(language_code):
    """Trả về tên viết tắt của ngôn ngữ dựa trên mã ngôn ngữ."""
    language_map = {
        'eng': 'ENG',  # Tiếng Anh
        'vie': 'VIE',  # Tiếng Việt
        'und': 'UNK',  # Không xác định (Undefined)
        'chi': 'CHI',  # Tiếng Trung
        'zho': 'CHI',  # Tiếng Trung (mã khác)
        'jpn': 'JPN',  # Tiếng Nhật
        'kor': 'KOR',  # Tiếng Hàn
        'fra': 'FRA',  # Tiếng Pháp
        'deu': 'DEU',  # Tiếng Đức
        'spa': 'SPA',  # Tiếng Tây Ban Nha
        'ita': 'ITA',  # Tiếng Ý
        'rus': 'RUS',  # Tiếng Nga
        'tha': 'THA',  # Tiếng Thái
        'ind': 'IND',  # Tiếng Indonesia
        'msa': 'MSA',  # Tiếng Malaysia
        'ara': 'ARA',  # Tiếng Ả Rập
        'hin': 'HIN',  # Tiếng Hindi
        'por': 'POR',  # Tiếng Bồ Đào Nha
        'nld': 'NLD',  # Tiếng Hà Lan
        'pol': 'POL',  # Tiếng Ba Lan
        'tur': 'TUR',  # Tiếng Thổ Nhĩ Kỳ
        'swe': 'SWE',  # Tiếng Thụy Điển
        'nor': 'NOR',  # Tiếng Na Uy
        'dan': 'DAN',  # Tiếng Đan Mạch
        'fin': 'FIN',  # Tiếng Phần Lan
        'ukr': 'UKR',  # Tiếng Ukraine
        'ces': 'CES',  # Tiếng Séc
        'hun': 'HUN',  # Tiếng Hungary
        'ron': 'RON',  # Tiếng Romania
        'bul': 'BUL',  # Tiếng Bulgaria
        'hrv': 'HRV',  # Tiếng Croatia
        'srp': 'SRP',  # Tiếng Serbia
        'slv': 'SLV',  # Tiếng Slovenia
        'ell': 'ELL',  # Tiếng Hy Lạp
        'heb': 'HEB',  # Tiếng Do Thái
        'kat': 'KAT',  # Tiếng Georgia
        'lat': 'LAT',  # Tiếng Latin
        'vie-Nom': 'NOM',  # Chữ Nôm
        'cmn': 'CMN',  # Tiếng Trung (Phổ thông)
        'yue': 'YUE',  # Tiếng Quảng Đông
        'nan': 'NAN',  # Tiếng Mân Nam
        'khm': 'KHM',  # Tiếng Khmer
        'lao': 'LAO',  # Tiếng Lào
        'mya': 'MYA',  # Tiếng Miến Điện
        'ben': 'BEN',  # Tiếng Bengal
        'tam': 'TAM',  # Tiếng Tamil
        'tel': 'TEL',  # Tiếng Telugu
        'mal': 'MAL',  # Tiếng Malayalam
        'kan': 'KAN',  # Tiếng Kannada
        'mar': 'MAR',  # Tiếng Marathi
        'pan': 'PAN',  # Tiếng Punjab
        'guj': 'GUJ',  # Tiếng Gujarat
        'ori': 'ORI',  # Tiếng Oriya
        'asm': 'ASM',  # Tiếng Assam
        'urd': 'URD',  # Tiếng Urdu
        'fas': 'FAS',  # Tiếng Ba Tư
        'pus': 'PUS',  # Tiếng Pashto
        'kur': 'KUR',  # Tiếng Kurdish
    }
    return language_map.get(language_code, language_code.upper()[:3])

def rename_simple(file_path):
    """Đổi tên file đơn giản cho trường hợp không có audio để tách."""
    try:
        resolution_label = get_video_resolution_label(file_path)
        probe = ffmpeg.probe(file_path)
        # Lấy ngôn ngữ từ audio stream đầu tiên
        audio_stream = next((stream for stream in probe['streams'] 
                           if stream['codec_type'] == 'audio'), None)
        language = 'und'  # mặc định là undefined
        audio_title = ''
        if audio_stream:
            language = audio_stream.get('tags', {}).get('language', 'und')
            audio_title = audio_stream.get('tags', {}).get('title', '')
        
        language_abbr = get_language_abbreviation(language)
        # Chỉ thêm audio_title nếu khác với language_abbr và không rỗng
        if audio_title and audio_title != language_abbr:
            lang_part = f"{language_abbr}_{audio_title}"
        else:
            lang_part = language_abbr
        
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        new_name = f"{resolution_label}_{lang_part}_{base_name}.mkv"
        new_name = sanitize_filename(new_name)
        
        dir_path = os.path.dirname(file_path)
        new_path = os.path.join(dir_path, new_name)
        
        os.rename(file_path, new_path)
        print(f"Simple renamed file to: {new_name}")
        return new_path
    except Exception as e:
        print(f"Error simple renaming file {file_path}: {e}")
        return file_path

def extract_video_with_audio(file_path, vn_folder, original_folder, log_file, probe_data, file_signature=None, rename_enabled=False):
    """Tách video với audio theo yêu cầu."""
    try:
        audio_streams = [stream for stream in probe_data['streams'] if stream['codec_type'] == 'audio']
        
        if not audio_streams:
            if rename_enabled:
                print(f"No audio found in {file_path}. Performing simple rename.")
                new_path = rename_simple(file_path)
                log_processed_file(
                    log_file,
                    os.path.basename(file_path),
                    os.path.basename(new_path),
                    signature=file_signature,
                    metadata={
                        "category": "video",
                        "source_path": file_path,
                        "output_path": os.path.abspath(new_path),
                    },
                )
            return

        # Lấy thông tin audio đầu tiên để xác định trường hợp
        first_audio = audio_streams[0]
        first_audio_language = first_audio.get('tags', {}).get('language', 'und')

        # Tạo danh sách audio tracks với thông tin cần thiết
        audio_tracks = []
        for stream in audio_streams:
            index = stream.get('index', -1)
            channels = stream.get('channels', 0)
            language = stream.get('tags', {}).get('language', 'und')
            title = stream.get('tags', {}).get('title', get_language_abbreviation(language))
            audio_tracks.append((index, channels, language, title))

        # Sắp xếp theo số kênh giảm dần
        audio_tracks.sort(key=lambda x: x[1], reverse=True)
        
        vietnamese_tracks = [track for track in audio_tracks if track[2] == 'vie']
        non_vietnamese_tracks = [track for track in audio_tracks if track[2] != 'vie']

        if first_audio_language == 'vie':
            # Trường hợp 1: Audio đầu tiên là tiếng Việt
            if non_vietnamese_tracks:
                # Chọn audio không phải tiếng Việt có nhiều kênh nhất
                selected_track = non_vietnamese_tracks[0]
                process_video(file_path, original_folder, selected_track, log_file, probe_data, file_signature=file_signature, rename_enabled=rename_enabled)
        else:
            # Trường hợp 2: Audio đầu tiên không phải tiếng Việt
            if vietnamese_tracks:
                # Chọn audio tiếng Việt có nhiều kênh nhất
                selected_track = vietnamese_tracks[0]
                process_video(file_path, vn_folder, selected_track, log_file, probe_data, file_signature=file_signature, rename_enabled=rename_enabled)

    except Exception as e:
        print(f"Exception while processing {file_path}: {e}")

def rename_file(file_path, audio_info, is_output=False):
    """Đổi tên file theo format yêu cầu."""
    try:
        resolution_label = get_video_resolution_label(file_path)
        year = get_movie_year(file_path)
        language = audio_info[2]  # Mã ngôn ngữ
        audio_title = audio_info[3]  # Tiêu đề audio
        
        # Lấy tên gốc của file
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Format chung cho cả file gốc và output:
        # resolution_label + language_abbr + audio_title + year + base_name
        language_abbr = get_language_abbreviation(language)
        new_name = f"{resolution_label}_{language_abbr}_{audio_title}"
        
        if year:
            new_name += f"_{year}"
        new_name += f"_{base_name}.mkv"
        
        new_name = sanitize_filename(new_name)
        
        # Tạo đường dẫn mới
        dir_path = os.path.dirname(file_path)
        new_path = os.path.join(dir_path, new_name)
        
        # Đổi tên file
        os.rename(file_path, new_path)
        print(f"Renamed file to: {new_name}")
        return new_path
    except Exception as e:
        print(f"Error renaming file {file_path}: {e}")
        return file_path

def process_video(file_path, output_folder, selected_track, log_file, probe_data, file_signature=None, rename_enabled=False):
    """Xử lý video với track audio đã chọn và trích xuất subtitle."""
    try:
        original_filename = os.path.basename(file_path)
        
        # Lấy thông tin cơ bản
        resolution_label = get_video_resolution_label(file_path)
        year = get_movie_year(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Lấy thông tin audio đầu tiên
        first_audio = next((stream for stream in probe_data['streams'] 
                          if stream['codec_type'] == 'audio'), None)
        
        if first_audio:
            first_audio_lang = first_audio.get('tags', {}).get('language', 'und')
            first_audio_title = first_audio.get('tags', {}).get('title', '')
            # Sử dụng title chỉ khi khác với language abbreviation
            first_audio_display = get_language_abbreviation(first_audio_lang)
            if first_audio_title and first_audio_title != first_audio_display:
                first_audio_display += f"_{first_audio_title}"
            
            # Logic tương tự cho selected track
            selected_lang_abbr = get_language_abbreviation(selected_track[2])
            selected_title = selected_track[3]
            selected_display = selected_lang_abbr
            if selected_title and selected_title != selected_lang_abbr:
                selected_display += f"_{selected_title}"
            
            # Format tên file
            if first_audio_lang == 'vie':
                source_name = f"{resolution_label}_{first_audio_display}"
                output_name = f"{resolution_label}_{selected_display}"
            else:
                source_name = f"{resolution_label}_{first_audio_display}"
                output_name = f"{resolution_label}_{selected_display}"
            
            # Thêm năm và tên gốc
            if year:
                source_name += f"_{year}"
                output_name += f"_{year}"
            source_name += f"_{base_name}.mkv"
            output_name += f"_{base_name}.mkv"
            
            # Đường dẫn output cuối cùng
            final_output_path = os.path.join(output_folder, sanitize_filename(output_name))
            
            # Kiểm tra trường hợp file đích đã tồn tại
            if os.path.exists(final_output_path):
                print(f"File đích đã tồn tại: {final_output_path}. Bỏ qua.")
                return True
            
            # Kiểm tra không gian trống trên đĩa
            try:
                output_dir = os.path.dirname(final_output_path)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                disk_usage = shutil.disk_usage(output_dir)
                free_space_gb = disk_usage.free / (1024**3)
                print(f"Dung lượng trống trên ổ đĩa: {free_space_gb:.2f} GB")
                
                if free_space_gb < 2:  # Cần ít nhất 2GB không gian trống để an toàn
                    print(f"CẢNH BÁO: Quá ít dung lượng trống trên ổ đĩa. Cần ít nhất 2GB")
                    return False
            except Exception as disk_err:
                print(f"Lỗi khi kiểm tra dung lượng ổ đĩa: {disk_err}")
            
            # Kiểm tra RAM khả dụng
            file_size = get_file_size_gb(file_path)
            available_ram = check_available_ram()
            
            # Ưu tiên xử lý trong RAM nếu có đủ RAM
            ram_required = file_size * 2  # Cần ít nhất 200% kích thước file
            try_ram_first = available_ram > ram_required
            
            if try_ram_first:
                print(f"Đủ RAM để xử lý file ({available_ram:.2f}GB > {ram_required:.2f}GB). Thử xử lý trong RAM...")
                
                # Xử lý trong RAM
                ram_success = False
                try:
                    with temp_directory_in_memory(use_ram=True, file_size_gb=file_size) as temp_dir:
                        # Đường dẫn tạm thời trong RAM
                        temp_output_path = os.path.join(temp_dir, sanitize_filename(output_name))
                        
                        # Xử lý tách audio trong RAM
                        cmd = [
                            'ffmpeg',
                            '-i', file_path,
                            '-map', '0:v',
                            '-map', f'0:{selected_track[0]}',
                            '-c', 'copy',
                            '-y',
                            temp_output_path
                        ]
                        
                        print(f"Đang chạy lệnh trong RAM: {' '.join(cmd)}")
                        result = run_ffmpeg_command(cmd, capture_output=True)
                        
                        if result.returncode == 0 and os.path.exists(temp_output_path):
                            print(f"Xử lý trong RAM thành công. Di chuyển file tới: {final_output_path}")
                            # Chuyển từ RAM sang ổ đĩa
                            shutil.copy2(temp_output_path, final_output_path)
                            ram_success = True
                except Exception as ram_error:
                    print(f"Lỗi khi xử lý trong RAM: {ram_error}")
                    
                # Nếu xử lý trong RAM thành công
                if ram_success and os.path.exists(final_output_path):
                    print(f"Video đã được lưu tới: {final_output_path}")
                    
                    # Rename file gốc sau khi xử lý thành công (chỉ khi rename_enabled = True)
                    if rename_enabled:
                        new_source_path = os.path.join(os.path.dirname(file_path), sanitize_filename(source_name))
                        os.rename(file_path, new_source_path)
                        print(f"Đã đổi tên file gốc thành: {source_name}")
                        
                        # Ghi log
                        log_processed_file(
                            log_file,
                            original_filename,
                            os.path.basename(new_source_path),
                            signature=file_signature,
                            metadata={
                                "category": "video",
                                "source_path": file_path,
                                "output_path": os.path.abspath(new_source_path),
                            },
                        )
                    else:
                        # Ghi log mà không rename
                        log_processed_file(
                            log_file,
                            original_filename,
                            original_filename,
                            signature=file_signature,
                            metadata={
                                "category": "video",
                                "source_path": file_path,
                                "output_path": os.path.abspath(file_path),
                            },
                        )
                    return True
                else:
                    print("Xử lý trong RAM thất bại. Chuyển sang xử lý trực tiếp trên ổ đĩa...")
            else:
                print(f"Không đủ RAM để xử lý ({available_ram:.2f}GB < {ram_required:.2f}GB). Xử lý trực tiếp trên ổ đĩa.")
            
            # Nếu không đủ RAM hoặc xử lý trong RAM thất bại, xử lý trực tiếp trên ổ đĩa
            print("Xử lý video trực tiếp trên ổ đĩa...")
            cmd = [
                'ffmpeg',
                '-i', file_path,
                '-map', '0:v',
                '-map', f'0:{selected_track[0]}',
                '-c', 'copy',
                '-y',
                final_output_path
            ]
            
            print(f"Đang chạy lệnh trên ổ đĩa: {' '.join(cmd)}")
            result = run_ffmpeg_command(cmd, capture_output=True)
            
            if result.returncode == 0 and os.path.exists(final_output_path):
                print(f"Video đã được lưu thành công tới: {final_output_path}")
                
                # Rename file gốc sau khi xử lý thành công (chỉ khi rename_enabled = True)
                if rename_enabled:
                    new_source_path = os.path.join(os.path.dirname(file_path), sanitize_filename(source_name))
                    os.rename(file_path, new_source_path)
                    print(f"Đã đổi tên file gốc thành: {source_name}")
                    
                    # Ghi log
                    log_processed_file(
                        log_file,
                        original_filename,
                        os.path.basename(new_source_path),
                        signature=file_signature,
                        metadata={
                            "category": "video",
                            "source_path": file_path,
                            "output_path": os.path.abspath(new_source_path),
                        },
                    )
                else:
                    # Ghi log mà không rename
                    log_processed_file(
                        log_file,
                        original_filename,
                        original_filename,
                        signature=file_signature,
                        metadata={
                            "category": "video",
                            "source_path": file_path,
                            "output_path": os.path.abspath(file_path),
                        },
                    )
                return True
            else:
                print(f"Xử lý thất bại: {file_path}")
                if result.stderr:
                    stderr_text = result.stderr.decode('utf-8', errors='replace')
                    print(f"Lỗi: {stderr_text}")
                return False
        else:
            print(f"Không tìm thấy audio trong {file_path}")
            return False
            
    except Exception as e:
        print(f"Lỗi khi xử lý {file_path}: {e}")
        return False

def extract_subtitle(file_path, subtitle_info, log_file, probe_data, file_signature=None):
    """Trích xuất subtitle tiếng Việt từ file video."""
    try:
        # Tạo thư mục ./Subtitles nếu chưa tồn tại
        sub_root_folder = os.path.join(".", "Subtitles")
        create_folder(sub_root_folder)
        
        index, language, title, codec = subtitle_info
        
        # Chỉ xử lý subtitle và định dạng text-based
        text_based_codecs = ['srt', 'ass', 'ssa', 'subrip']
        if codec.lower() not in text_based_codecs:
            print(f"Bỏ qua subtitle: định dạng {codec} không được hỗ trợ (chỉ hỗ trợ text-based)")
            return False
            
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Rút gọn tên file nếu quá dài
        if len(base_name) > 100:
            base_name = base_name[:100]
        
        # Đặt tên file subtitle giữ nguyên tên gốc và thêm mã ngôn ngữ
        sub_filename = sanitize_filename(f"{base_name}_{language}.srt")
        final_output_path = os.path.join(sub_root_folder, sub_filename)
        
        # Kiểm tra nếu subtitle đã tồn tại
        if os.path.exists(final_output_path):
            print(f"Subtitle đã tồn tại: {final_output_path}. Bỏ qua.")
            log_processed_file(
                log_file,
                os.path.basename(file_path),
                sub_filename,
                signature=file_signature,
                metadata={
                    "category": "subtitle",
                    "language": language,
                    "output_path": os.path.abspath(final_output_path),
                    "local_path": os.path.abspath(final_output_path),
                },
            )
            return final_output_path
        
        # Kiểm tra RAM khả dụng - subtitle thường nhỏ nên yêu cầu ít RAM hơn
        available_ram = check_available_ram()
        print(f"Xử lý subtitle với {available_ram:.2f} GB RAM khả dụng")
        
        # Ưu tiên xử lý trong RAM nếu có đủ RAM (>= 0.5GB)
        try_ram_first = available_ram >= 0.5
        
        if try_ram_first:
            print(f"Thử trích xuất subtitle trong RAM...")
            
            # Xử lý trong RAM
            ram_success = False
            try:
                with temp_directory_in_memory(use_ram=True, file_size_gb=None) as temp_dir:
                    # Đường dẫn tạm thời trong RAM
                    temp_output_path = os.path.join(temp_dir, sub_filename)
                    
                    # Lệnh ffmpeg để trích xuất subtitle vào RAM
                    cmd = [
                        'ffmpeg',
                        '-i', file_path,
                        '-map', f'0:{index}',
                        '-c:s', 'srt',
                        '-y',
                        temp_output_path
                    ]
                    
                    print(f"Đang chạy lệnh trong RAM: {' '.join(cmd)}")
                    result = run_ffmpeg_command(cmd, capture_output=True)
                    
                    if result.returncode == 0 and os.path.exists(temp_output_path):
                        print(f"Trích xuất trong RAM thành công. Di chuyển file tới: {final_output_path}")
                        # Chuyển từ RAM sang ổ đĩa
                        shutil.copy2(temp_output_path, final_output_path)
                        ram_success = True
            except Exception as ram_error:
                print(f"Lỗi khi xử lý trong RAM: {ram_error}")
                
            # Nếu xử lý trong RAM thành công
            if ram_success and os.path.exists(final_output_path):
                print(f"Subtitle đã được lưu thành công tới: {final_output_path}")
                
                # Ghi vào log
                log_processed_file(
                    log_file,
                    os.path.basename(file_path),
                    sub_filename,
                    signature=file_signature,
                    metadata={
                        "category": "subtitle",
                        "language": language,
                        "output_path": os.path.abspath(final_output_path),
                        "local_path": os.path.abspath(final_output_path),
                    },
                )
                return final_output_path
            else:
                print("Xử lý trong RAM thất bại. Chuyển sang xử lý trực tiếp trên ổ đĩa...")
        else:
            print(f"Không đủ RAM để xử lý. Xử lý trực tiếp trên ổ đĩa.")
        
        # Xử lý trực tiếp vào thư mục đích nếu không thể xử lý trong RAM
        print(f"Trích xuất subtitle trực tiếp vào: {final_output_path}")
        
        # Lệnh ffmpeg để trích xuất subtitle
        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-map', f'0:{index}',
            '-c:s', 'srt',
            '-y',
            final_output_path
        ]
        
        print(f"Đang chạy lệnh trên ổ đĩa: {' '.join(cmd)}")
        result = run_ffmpeg_command(cmd, capture_output=True)
        
        if result.returncode == 0 and os.path.exists(final_output_path):
            print(f"Subtitle đã được trích xuất thành công: {final_output_path}")
            
            # Ghi vào log
            log_processed_file(
                log_file,
                os.path.basename(file_path),
                sub_filename,
                signature=file_signature,
                metadata={
                    "category": "subtitle",
                    "language": language,
                    "output_path": os.path.abspath(final_output_path),
                    "local_path": os.path.abspath(final_output_path),
                },
            )
            return final_output_path
        else:
            print("Lỗi khi trích xuất subtitle trực tiếp")
            if result.stderr:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
                print(f"Lỗi: {stderr_text}")
            
            # Thử phương pháp khác nếu cách trên thất bại
            print("Thử phương pháp thay thế để trích xuất subtitle...")
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_output_path = os.path.join(temp_dir, sub_filename)
                
                alt_cmd = [
                    'ffmpeg',
                    '-i', file_path,
                    '-map', f'0:{index}',
                    '-f', 'srt',
                    '-y',
                    temp_output_path
                ]
                
                print(f"Đang chạy lệnh thay thế: {' '.join(alt_cmd)}")
                alt_result = run_ffmpeg_command(alt_cmd, capture_output=True)
                
                if alt_result.returncode == 0 and os.path.exists(temp_output_path):
                    print(f"Subtitle được trích xuất tạm thời: {temp_output_path}")
                    # Di chuyển tới đường dẫn cuối cùng
                    shutil.move(temp_output_path, final_output_path)
                    print(f"Subtitle đã được di chuyển tới: {final_output_path}")
                    
                    # Ghi vào log
                    log_processed_file(
                        log_file,
                        os.path.basename(file_path),
                        sub_filename,
                        signature=file_signature,
                        metadata={
                            "category": "subtitle",
                            "language": language,
                            "output_path": os.path.abspath(final_output_path),
                            "local_path": os.path.abspath(final_output_path),
                        },
                    )
                    return final_output_path
                else:
                    print("Không thể trích xuất subtitle bằng cả hai phương pháp")
                    if alt_result.stderr:
                        stderr_text = alt_result.stderr.decode('utf-8', errors='replace')
                        print(f"Lỗi: {stderr_text}")
                    return None
    except Exception as e:
        print(f"Lỗi khi trích xuất subtitle: {e}")
        return None

def get_subtitle_info(file_path):
    """Lấy thông tin về các track subtitle trong file video."""
    try:
        probe = ffmpeg.probe(file_path)
        subtitle_tracks = []
        for stream in probe['streams']:
            if stream['codec_type'] == 'subtitle':
                index = stream.get('index', -1)
                language = stream.get('tags', {}).get('language', 'und')
                title = stream.get('tags', {}).get('title', '')
                codec = stream.get('codec_name', '')
                
                # Thêm thông tin về codec_type vào log
                print(f"Found subtitle track: index={index}, language={language}, codec={codec}")
                
                # Thêm vào danh sách các subtitle cần xử lý
                subtitle_tracks.append((index, language, title, codec))
        return subtitle_tracks
    except Exception as e:
        print(f"Lỗi khi lấy thông tin subtitle từ {file_path}: {e}")
        return []

def get_file_signature(file_path, include_hash: bool = False):
    """
    Lấy chữ ký của file để nhận diện file trùng.
    
    Format: {size}_{duration}_{sub_count}_{sub_langs}[_{first_1mb_hash}]
    
    Ví dụ: 8589934592_7200.5_3_vie,eng,chi_a1b2c3d4
    """
    try:
        file_size = os.path.getsize(file_path)
        probe = ffmpeg.probe(file_path)
        duration = probe.get('format', {}).get('duration', '0')
        
        # Đếm subtitle tracks và ngôn ngữ
        sub_streams = [s for s in probe.get('streams', []) if s.get('codec_type') == 'subtitle']
        sub_count = len(sub_streams)
        sub_langs = sorted(set(
            s.get('tags', {}).get('language', 'und') 
            for s in sub_streams
        ))
        sub_langs_str = ','.join(sub_langs) if sub_langs else 'none'
        
        signature = f"{file_size}_{duration}_{sub_count}_{sub_langs_str}"
        
        # Optional: thêm hash của 1MB đầu tiên để tăng độ chính xác
        if include_hash:
            import hashlib
            try:
                with open(file_path, 'rb') as f:
                    first_mb = f.read(1024 * 1024)  # 1MB
                    hash_str = hashlib.md5(first_mb).hexdigest()[:8]
                    signature += f"_{hash_str}"
            except Exception:
                pass
        
        return signature
    except Exception as e:
        print(f"Error getting file signature: {e}")
        return None

def check_ffmpeg_available():
    """Kiểm tra FFmpeg có sẵn - sử dụng helper để tìm local FFmpeg"""
    try:
        from ffmpeg_helper import check_ffmpeg_available as check_local
        return check_local()
    except ImportError:
        # Fallback nếu không có helper
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

def check_available_ram():
    """Kiểm tra lượng RAM còn trống trong hệ thống."""
    try:
        memory = psutil.virtual_memory()
        free_memory_gb = memory.available / (1024 ** 3)  # Convert to GB
        print(f"RAM khả dụng: {free_memory_gb:.2f} GB")
        return free_memory_gb
    except Exception as e:
        print(f"Lỗi khi kiểm tra RAM: {e}")
        return 0

def get_file_size_gb(file_path):
    """Lấy kích thước file theo GB."""
    try:
        file_size = os.path.getsize(file_path)
        file_size_gb = file_size / (1024 ** 3)  # Convert to GB
        print(f"Kích thước file: {file_size_gb:.2f} GB")
        return file_size_gb
    except Exception as e:
        print(f"Lỗi khi lấy kích thước file: {e}")
        return 0

@contextmanager
def temp_directory_in_memory(use_ram=True, file_size_gb=None):
    """Tạo thư mục tạm trong RAM hoặc trên đĩa tùy thuộc vào tham số use_ram.
    
    Args:
        use_ram (bool): Có sử dụng RAM không
        file_size_gb (float, optional): Kích thước file đang xử lý theo GB, dùng để tính toán không gian cần thiết
    """
    if not use_ram:
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Tạo thư mục tạm trên ổ đĩa: {temp_dir}")
            yield temp_dir
        return
    
    # Tính toán không gian tối thiểu cần thiết dựa trên kích thước file nếu có
    # Đối với subtitle, chỉ cần một phần nhỏ dung lượng, còn video cần nhiều hơn
    if file_size_gb:
        # Đối với file nhỏ, yêu cầu ít nhất 400MB
        required_space_gb = max(0.4, file_size_gb * 0.5)
        print(f"Cần ít nhất {required_space_gb:.2f} GB cho file {file_size_gb:.2f} GB")
    else:
        # Mặc định yêu cầu 1GB nếu không biết kích thước file
        required_space_gb = 1.0
    
    # Tạo danh sách các vị trí RAM có thể sử dụng
    ram_locations = []
    
    # 1. Ubuntu/Linux: Các vị trí RAM disk tiềm năng
    if os.name == 'posix':
        # /dev/shm - thường là RAM disk trên hầu hết các hệ thống Linux
        if os.path.exists('/dev/shm') and os.access('/dev/shm', os.W_OK):
            ram_locations.append(('/dev/shm', 'RAM disk'))
        
        # /run/user/<uid> - thư mục người dùng trên systemd, thường nằm trong RAM
        uid = os.getuid() if hasattr(os, 'getuid') else None
        if uid is not None:
            user_runtime_dir = f"/run/user/{uid}"
            if os.path.exists(user_runtime_dir) and os.access(user_runtime_dir, os.W_OK):
                ram_locations.append((user_runtime_dir, 'Runtime user directory'))
        
        # /run - thư mục runtime cho các tiến trình của hệ thống 
        if os.path.exists('/run') and os.access('/run', os.W_OK):
            ram_locations.append(('/run', 'Runtime directory'))
        
        # /tmp - có thể được cấu hình là tmpfs trên RAM trên một số hệ thống
        if os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
            ram_locations.append(('/tmp', 'Temporary directory'))
    
    # 2. macOS: Thử /private/tmp (có thể được lưu trữ trong RAM trên một số cấu hình)
    if platform.system() == 'Darwin':
        if os.path.exists('/private/tmp') and os.access('/private/tmp', os.W_OK):
            ram_locations.append(('/private/tmp', 'macOS temporary directory'))
    
    # Kiểm tra từng vị trí và tìm nơi có không gian trống nhiều nhất
    best_location = None
    best_location_desc = None
    max_free_space = 0
    
    print(f"Tìm kiếm vị trí lưu trữ tạm (yêu cầu ít nhất {required_space_gb:.2f} GB)...")
    for location, desc in ram_locations:
        try:
            usage = shutil.disk_usage(location)
            free_space_gb = usage.free / (1024**3)
            print(f"- {desc} ({location}): {free_space_gb:.2f} GB trống")
            
            # Lưu lại vị trí có không gian trống lớn nhất
            if free_space_gb > max_free_space:
                max_free_space = free_space_gb
                best_location = location
                best_location_desc = desc
        except Exception as e:
            print(f"- {desc} ({location}): Không thể kiểm tra ({e})")
    
    # Tạo thư mục tạm trong vị trí tốt nhất nếu có đủ không gian
    if best_location and max_free_space >= required_space_gb:
        try:
            temp_dir = tempfile.mkdtemp(dir=best_location)
            print(f"Sử dụng {best_location_desc} ({max_free_space:.2f} GB trống) cho xử lý RAM: {temp_dir}")
            try:
                yield temp_dir
            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    print(f"Đã xóa thư mục tạm: {temp_dir}")
            return
        except Exception as e:
            print(f"Lỗi khi tạo thư mục tạm trong {best_location}: {e}")
    
    # Nếu không có RAM disk nào hoặc không đủ không gian, sử dụng ổ đĩa thay thế
    try:
        # Cố gắng tạo thư mục tạm ưu tiên trong /tmp nếu có
        if os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
            temp_dir = tempfile.mkdtemp(dir='/tmp')
        else:
            temp_dir = tempfile.mkdtemp()
        
        if best_location:
            print(f"THÔNG BÁO: Không đủ không gian trong {best_location_desc} ({max_free_space:.2f} GB < {required_space_gb:.2f} GB)")
            print(f"Sử dụng ổ đĩa thay thế: {temp_dir}")
        else:
            print(f"THÔNG BÁO: Không tìm thấy RAM disk phù hợp. Sử dụng ổ đĩa thay thế: {temp_dir}")
        
        try:
            yield temp_dir
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"Đã xóa thư mục tạm: {temp_dir}")
    except Exception as e:
        print(f"Lỗi khi xử lý thư mục tạm: {e}")
        # Fallback cuối cùng: sử dụng tempfile thông thường
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Fallback: Sử dụng thư mục tạm trên ổ đĩa: {temp_dir}")
            yield temp_dir

def ensure_git_available() -> Optional[str]:
    """Đảm bảo có git, tải MinGit nếu cần."""
    global GIT_CACHED_PATH
    if GIT_CACHED_PATH and Path(GIT_CACHED_PATH).exists():
        return GIT_CACHED_PATH

    git_cmd = find_git_executable()
    if not git_cmd:
        git_cmd = download_git_portable()

    if git_cmd:
        try:
            run_git_command(git_cmd, ["--version"], check=True)
            GIT_CACHED_PATH = git_cmd
            return git_cmd
        except Exception:
            pass
    print("Warning: Git không khả dụng. Bỏ qua auto-commit.")
    return None


def check_git_available():
    return ensure_git_available()

def get_file_size_mb(file_path):
    """Lấy kích thước file theo MB."""
    try:
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 ** 2)  # Convert to MB
        return file_size_mb
    except Exception as e:
        print(f"Lỗi khi lấy kích thước file: {e}")
        return 0

def auto_commit_subtitles(subtitle_folder, settings: Optional[Dict[str, Any]] = None):
    """Tự động commit các file subtitle và log lên git."""
    git_cmd = check_git_available()
    if not git_cmd:
        return False
    
    # Load settings nếu chưa có
    if settings is None:
        settings = load_user_config()
    
    # Kiểm tra config
    repo_url = settings.get("repo_url", "").strip()
    branch = settings.get("branch", "main").strip()
    token = settings.get("token", "").strip()
    
    if not repo_url:
        print("[AUTO-COMMIT] Chưa cấu hình repo URL. Bỏ qua auto-commit.")
        return False
    
    try:
        # Bước 1: Kiểm tra và copy file subtitle trước (đảm bảo file đã được tạo)
        subtitle_path = Path(subtitle_folder).resolve()
        if not subtitle_path.exists():
            print(f"[AUTO-COMMIT] Thư mục {subtitle_folder} không tồn tại.")
            return False
        
        # Copy file subtitle vào thư mục (nếu chưa có git, sẽ copy vào thư mục hiện tại)
        print(f"[AUTO-COMMIT] Đang kiểm tra file subtitle...")
        subtitle_files = []
        for root, dirs, files in os.walk(subtitle_path):
            for file in files:
                if file.endswith('.srt'):
                    subtitle_files.append(Path(root) / file)
        
        if not subtitle_files:
            print("[AUTO-COMMIT] Không có file subtitle nào để commit.")
            return True
        
        # work_dir là Subtitles/ (không phải thư mục cha)
        # File subtitle sẽ được commit trong Subtitles/ trên GitHub
        work_dir = subtitle_path
        
        # Bước 2: Kiểm tra xem có phải git repository không
        result = run_git_command(git_cmd, ['rev-parse', '--git-dir'], cwd=str(work_dir))
        is_git_repo = result.returncode == 0
        
        if not is_git_repo:
            # Tạo URL với token nếu có
            if token and "github.com" in repo_url:
                # Format: https://token@github.com/user/repo.git
                url_parts = repo_url.replace("https://", "").replace("http://", "").split("/")
                if len(url_parts) >= 2:
                    auth_url = f"https://{token}@{'/'.join(url_parts)}"
                else:
                    auth_url = repo_url
            else:
                auth_url = repo_url
            
            # Kiểm tra xem thư mục đã tồn tại chưa
            if work_dir.exists():
                # Thư mục đã tồn tại -> init git và pull (KHÔNG clone vì sẽ lỗi)
                print(f"[AUTO-COMMIT] Thư mục đã tồn tại. Đang init git và pull...")
                try:
                    # Init git repo
                    run_git_command(git_cmd, ['init'], cwd=str(work_dir), check=True)
                    
                    # Add remote (nếu chưa có)
                    remote_check = run_git_command(git_cmd, ['remote', 'get-url', 'origin'], cwd=str(work_dir))
                    if remote_check.returncode != 0:
                        run_git_command(git_cmd, ['remote', 'add', 'origin', auth_url], cwd=str(work_dir), check=True)
                    else:
                        # Nếu remote đã tồn tại, set lại URL
                        run_git_command(git_cmd, ['remote', 'set-url', 'origin', auth_url], cwd=str(work_dir), check=True)
                    
                    # Enable sparse checkout - chỉ pull logs/ và processed_files.log
                    # KHÔNG pull thư mục subtitles/ từ remote để tránh tạo Subtitles/subtitles/
                    run_git_command(git_cmd, ['sparse-checkout', 'init', '--cone'], cwd=str(work_dir), check=True)
                    run_git_command(git_cmd, ['sparse-checkout', 'set', 'logs', 'processed_files.log'], cwd=str(work_dir), check=True)
                    
                    # Fetch và pull
                    run_git_command(git_cmd, ['fetch', 'origin', branch], cwd=str(work_dir), check=True, timeout=60)
                    run_git_command(git_cmd, ['checkout', '-b', branch, f'origin/{branch}'], cwd=str(work_dir), check=False)
                    run_git_command(git_cmd, ['pull', 'origin', branch], cwd=str(work_dir), check=False, timeout=60)
                    
                    print(f"[AUTO-COMMIT] Đã init git và pull thành công.")
                    
                except Exception as init_err:
                    print(f"[AUTO-COMMIT] Lỗi khi init git: {init_err}")
                    return False
            else:
                # Thư mục chưa tồn tại -> clone như bình thường
                print(f"[AUTO-COMMIT] Đang clone repo về {work_dir} (sparse: chỉ logs/ và processed_files.log)...")
                try:
                    clone_cmd = [
                        git_cmd, 'clone',
                        '--filter=blob:none',  # Chỉ clone metadata, không clone file lớn
                        '--sparse',
                        '--depth=1',
                        '--branch', branch,
                        auth_url,
                        str(work_dir)
                    ]
                    
                    # Clone với console ẩn
                    clone_kwargs = {'capture_output': True, 'text': True, 'timeout': 120}
                    if platform.system() == "Windows":
                        clone_kwargs['creationflags'] = CREATE_NO_WINDOW
                    clone_result = subprocess.run(clone_cmd, **clone_kwargs)
                    
                    if clone_result.returncode != 0:
                        print(f"[AUTO-COMMIT] Lỗi khi clone: {clone_result.stderr}")
                        return False
                    
                    # Sparse checkout chỉ logs/ và processed_files.log (log cũ)
                    run_git_command(git_cmd, ['sparse-checkout', 'set', 'logs', 'processed_files.log'], cwd=str(work_dir), check=True)
                    
                    print(f"[AUTO-COMMIT] Đã clone repo thành công.")
                    
                except Exception as clone_err:
                    print(f"[AUTO-COMMIT] Không thể clone repo: {clone_err}")
                    return False
        else:
            # Đã là git repo, pull để cập nhật logs/ và processed_files.log
            print(f"[AUTO-COMMIT] Đã là git repo. Đang pull (chỉ logs/ và processed_files.log)...")
            try:
                run_git_command(git_cmd, ['pull'], cwd=str(work_dir), check=True, timeout=60)
            except Exception:
                pass  # Bỏ qua lỗi pull
        
        # Setup git config
        git_user = settings.get("git_user_name", "MKV Processor Bot")
        git_email = settings.get("git_user_email", "bot@example.com")
        run_git_command(git_cmd, ['config', 'user.name', git_user], cwd=str(work_dir), check=False)
        run_git_command(git_cmd, ['config', 'user.email', git_email], cwd=str(work_dir), check=False)
        
        # Bước 3: Convert processed_files.log cũ sang JSON nếu có (sau khi đã có git)
        processed_log_path = work_dir / "processed_files.log"
        logs_dir = work_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Kiểm tra xem processed_files.log có tồn tại trong git nhưng đã bị xóa local không
        deleted_log_file = None
        if processed_log_path.exists():
            print("[AUTO-COMMIT] Phát hiện processed_files.log cũ. Đang chuyển sang JSON...")
            try:
                converted = convert_legacy_log_file(processed_log_path, logs_dir)
                if converted:
                    print(f"[AUTO-COMMIT] Đã chuyển log cũ thành {converted.name}")
                    # File đã bị xóa sau khi convert, cần add vào staging
                    deleted_log_file = "processed_files.log"
            except Exception as convert_err:
                print(f"[AUTO-COMMIT] Lỗi khi chuyển log cũ: {convert_err}")
        else:
            # Kiểm tra xem file có trong git nhưng đã bị xóa local không
            check_result = run_git_command(git_cmd, ['ls-files', 'processed_files.log'], cwd=str(work_dir))
            if check_result.returncode == 0 and check_result.stdout.strip():
                # File có trong git nhưng không còn ở local (đã bị xóa)
                deleted_log_file = "processed_files.log"
        
        # Bước 4: Lấy danh sách file subtitle và log để commit
        # File subtitle nằm trong thư mục Subtitles (work_dir = subtitle_path)
        subtitle_files_to_commit = []
        log_files = []
        skipped_files = []
        
        # Lấy file .srt (subtitle) trong thư mục Subtitles (work_dir)
        for file_path in work_dir.glob("*.srt"):
            if file_path.is_file():
                file_size_mb = get_file_size_mb(str(file_path))
                
                if file_size_mb < 1.0:  # < 1MB
                    # Relative path từ work_dir (Subtitles/) đến file subtitle
                    # Kết quả: chỉ tên file (file.srt), không có thư mục con
                    relative_path = file_path.relative_to(work_dir)
                    subtitle_files_to_commit.append((str(relative_path), file_path.stem))
                else:
                    skipped_files.append((file_path.name, file_size_mb))
        
        # Lấy file log JSON trong thư mục logs/
        logs_dir = work_dir / "logs"
        if logs_dir.exists():
            for file_path in logs_dir.glob("*.json"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(work_dir)
                    log_files.append(str(relative_path))
        
        files_to_commit = [f[0] for f in subtitle_files_to_commit] + log_files
        
        if not files_to_commit:
            print("[AUTO-COMMIT] Không có file nào để commit.")
            return True
        
        print(f"\n=== AUTO-COMMIT SUBTITLES & LOGS ===")
        print(f"Sẽ commit {len(subtitle_files_to_commit)} subtitle(s) và {len(log_files)} log file(s):")
        for file_path, movie_name in subtitle_files_to_commit:
            print(f"  - {file_path} ({movie_name})")
        for file_path in log_files:
            print(f"  - {file_path}")
        
        if skipped_files:
            print(f"\nBỏ qua {len(skipped_files)} file subtitle >= 1MB:")
            for file_name, size_mb in skipped_files:
                print(f"  - {file_name} ({size_mb:.2f} MB)")
        
        # Add files to git (bao gồm cả file đã xóa nếu có)
        if deleted_log_file:
            # Add file đã xóa vào staging
            rm_result = run_git_command(git_cmd, ['rm', deleted_log_file], cwd=str(work_dir))
            if rm_result.returncode != 0:
                # Nếu rm thất bại, thử add để stage deletion
                add_result = run_git_command(git_cmd, ['add', deleted_log_file], cwd=str(work_dir))
                if add_result.returncode != 0:
                    print(f"[AUTO-COMMIT] Cảnh báo: Không thể stage file đã xóa {deleted_log_file}")
        
        # Add các file mới
        for file_path in files_to_commit:
            add_result = run_git_command(git_cmd, ['add', file_path], cwd=str(work_dir))
            if add_result.returncode != 0:
                err_text = add_result.stderr.decode('utf-8', errors='replace') if add_result.stderr else "Unknown error"
                print(f"[AUTO-COMMIT] Lỗi khi add file {file_path}: {err_text}")
                return False
        
        # Check if there are changes to commit
        status_result = run_git_command(git_cmd, ['status', '--porcelain'], cwd=str(work_dir))
        status_text = status_result.stdout.decode('utf-8', errors='replace').strip() if status_result.stdout else ""
        
        if not status_text:
            print("[AUTO-COMMIT] Không có thay đổi mới để commit.")
            return True
        
        # Kiểm tra xem có file nào được staged không (bắt đầu bằng A, M, D, R)
        staged_changes = [line for line in status_text.split('\n') if line and line[0] in 'AMD R']
        if not staged_changes:
            print("[AUTO-COMMIT] Không có file nào được staged để commit.")
            print(f"[DEBUG] Git status: {status_text}")
            return True
        
        # Tạo commit message chi tiết với ngày và danh sách phim
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Lấy tên phim từ file subtitle (bỏ đuôi .srt và các phần không cần thiết)
        movie_names = []
        language_suffixes = ['_vie', '_eng', '_chi', '_jpn', '_kor', '_und', '_fre', '_spa', '_ger', 
                            '_fra', '_deu', '_ita', '_rus', '_tha', '_ind', '_msa', '_ara', '_hin', 
                            '_por', '_nld', '_pol', '_tur', '_swe', '_nor', '_dan', '_fin', '_ukr',
                            '_ces', '_hun', '_ron', '_bul', '_hrv', '_srp', '_slv', '_ell', '_heb',
                            '_kat', '_lat', '_cmn', '_yue', '_nan', '_khm', '_lao', '_mya', '_ben',
                            '_tam', '_tel', '_mal', '_kan', '_mar', '_pan', '_guj', '_ori', '_asm',
                            '_urd', '_fas', '_pus', '_kur']
        
        for _, movie_name in subtitle_files_to_commit:
            # Làm sạch tên phim: bỏ các phần như _vie, _eng, etc.
            clean_name = movie_name
            # Bỏ các suffix ngôn ngữ (case-insensitive)
            for suffix in language_suffixes:
                if clean_name.lower().endswith(suffix.lower()):
                    clean_name = clean_name[:-len(suffix)]
                    break  # Chỉ bỏ 1 suffix đầu tiên tìm thấy
            # Nếu tên quá dài, rút gọn
            if len(clean_name) > 50:
                clean_name = clean_name[:47] + "..."
            if clean_name:  # Chỉ thêm nếu tên không rỗng
                movie_names.append(clean_name)
        
        # Loại bỏ trùng lặp nhưng giữ thứ tự
        seen = set()
        unique_movie_names = []
        for name in movie_names:
            if name not in seen:
                seen.add(name)
                unique_movie_names.append(name)
        movie_names = unique_movie_names
        
        # Tạo commit message rõ ràng
        if subtitle_files_to_commit:
            if len(movie_names) == 1:
                commit_message = f"📅 {current_date} | 🎬 {movie_names[0]} | {len(subtitle_files_to_commit)} subtitle(s)"
            elif len(movie_names) <= 3:
                movies_str = ", ".join(movie_names)
                commit_message = f"📅 {current_date} | 🎬 {movies_str} | {len(subtitle_files_to_commit)} subtitle(s)"
            else:
                movies_str = ", ".join(movie_names[:3]) + f" và {len(movie_names) - 3} phim khác"
                commit_message = f"📅 {current_date} | 🎬 {movies_str} | {len(subtitle_files_to_commit)} subtitle(s)"
            
            if log_files:
                commit_message += f" + {len(log_files)} log file(s)"
        else:
            commit_message = f"📅 {current_date} | 📝 Update {len(log_files)} log file(s)"
        
        commit_message += f" | ⏰ {current_time}"
        
        commit_result = run_git_command(git_cmd, ['commit', '-m', commit_message], cwd=str(work_dir))
        
        if commit_result.returncode == 0:
            print(f"✅ Đã commit thành công: {commit_message}")
            
            # Thử push, nếu conflict thì tự resolve
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    push_result = run_git_command(git_cmd, ['push'], cwd=str(work_dir), timeout=60)
                    if push_result.returncode == 0:
                        print("✅ Đã push lên remote repository thành công.")
                        return True
                    else:
                        # Lấy thông báo lỗi từ cả stderr và stdout
                        err_parts = []
                        if push_result.stderr:
                            err_parts.append(push_result.stderr.decode('utf-8', errors='replace').strip())
                        if push_result.stdout:
                            stdout_text = push_result.stdout.decode('utf-8', errors='replace').strip()
                            if stdout_text and stdout_text not in err_parts:
                                err_parts.append(stdout_text)
                        err_msg = " | ".join(err_parts) if err_parts else f"Exit code: {push_result.returncode}"
                        
                        if "conflict" in err_msg.lower() or "non-fast-forward" in err_msg.lower():
                            print(f"[AUTO-COMMIT] Phát hiện conflict. Đang pull và merge (lần thử {attempt + 1}/{max_retries})...")
                            # Pull về để merge
                            pull_result = run_git_command(git_cmd, ['pull', '--no-edit'], cwd=str(work_dir), timeout=60)
                            if pull_result.returncode == 0:
                                # Commit lại sau khi merge
                                commit_result = run_git_command(git_cmd, ['commit', '-m', commit_message], cwd=str(work_dir))
                                if commit_result.returncode == 0:
                                    continue  # Thử push lại
                            else:
                                # Nếu merge thất bại, dùng strategy ours để giữ bản local
                                print("[AUTO-COMMIT] Merge thất bại. Dùng strategy ours...")
                                run_git_command(git_cmd, ['pull', '--strategy=ours', '--no-edit'], cwd=str(work_dir), timeout=60)
                                continue
                        else:
                            print(f"⚠️ Commit thành công nhưng không thể push: {err_msg}")
                            return False
                except Exception as push_err:
                    print(f"⚠️ Lỗi khi push: {push_err}")
                    if attempt < max_retries - 1:
                        print(f"[AUTO-COMMIT] Đang thử lại...")
                        continue
                    return False
            
            print("⚠️ Không thể push sau nhiều lần thử.")
            return False
        else:
            # Lấy thông báo lỗi từ cả stderr và stdout
            err_parts = []
            if commit_result.stderr:
                err_parts.append(commit_result.stderr.decode('utf-8', errors='replace').strip())
            if commit_result.stdout:
                stdout_text = commit_result.stdout.decode('utf-8', errors='replace').strip()
                if stdout_text and stdout_text not in err_parts:
                    err_parts.append(stdout_text)
            err_msg = " | ".join(err_parts) if err_parts else f"Exit code: {commit_result.returncode}"
            
            print(f"❌ Lỗi khi commit (returncode={commit_result.returncode}): {err_msg}")
            
            # Debug: Kiểm tra git status để xem có file nào cần commit không
            status_result = run_git_command(git_cmd, ['status', '--short'], cwd=str(work_dir))
            if status_result.stdout:
                status_text = status_result.stdout.decode('utf-8', errors='replace').strip()
                if status_text:
                    print(f"[DEBUG] Git status: {status_text}")
            
            return False
            
    except Exception as e:
        print(f"Lỗi trong quá trình auto-commit: {e}")
        return False

def main(input_folder=None, force_reprocess: Optional[bool] = None, dry_run: bool = False):
    """
    Hàm main xử lý video
    
    Args:
        input_folder: Thư mục chứa file MKV cần xử lý. 
                     Nếu None, sử dụng thư mục hiện tại.
    """
    if not check_ffmpeg_available():
        return
    
    # Sử dụng thư mục được chỉ định hoặc thư mục hiện tại
    if input_folder is None:
        input_folder = "."
    
    # Đảm bảo đường dẫn tuyệt đối
    input_folder = os.path.abspath(input_folder)
    
    # Thay đổi thư mục làm việc nếu cần
    original_cwd = os.getcwd()
    need_restore_cwd = False
    if input_folder != original_cwd:
        os.chdir(input_folder)
        need_restore_cwd = True
        print(f"Đã chuyển sang thư mục: {input_folder}")
    
    vn_folder = "Lồng Tiếng - Thuyết Minh"
    original_folder = "Original"
    subtitle_folder = os.path.join(".", "Subtitles")
    log_file = os.path.join(subtitle_folder, "processed_files.log")

    # Tạo các thư mục cần thiết
    create_folder(vn_folder)
    create_folder(original_folder)
    create_folder(os.path.join(".", "Subtitles"))

    # Kiểm tra dung lượng ổ đĩa
    try:
        disk_usage = shutil.disk_usage(".")
        total_gb = disk_usage.total / (1024**3)
        free_gb = disk_usage.free / (1024**3)
        used_gb = disk_usage.used / (1024**3)
        percent_free = (free_gb / total_gb) * 100
        
        print(f"=== THÔNG TIN HỆ THỐNG ===")
        print(f"Ổ đĩa:")
        print(f"  Tổng dung lượng: {total_gb:.2f} GB")
        print(f"  Đã sử dụng: {used_gb:.2f} GB")
        print(f"  Còn trống: {free_gb:.2f} GB ({percent_free:.1f}%)")
        
        if percent_free < 10:
            print("\nCẢNH BÁO: Ổ đĩa của bạn còn rất ít dung lượng trống. Có thể gặp lỗi khi xử lý file lớn.")
    except Exception as e:
        print(f"Không thể kiểm tra dung lượng ổ đĩa: {e}")

    # Kiểm tra và hiển thị thông tin về RAM
    available_ram = check_available_ram()
    print(f"\nRAM khả dụng: {available_ram:.2f} GB")
    
    # Kiểm tra không gian trong /dev/shm nếu có
    if os.path.exists('/dev/shm'):
        try:
            shm_usage = shutil.disk_usage('/dev/shm')
            shm_free_gb = shm_usage.free / (1024**3)
            shm_total_gb = shm_usage.total / (1024**3)
            print(f"RAM disk (/dev/shm): {shm_total_gb:.2f} GB, còn trống: {shm_free_gb:.2f} GB")
        except Exception as e:
            print(f"Không thể kiểm tra /dev/shm: {e}")
    
    # Cập nhật thông tin chiến lược xử lý
    print(f"\n=== CHIẾN LƯỢC XỬ LÝ ===")
    print(f"1. Ưu tiên xử lý trong RAM để tối ưu tốc độ")
    print(f"2. Nếu có đủ RAM (200% kích thước file), sẽ xử lý trong RAM")
    print(f"3. Nếu xử lý trong RAM thất bại, sẽ tự động chuyển sang xử lý trên ổ đĩa")
    print(f"4. Trích xuất subtitle trực tiếp vào thư mục đích")
    print(f"======================\n")

    # Đọc danh sách file đã xử lý
    if force_reprocess:
        processed_files, processed_signatures = {}, {}
        print("[FORCE] Bỏ qua log cũ – sẽ xử lý lại tất cả file trong thư mục.")
    else:
        processed_files, processed_signatures = read_processed_files(log_file)

    # Load cấu hình người dùng
    settings = load_user_config()
    # Nếu force_reprocess được truyền vào, override giá trị từ config
    if force_reprocess is not None:
        settings["force_reprocess"] = force_reprocess

    logs_dir = Path(settings.get("logs_dir", "logs"))

    # Khởi tạo đồng bộ GitHub nếu có cấu hình
    global REMOTE_SYNC, RUN_LOG_ENTRIES
    RUN_LOG_ENTRIES = []
    remote_entries = []
    auto_config = build_auto_push_config(settings)
    if auto_config:
        print("\n[AUTO PUSH] Đã bật đồng bộ subtitle lên GitHub.")
        REMOTE_SYNC = RemoteSyncManager(auto_config)
        # Convert legacy log trên remote nếu còn
        REMOTE_SYNC.convert_remote_legacy_log()
        remote_entries = REMOTE_SYNC.load_remote_logs()
        if remote_entries:
            logs_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = logs_dir / f"remote_sync_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            snapshot_path.write_text(json.dumps(remote_entries, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[AUTO PUSH] Đã lưu log từ repo tại {snapshot_path}")
        if not force_reprocess:
            for entry in remote_entries:
                if entry.get("category") != "video":
                    continue
                info = {
                    "new_name": entry.get("new_name", ""),
                    "time": entry.get("timestamp", ""),
                    "signature": entry.get("signature", ""),
                }
                processed_files[entry.get("old_name", "")] = info
                signature = entry.get("signature")
                if signature:
                    processed_signatures[signature] = info
    else:
        REMOTE_SYNC = None

    # Nếu local vẫn còn log cũ -> chuyển đổi
    legacy_json = convert_legacy_log_file(Path(log_file), logs_dir)
    if legacy_json and legacy_json.exists() and not force_reprocess:
        try:
            legacy_entries = json.loads(legacy_json.read_text(encoding="utf-8"))
            for entry in legacy_entries:
                info = {
                    "new_name": entry.get("new_name", ""),
                    "time": entry.get("timestamp", ""),
                    "signature": entry.get("signature", ""),
                }
                processed_files[entry.get("old_name", "")] = info
                signature = entry.get("signature")
                if signature:
                    processed_signatures[signature] = info
        except Exception as exc:
            print(f"[LOG] Không thể đọc log đã chuyển: {exc}")

    # Đọc file options từ GUI
    file_options_map = {}  # {file_path: options_dict}
    options_env = os.environ.get("MKV_FILE_OPTIONS")
    if options_env:
        try:
            options_data = json.loads(options_env)
            for file_path, opts in options_data.items():
                file_options_map[os.path.abspath(file_path)] = opts
        except json.JSONDecodeError:
            print("[GUI] Không thể phân tích file options. Sẽ dùng mặc định.")

    try:
        mkv_files = [f for f in os.listdir(input_folder) if f.lower().endswith(".mkv")]
        selected_env = os.environ.get("MKV_SELECTED_FILES")
        if selected_env:
            try:
                selected_paths = json.loads(selected_env)
                selected_abs = {os.path.abspath(path) for path in selected_paths}
                mkv_files = [
                    f for f in mkv_files
                    if os.path.abspath(os.path.join(input_folder, f)) in selected_abs
                ]
            except json.JSONDecodeError:
                print("[GUI] Không thể phân tích danh sách file được chọn. Sẽ xử lý toàn bộ.")
        if not mkv_files:
            print("Không tìm thấy file MKV nào trong thư mục hiện tại hoặc danh sách đã chọn trống.")
            return

        total_files = len(mkv_files)
        for file_idx, mkv_file in enumerate(mkv_files, 1):
            file_path = os.path.join(input_folder, mkv_file)
            print(f"Processing file {file_idx}/{total_files}: {mkv_file}")
            print(f"\n===== ĐANG XỬ LÝ FILE: {file_path} =====")
            
            # Hiển thị kích thước file
            file_size = get_file_size_gb(file_path)
            
            # Kiểm tra file đã xử lý bằng tên và signature
            file_signature = get_file_signature(file_path)
            file_abs_path = os.path.abspath(file_path)
            file_opts = file_options_map.get(file_abs_path, {})
            rename_enabled = file_opts.get("rename_enabled", False)
            force_rename = file_opts.get("force_process", False) or rename_enabled
            
            # Nếu file đã xử lý nhưng chỉ cần rename (không có force_reprocess), vẫn tiếp tục
            skip_file = False
            if not force_reprocess and not force_rename:
                if mkv_file in processed_files:
                    print(f"File {mkv_file} đã được xử lý thành {processed_files[mkv_file]['new_name']} vào {processed_files[mkv_file]['time']}. Bỏ qua.")
                    skip_file = True
                elif file_signature and file_signature in processed_signatures:
                    print(f"File {mkv_file} có cùng nội dung với file đã xử lý {processed_signatures[file_signature]['new_name']}. Bỏ qua.")
                    skip_file = True
            elif mkv_file in processed_files and rename_enabled:
                # File đã xử lý nhưng chỉ cần rename, skip extract nhưng vẫn rename
                print(f"File {mkv_file} đã được xử lý. Chỉ thực hiện rename theo yêu cầu...")
                skip_file = False  # Không skip, sẽ rename ở cuối
                skip_extract = True  # Skip extract, chỉ rename
            else:
                skip_extract = False
            
            if skip_file:
                continue

            # Kiểm tra dung lượng trống trước khi xử lý
            try:
                disk_usage = shutil.disk_usage(".")
                free_gb = disk_usage.free / (1024**3)
                if free_gb < file_size * 1.5:
                    print(f"CẢNH BÁO: Không đủ dung lượng trống trên ổ đĩa để xử lý an toàn. Cần ít nhất {file_size * 1.5:.2f} GB, hiện có {free_gb:.2f} GB")
                    response = input("Bạn có muốn tiếp tục mặc dù có thể gặp lỗi? (y/n): ")
                    if response.lower() != 'y':
                        print("Bỏ qua file này.")
                        continue
            except Exception as e:
                print(f"Không thể kiểm tra dung lượng ổ đĩa: {e}")

            # Đọc thông tin file một lần duy nhất
            try:
                probe_data = ffmpeg.probe(file_path)
                audio_streams = [stream for stream in probe_data['streams'] if stream['codec_type'] == 'audio']
                subtitle_streams = [stream for stream in probe_data['streams'] if stream['codec_type'] == 'subtitle']
                
                # In thông tin streams để người dùng biết
                print("\nThông tin streams:")
                print("- Video streams:")
                for i, stream in enumerate([s for s in probe_data['streams'] if s['codec_type'] == 'video']):
                    width = stream.get('width', 'N/A')
                    height = stream.get('height', 'N/A')
                    codec = stream.get('codec_name', 'N/A')
                    print(f"  Stream #{i}: {codec}, {width}x{height}")
                
                print("- Audio streams:")
                for i, stream in enumerate(audio_streams):
                    lang = stream.get('tags', {}).get('language', 'und')
                    title = stream.get('tags', {}).get('title', '')
                    channels = stream.get('channels', 'N/A')
                    codec = stream.get('codec_name', 'N/A')
                    lang_display = f"{get_language_abbreviation(lang)}"
                    if title:
                        lang_display += f" - {title}"
                    print(f"  Stream #{stream.get('index', i)}: {codec}, {channels} channels, {lang_display}")
                
                print("- Subtitle streams:")
                for i, stream in enumerate(subtitle_streams):
                    lang = stream.get('tags', {}).get('language', 'und')
                    title = stream.get('tags', {}).get('title', '')
                    codec = stream.get('codec_name', 'N/A')
                    lang_display = f"{get_language_abbreviation(lang)}"
                    if title:
                        lang_display += f" - {title}"
                    print(f"  Stream #{stream.get('index', i)}: {codec}, {lang_display}")
                
            except Exception as e:
                print(f"Lỗi khi đọc thông tin file {file_path}: {e}")
                # Nếu không thể đọc thông tin file, chỉ rename nếu rename_enabled = True
                if rename_enabled:
                    try:
                        new_path = rename_simple(file_path)
                        log_processed_file(
                            log_file,
                            mkv_file,
                            os.path.basename(new_path),
                            signature=file_signature,
                            metadata={
                                "category": "video",
                                "source_path": file_path,
                                "output_path": os.path.abspath(new_path),
                            },
                        )
                    except Exception as rename_err:
                        print(f"Không thể đổi tên: {rename_err}")
                continue 

            # Kiểm tra subtitle và audio tiếng Việt
            has_vie_subtitle = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                                 for stream in subtitle_streams)
            has_vie_audio = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                               for stream in audio_streams)

            processed = False  # Flag để đánh dấu file đã được xử lý
            
            # Kiểm tra subtitle và audio tiếng Việt (cần cho cả rename logic)
            has_vie_subtitle = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                                 for stream in subtitle_streams)
            has_vie_audio = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                               for stream in audio_streams)

            # Nếu chỉ cần rename (file đã xử lý), skip extract
            if not skip_extract:
                # Xử lý subtitle tiếng Việt
                vie_subtitle_streams = [stream for stream in subtitle_streams
                                        if stream.get('tags', {}).get('language', 'und') == 'vie']
                if vie_subtitle_streams:
                    print(f"\nPhát hiện {len(vie_subtitle_streams)} subtitle tiếng Việt. Bắt đầu trích xuất...")
                for stream in vie_subtitle_streams:
                    subtitle_info = (
                        stream['index'],
                        'vie',
                        stream.get('tags', {}).get('title', ''),
                        stream.get('codec_name', '')
                    )
                    extract_subtitle(file_path, subtitle_info, log_file, probe_data, file_signature=file_signature)

            # Xử lý video nếu có audio tiếng Việt
            if has_vie_audio:
                try:
                    print("\nPhát hiện audio tiếng Việt. Bắt đầu xử lý...")
                    # Tìm audio track tiếng Việt có nhiều kênh nhất
                    vie_audio_tracks = [(stream.get('index', i), stream.get('channels', 0), 'vie', 
                                      stream.get('tags', {}).get('title', 'VIE'))
                                      for i, stream in enumerate(audio_streams)
                                      if stream.get('tags', {}).get('language', 'und') == 'vie']
                    if vie_audio_tracks:
                        # Sắp xếp theo số kênh giảm dần
                        vie_audio_tracks.sort(key=lambda x: x[1], reverse=True)
                        selected_track = vie_audio_tracks[0]
                        print(f"Chọn track audio tiếng Việt index={selected_track[0]} với {selected_track[1]} kênh")
                        extract_video_with_audio(
                            file_path,
                            vn_folder,
                            original_folder,
                            log_file,
                            probe_data,
                            file_signature=file_signature,
                            rename_enabled=rename_enabled,
                        )
                        processed = True  # Đánh dấu file đã được xử lý
                except Exception as e:
                    print(f"Lỗi khi xử lý audio: {e}")

            # Kiểm tra rename_enabled option
            rename_enabled = file_opts.get("rename_enabled", False)
            force_reprocess_file = file_opts.get("force_process", False)
            
            # Chỉ rename khi:
            # 1. force_reprocess = True (ép xử lý lại) VÀ rename_enabled = True
            # 2. File chưa xử lý VÀ rename_enabled = True
            file_already_processed = mkv_file in processed_files or (file_signature and file_signature in processed_signatures)
            should_rename = rename_enabled and (force_reprocess_file or not file_already_processed)
            
            # Nếu chỉ extract SRT (không có audio VIE) và should_rename = True, rename file video
            if not processed and has_vie_subtitle and not has_vie_audio and should_rename:
                print(f"\nĐã extract subtitle. Đổi tên file video theo yêu cầu...")
                try:
                    new_path = rename_simple(file_path)
                    log_processed_file(
                        log_file,
                        mkv_file,
                        os.path.basename(new_path),
                        signature=file_signature,
                        metadata={
                            "category": "video",
                            "source_path": file_path,
                            "output_path": os.path.abspath(new_path),
                        },
                    )
                    print(f"Đã đổi tên file thành: {os.path.basename(new_path)}")
                except Exception as rename_err:
                    print(f"Không thể đổi tên: {rename_err}")
            # Nếu không có cả subtitle và audio tiếng Việt HOẶC xử lý audio thất bại
            # Chỉ rename nếu should_rename = True
            elif (not has_vie_subtitle and not has_vie_audio) or (not processed and not should_rename):
                if not has_vie_subtitle and not has_vie_audio and should_rename:
                    print(f"\nKhông tìm thấy subtitle hoặc audio tiếng Việt. Chỉ đổi tên file...")
                    try:
                        new_path = rename_simple(file_path)
                        log_processed_file(
                            log_file,
                            mkv_file,
                            os.path.basename(new_path),
                            signature=file_signature,
                            metadata={
                                "category": "video",
                                "source_path": file_path,
                                "output_path": os.path.abspath(new_path),
                            },
                        )
                    except Exception as rename_err:
                        print(f"Không thể đổi tên: {rename_err}")

        # Auto-commit subtitles sau khi xử lý xong tất cả files
        print("\n=== HOÀN THÀNH XỬ LÝ ===")
        print("Bắt đầu auto-commit subtitle files...")
        auto_commit_subtitles(subtitle_folder, settings)

        if REMOTE_SYNC:
            REMOTE_SYNC.flush()
        write_run_log_snapshot(logs_dir)

    except Exception as e:
        print(f"Lỗi khi truy cập thư mục '{input_folder}': {e}")
    finally:
        # Khôi phục thư mục làm việc ban đầu
        if need_restore_cwd:
            try:
                os.chdir(original_cwd)
            except:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MKV Processor CLI")
    parser.add_argument("folder", nargs="?", help="Thư mục chứa file MKV")
    parser.add_argument("--force", action="store_true", help="Bỏ qua log cũ, xử lý lại tất cả")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê trạng thái file (không xử lý)")
    args = parser.parse_args()

    if args.folder:
        main(args.folder, force_reprocess=args.force, dry_run=args.dry_run)
    else:
        main(force_reprocess=args.force, dry_run=args.dry_run)