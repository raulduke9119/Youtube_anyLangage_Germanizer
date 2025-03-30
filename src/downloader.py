import logging
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional # Add missing import
from yt_dlp import YoutubeDL

# Assuming FileManager is defined elsewhere or passed correctly
# from .file_manager import FileManager # Use relative import if FileManager is in the same package

logger = logging.getLogger("YTGermanizerV2.Downloader")

# Global variable to store the last successful download path as a fallback
_LAST_DOWNLOADED_VIDEO_PATH = None

def download_video(video_url: str, file_manager) -> str:
    """
    Downloads a video from the specified URL using yt-dlp with retries and format fallbacks.

    Args:
        video_url: The URL of the YouTube video.
        file_manager: An instance of the FileManager class to handle paths.

    Returns:
        The absolute path to the downloaded video file as a string.

    Raises:
        FileNotFoundError: If the video download fails after all attempts.
        Exception: For other yt-dlp or unexpected errors.
    """
    global _LAST_DOWNLOADED_VIDEO_PATH
    try:
        logger.info(f"Attempting to download video: {video_url}")

        # Create a unique temporary directory for this download
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use file_manager to get a temp path, but treat it as a directory base
        temp_dir_base = file_manager.get_temp_path(f"video_dl_{timestamp}", "")
        # Ensure the suffix is removed and create the directory
        temp_dir = temp_dir_base.with_suffix("")
        temp_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Using temporary download directory: {temp_dir}")

        # --- yt-dlp Configuration ---
        # Start with the most likely successful format combination
        ydl_opts_base = {
            'outtmpl': str(temp_dir / '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True, # Sometimes helps with network issues
            'ignoreerrors': False, # Stop on errors during extraction/download
            'http_chunk_size': 10485760, # 10MB chunks
            'extractor_retries': 3, # Retry extractor errors
            'retries': 5, # Retry download errors
            'fragment_retries': 5, # Retry fragment download errors
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'progress_hooks': [lambda d: logger.debug(f"yt-dlp status: {d.get('status', 'N/A')}, downloaded: {d.get('_percent_str', 'N/A')}") if d['status'] == 'downloading' else None],
            # Add ffmpeg location if needed, especially on Windows or non-standard setups
            # 'ffmpeg_location': '/path/to/your/ffmpeg',
        }

        # --- Attempt yt-dlp Update ---
        try:
            logger.info("Attempting to update yt-dlp...")
            result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                                    check=True, capture_output=True, text=True, timeout=60)
            logger.info(f"yt-dlp update check completed.\n{result.stdout[-200:]}") # Show last bit of output
        except subprocess.TimeoutExpired:
             logger.warning("yt-dlp update check timed out.")
        except Exception as e:
            logger.warning(f"Could not check for yt-dlp update: {e}\n{getattr(e, 'stderr', '')}")

        # --- Download Attempts ---
        download_attempts = [
            {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'desc': 'Best MP4 video+audio'},
            {'format': 'bestvideo+bestaudio/best', 'desc': 'Best available video+audio (any container)'},
            {'format': 'best', 'desc': 'Best available single file (might be lower quality)'}
        ]

        info = None
        errors = []

        for attempt in download_attempts:
            ydl_opts = ydl_opts_base.copy()
            ydl_opts['format'] = attempt['format']
            logger.info(f"Download attempt with format: '{attempt['desc']}' ({attempt['format']})")
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                # If download successful, break the loop
                logger.info(f"Download successful with format: '{attempt['desc']}'")
                break
            except Exception as e:
                error_msg = f"Attempt '{attempt['desc']}' failed: {type(e).__name__} - {e}"
                logger.warning(error_msg)
                errors.append(error_msg)
                # Clean up potentially incomplete files from this attempt
                for item in temp_dir.glob('*'):
                    if item.is_file() and not item.name.endswith('.part'): # Keep .part files for potential resume
                         try: item.unlink()
                         except OSError: pass
        else:
            # This block executes if the loop completes without a break (all attempts failed)
            error_details = "\n - ".join(errors)
            logger.error(f"All download attempts failed for {video_url}:\n - {error_details}")
            raise Exception(f"Failed to download video after multiple attempts. See logs for details.")

        # --- Find Downloaded File ---
        # yt-dlp should merge into a single file based on outtmpl's extension
        expected_ext = '.mp4' # Default, but could be different based on format
        if info and 'ext' in info:
             expected_ext = f".{info['ext']}"

        downloaded_files = list(temp_dir.glob(f'*{expected_ext}'))
        if not downloaded_files:
             # Fallback: check for any common video extension
             common_exts = ['.mkv', '.webm', '.mov', '.avi', '.flv']
             for ext in common_exts:
                  downloaded_files = list(temp_dir.glob(f'*{ext}'))
                  if downloaded_files:
                       logger.warning(f"Downloaded file has unexpected extension '{ext}'.")
                       break

        if not downloaded_files:
            # Check if any file exists at all
            all_files = list(temp_dir.glob('*.*'))
            logger.error(f"Could not find the final video file in {temp_dir}. Contents: {all_files}")
            raise FileNotFoundError(f"Video downloaded, but the final file could not be located in {temp_dir}.")

        # Assume the largest file is the correct one if multiple exist (unlikely)
        output_path = max(downloaded_files, key=lambda p: p.stat().st_size)

        # Verify file size
        if output_path.stat().st_size < 1024: # Check if file is reasonably sized (e.g., > 1KB)
             logger.error(f"Downloaded video file seems too small: {output_path} ({output_path.stat().st_size} bytes)")
             raise FileNotFoundError(f"Downloaded video file {output_path} is suspiciously small.")

        _LAST_DOWNLOADED_VIDEO_PATH = str(output_path.resolve()) # Store absolute path
        logger.info(f"Video download completed successfully: {_LAST_DOWNLOADED_VIDEO_PATH}")
        return _LAST_DOWNLOADED_VIDEO_PATH

    except Exception as e:
        logger.exception(f"An unexpected error occurred during video download: {e}")
        # Re-raise the exception after logging
        raise

def get_last_downloaded_video_path() -> Optional[str]:
    """Returns the path of the last successfully downloaded video, if any."""
    return _LAST_DOWNLOADED_VIDEO_PATH