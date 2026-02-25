"""
Video processing functions for MKV Processor.

Handles video file processing, audio extraction, and file renaming.
"""
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import ffmpeg  # type: ignore

from .utils.file_utils import create_folder, get_file_size_gb, sanitize_filename
from .utils.metadata_utils import (
    get_language_abbreviation,
    get_movie_year,
    get_video_resolution_label,
)
from .utils.system_utils import check_available_ram
from .log_manager import log_processed_file
from .ffmpeg_helper import get_ffmpeg_command
from .utils.temp_utils import temp_directory_in_memory
from .utils.ffmpeg_runner import run_ffmpeg_command

logger = logging.getLogger(__name__)


def rename_simple(file_path: Union[str, Path]) -> Union[str, Path]:
    """Simple rename for files without audio to extract.
    
    Args:
        file_path: Path to video file
    
    Returns:
        New file path after renaming
    """
    try:
        resolution_label = get_video_resolution_label(str(file_path))
        probe = ffmpeg.probe(str(file_path))
        # Get language from first audio stream
        audio_stream = next((stream for stream in probe['streams'] 
                           if stream['codec_type'] == 'audio'), None)
        language = 'und'  # default is undefined
        audio_title = ''
        if audio_stream:
            language = audio_stream.get('tags', {}).get('language', 'und')
            audio_title = audio_stream.get('tags', {}).get('title', '')
        
        language_abbr = get_language_abbreviation(language)
        # Only add audio_title if different from language_abbr and not empty
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
        logger.info(f"Simple renamed file to: {new_name}")
        return new_path
    except Exception as e:
        logger.error(f"Error simple renaming file {file_path}: {e}")
        return file_path


def rename_file(file_path: Union[str, Path], audio_info: Tuple[int, int, str, str], is_output: bool = False) -> str:
    """Rename file according to required format.
    
    Args:
        file_path: Path to video file
        audio_info: Tuple of (index, channels, language, title)
        is_output: Whether this is an output file
    
    Returns:
        New filename
    """
    try:
        resolution_label = get_video_resolution_label(str(file_path))
        year = get_movie_year(str(file_path))
        language = audio_info[2]  # Language code
        audio_title = audio_info[3]  # Audio title
        
        language_abbr = get_language_abbreviation(language)
        
        # Only add audio_title if different from language_abbr and not empty
        if audio_title and audio_title != language_abbr:
            lang_part = f"{language_abbr}_{audio_title}"
        else:
            lang_part = language_abbr
        
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Format: Resolution_Language_Year_BaseName.mkv
        if year:
            new_name = f"{resolution_label}_{lang_part}_{year}_{base_name}.mkv"
        else:
            new_name = f"{resolution_label}_{lang_part}_{base_name}.mkv"
        
        new_name = sanitize_filename(new_name)
        return new_name
    except Exception as e:
        logger.error(f"Error renaming file {file_path}: {e}")
        return os.path.basename(file_path)


def process_video(
    file_path: Union[str, Path],
    output_folder: str,
    selected_track: Tuple[int, int, str, str],
    log_file: Union[str, Path],
    probe_data: Dict,
    file_signature: Optional[str] = None,
    rename_enabled: bool = False,
) -> bool:
    """Process video with selected audio track and extract subtitles.
    
    Args:
        file_path: Path to input video file
        output_folder: Output directory
        selected_track: Track index to extract (index, channels, language, title)
        log_file: Path to log file
        probe_data: FFprobe metadata
        file_signature: Optional file signature for deduplication
        rename_enabled: Whether to rename output files
    
    Returns:
        True if processing succeeded, False otherwise
    """
    try:
        original_filename = os.path.basename(file_path)
        
        # Get basic information
        resolution_label = get_video_resolution_label(str(file_path))
        year = get_movie_year(str(file_path))
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Get first audio information
        first_audio = next((stream for stream in probe_data['streams'] 
                          if stream['codec_type'] == 'audio'), None)
        
        if first_audio:
            first_audio_lang = first_audio.get('tags', {}).get('language', 'und')
            first_audio_title = first_audio.get('tags', {}).get('title', '')
            # Use title only when different from language abbreviation
            first_audio_display = get_language_abbreviation(first_audio_lang)
            if first_audio_title and first_audio_title != first_audio_display:
                first_audio_display += f"_{first_audio_title}"
            
            # Similar logic for selected track
            selected_lang_abbr = get_language_abbreviation(selected_track[2])
            selected_title = selected_track[3]
            selected_display = selected_lang_abbr
            if selected_title and selected_title != selected_lang_abbr:
                selected_display += f"_{selected_title}"
            
            # Format filename
            if first_audio_lang == 'vie':
                source_name = f"{resolution_label}_{first_audio_display}"
                output_name = f"{resolution_label}_{selected_display}"
            else:
                source_name = f"{resolution_label}_{first_audio_display}"
                output_name = f"{resolution_label}_{selected_display}"
            
            # Add year and original name
            if year:
                source_name += f"_{year}"
                output_name += f"_{year}"
            source_name += f"_{base_name}.mkv"
            output_name += f"_{base_name}.mkv"
            
            # Final output path
            final_output_path = os.path.join(output_folder, sanitize_filename(output_name))
            
            # Check if destination file already exists
            if os.path.exists(final_output_path):
                logger.warning(f"Destination file already exists: {final_output_path}. Skipping.")
                return True
            
            # Check available disk space
            try:
                output_dir = os.path.dirname(final_output_path)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                disk_usage = shutil.disk_usage(output_dir)
                free_space_gb = disk_usage.free / (1024**3)
                logger.info(f"Free disk space: {free_space_gb:.2f} GB")
                
                if free_space_gb < 2:  # Need at least 2GB free space for safety
                    logger.warning(f"WARNING: Too little free disk space. Need at least 2GB")
                    return False
            except Exception as disk_err:
                logger.error(f"Error checking disk space: {disk_err}")
            
            # Check available RAM
            file_size = get_file_size_gb(file_path)
            available_ram = check_available_ram()
            
            # Prefer processing in RAM if enough RAM available
            ram_required = file_size * 2  # Need at least 200% of file size
            try_ram_first = available_ram > ram_required
            
            if try_ram_first:
                logger.info(f"Enough RAM to process file ({available_ram:.2f}GB > {ram_required:.2f}GB). Trying RAM processing...")
                
                # Process in RAM
                ram_success = False
                try:
                    with temp_directory_in_memory(use_ram=True, file_size_gb=file_size) as temp_dir:
                        # Temporary path in RAM
                        temp_output_path = os.path.join(temp_dir, sanitize_filename(output_name))
                        
                        # Process audio extraction in RAM
                        cmd = [
                            'ffmpeg',
                            '-i', str(file_path),
                            '-map', '0:v',
                            '-map', f'0:{selected_track[0]}',
                            '-c', 'copy',
                            '-y',
                            temp_output_path
                        ]
                        
                        logger.debug(f"Running command in RAM: {' '.join(cmd)}")
                        result = run_ffmpeg_command(cmd, capture_output=True)
                        
                        if result.returncode == 0 and os.path.exists(temp_output_path):
                            logger.info(f"RAM processing successful. Moving file to: {final_output_path}")
                            shutil.copy2(temp_output_path, final_output_path)
                            ram_success = True
                except Exception as ram_error:
                    logger.error(f"Error processing in RAM: {ram_error}")
                
                # If RAM processing succeeded
                if ram_success and os.path.exists(final_output_path):
                    logger.info(f"Video processed successfully: {final_output_path}")
                    
                    # Log processed file
                    log_processed_file(
                        log_file,
                        original_filename,
                        os.path.basename(final_output_path),
                        signature=file_signature,
                        metadata={
                            "category": "video",
                            "source_path": str(file_path),
                            "output_path": os.path.abspath(final_output_path),
                            "language": selected_track[2],
                        },
                    )
                    return True
                else:
                    logger.warning("RAM processing failed. Switching to disk processing...")
            else:
                logger.info(f"Insufficient RAM. Processing directly on disk.")
            
            # Process directly to destination if cannot process in RAM
            logger.info(f"Processing video directly to: {final_output_path}")
            
            # FFmpeg command to extract audio
            cmd = [
                'ffmpeg',
                '-i', str(file_path),
                '-map', '0:v',
                '-map', f'0:{selected_track[0]}',
                '-c', 'copy',
                '-y',
                final_output_path
            ]
            
            logger.debug(f"Running command on disk: {' '.join(cmd)}")
            result = run_ffmpeg_command(cmd, capture_output=True)
            
            if result.returncode == 0 and os.path.exists(final_output_path):
                logger.info(f"Video processed successfully: {final_output_path}")
                
                # Log processed file
                log_processed_file(
                    log_file,
                    original_filename,
                    os.path.basename(final_output_path),
                    signature=file_signature,
                    metadata={
                        "category": "video",
                        "source_path": str(file_path),
                        "output_path": os.path.abspath(final_output_path),
                        "language": selected_track[2],
                    },
                )
                return True
            else:
                logger.error("Error processing video directly")
                if result.stderr:
                    stderr_text = result.stderr.decode('utf-8', errors='replace')
                    logger.error(f"FFmpeg error: {stderr_text}")
                return False
        else:
            logger.warning(f"No audio stream found in {file_path}")
            return False
            
    except Exception as e:
        logger.error(f"Exception while processing {file_path}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def extract_video_with_audio(
    file_path: Union[str, Path],
    vn_folder: str,
    original_folder: str,
    log_file: Union[str, Path],
    probe_data: Dict,
    file_signature: Optional[str] = None,
    rename_enabled: bool = False,
) -> None:
    """Extract video with audio as required.
    
    Args:
        file_path: Path to video file
        vn_folder: Folder for Vietnamese audio output
        original_folder: Folder for original audio output
        log_file: Path to log file
        probe_data: FFprobe metadata
        file_signature: Optional file signature
        rename_enabled: Whether to rename output files
    """
    try:
        audio_streams = [stream for stream in probe_data['streams'] if stream['codec_type'] == 'audio']
        
        if not audio_streams:
            if rename_enabled:
                logger.info(f"No audio found in {file_path}. Performing simple rename.")
                new_path = rename_simple(file_path)
                log_processed_file(
                    log_file,
                    os.path.basename(file_path),
                    os.path.basename(new_path),
                    signature=file_signature,
                    metadata={
                        "category": "video",
                        "source_path": str(file_path),
                        "output_path": os.path.abspath(new_path),
                    },
                )
            return

        # Get first audio information to determine case
        first_audio = audio_streams[0]
        first_audio_language = first_audio.get('tags', {}).get('language', 'und')

        # Create list of audio tracks with necessary information
        audio_tracks = []
        for stream in audio_streams:
            index = stream.get('index', -1)
            channels = stream.get('channels', 0)
            language = stream.get('tags', {}).get('language', 'und')
            title = stream.get('tags', {}).get('title', get_language_abbreviation(language))
            audio_tracks.append((index, channels, language, title))

        # Sort by channel count descending
        audio_tracks.sort(key=lambda x: x[1], reverse=True)
        
        vietnamese_tracks = [track for track in audio_tracks if track[2] == 'vie']
        non_vietnamese_tracks = [track for track in audio_tracks if track[2] != 'vie']

        if first_audio_language == 'vie':
            # Case 1: First audio is Vietnamese
            if non_vietnamese_tracks:
                # Select non-Vietnamese audio with most channels
                selected_track = non_vietnamese_tracks[0]
                process_video(file_path, original_folder, selected_track, log_file, probe_data, file_signature=file_signature, rename_enabled=rename_enabled)
        else:
            # Case 2: First audio is not Vietnamese
            if vietnamese_tracks:
                # Select Vietnamese audio with most channels
                selected_track = vietnamese_tracks[0]
                process_video(file_path, vn_folder, selected_track, log_file, probe_data, file_signature=file_signature, rename_enabled=rename_enabled)

    except Exception as e:
        logger.error(f"Exception while processing {file_path}: {e}")

