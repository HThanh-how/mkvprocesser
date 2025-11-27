"""
Subtitle extraction functions for MKV Processor.

Handles subtitle extraction from video files.
"""
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Union

from .utils.file_utils import create_folder, sanitize_filename
from .utils.system_utils import check_available_ram
from .utils.temp_utils import temp_directory_in_memory
from .utils.ffmpeg_runner import run_ffmpeg_command
from .log_manager import log_processed_file

logger = logging.getLogger(__name__)


def extract_subtitle(
    file_path: Union[str, Path],
    subtitle_info: Tuple[int, str, str, str],
    log_file: Union[str, Path],
    probe_data: dict,
    file_signature: Optional[str] = None,
) -> Optional[str]:
    """Extract Vietnamese subtitle from video file.
    
    Args:
        file_path: Path to video file
        subtitle_info: Tuple of (index, language, title, codec)
        log_file: Path to log file
        probe_data: FFprobe metadata
        file_signature: Optional file signature
    
    Returns:
        Path to extracted subtitle file, or None if extraction fails
    """
    try:
        # Create ./Subtitles folder if it doesn't exist
        sub_root_folder = os.path.join(".", "Subtitles")
        create_folder(sub_root_folder)
        
        index, language, title, codec = subtitle_info
        
        # Only process text-based subtitle formats
        text_based_codecs = ['srt', 'ass', 'ssa', 'subrip']
        if codec.lower() not in text_based_codecs:
            logger.warning(f"Skipping subtitle: format {codec} not supported (only text-based formats)")
            return None
            
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Shorten filename if too long
        if len(base_name) > 100:
            base_name = base_name[:100]
        
        # Set subtitle filename keeping original name and adding language code
        sub_filename = sanitize_filename(f"{base_name}_{language}.srt")
        final_output_path = os.path.join(sub_root_folder, sub_filename)
        
        # Check if subtitle already exists
        if os.path.exists(final_output_path):
            logger.info(f"Subtitle already exists: {final_output_path}. Skipping.")
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
        
        # Check available RAM - subtitles are usually small so require less RAM
        available_ram = check_available_ram()
        logger.info(f"Processing subtitle with {available_ram:.2f} GB available RAM")
        
        # Prefer processing in RAM if enough RAM (>= 0.5GB)
        try_ram_first = available_ram >= 0.5
        
        if try_ram_first:
            logger.info(f"Trying to extract subtitle in RAM...")
            
            # Process in RAM
            ram_success = False
            try:
                with temp_directory_in_memory(use_ram=True, file_size_gb=None) as temp_dir:
                    # Temporary path in RAM
                    temp_output_path = os.path.join(temp_dir, sub_filename)
                    
                    # FFmpeg command to extract subtitle to RAM
                    cmd = [
                        'ffmpeg',
                        '-i', str(file_path),
                        '-map', f'0:{index}',
                        '-c:s', 'srt',
                        '-y',
                        temp_output_path
                    ]
                    
                    logger.debug(f"Running command in RAM: {' '.join(cmd)}")
                    result = run_ffmpeg_command(cmd, capture_output=True)
                    
                    if result.returncode == 0 and os.path.exists(temp_output_path):
                        logger.info(f"Extraction in RAM successful. Moving file to: {final_output_path}")
                        # Move from RAM to disk
                        shutil.copy2(temp_output_path, final_output_path)
                        ram_success = True
            except Exception as ram_error:
                logger.error(f"Error processing in RAM: {ram_error}")
                
            # If RAM processing succeeded
            if ram_success and os.path.exists(final_output_path):
                logger.info(f"Subtitle saved successfully to: {final_output_path}")
                
                # Log processed file
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
                logger.warning("RAM processing failed. Switching to direct disk processing...")
        else:
            logger.info(f"Insufficient RAM. Processing directly on disk.")
        
        # Process directly to destination if cannot process in RAM
        logger.info(f"Extracting subtitle directly to: {final_output_path}")
        
        # FFmpeg command to extract subtitle
        cmd = [
            'ffmpeg',
            '-i', str(file_path),
            '-map', f'0:{index}',
            '-c:s', 'srt',
            '-y',
            final_output_path
        ]
        
        logger.debug(f"Running command on disk: {' '.join(cmd)}")
        result = run_ffmpeg_command(cmd, capture_output=True)
        
        if result.returncode == 0 and os.path.exists(final_output_path):
            logger.info(f"Subtitle extracted successfully: {final_output_path}")
            
            # Log processed file
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
            logger.error("Error extracting subtitle directly")
            if result.stderr:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
                logger.error(f"Error: {stderr_text}")
            
            # Try alternative method if above fails
            logger.info("Trying alternative method to extract subtitle...")
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_output_path = os.path.join(temp_dir, sub_filename)
                
                alt_cmd = [
                    'ffmpeg',
                    '-i', str(file_path),
                    '-map', f'0:{index}',
                    '-f', 'srt',
                    '-y',
                    temp_output_path
                ]
                
                logger.debug(f"Running alternative command: {' '.join(alt_cmd)}")
                alt_result = run_ffmpeg_command(alt_cmd, capture_output=True)
                
                if alt_result.returncode == 0 and os.path.exists(temp_output_path):
                    logger.info(f"Subtitle extracted temporarily: {temp_output_path}")
                    # Move to final path
                    shutil.move(temp_output_path, final_output_path)
                    logger.info(f"Subtitle moved to: {final_output_path}")
                    
                    # Log processed file
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
                    logger.error("Unable to extract subtitle using both methods")
                    if alt_result.stderr:
                        stderr_text = alt_result.stderr.decode('utf-8', errors='replace')
                        logger.error(f"Error: {stderr_text}")
                    return None
    except Exception as e:
        logger.error(f"Error extracting subtitle: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

