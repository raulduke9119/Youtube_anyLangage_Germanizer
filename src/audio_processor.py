import logging
import subprocess
from pathlib import Path

# Assuming FileManager is defined elsewhere or passed correctly
# from .file_manager import FileManager

logger = logging.getLogger("YTGermanizerV2.AudioProcessor")

class AudioProcessingError(Exception):
    """Custom exception for audio processing errors."""
    pass

def extract_audio(video_path: str, file_manager) -> str:
    """
    Extracts audio from the specified video file using ffmpeg and saves it as WAV.

    Args:
        video_path: Path to the input video file.
        file_manager: An instance of the FileManager class.

    Returns:
        Path to the extracted WAV audio file.

    Raises:
        FileNotFoundError: If the input video file does not exist.
        AudioProcessingError: If ffmpeg fails or the output file is invalid.
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Input video file not found: {video_path}")

    # Use file_manager to get a temporary path for the output WAV
    audio_output_path = file_manager.get_temp_path("extracted_audio", ".wav")
    logger.info(f"Extracting audio from '{video_path_obj.name}' to '{audio_output_path.name}'...")

    try:
        # ffmpeg command:
        # -i: input file
        # -vn: disable video recording (audio only)
        # -acodec pcm_s16le: standard WAV codec (16-bit PCM)
        # -ar 44100: standard audio sample rate (CD quality) - AssemblyAI prefers 16000Hz, but 44100 is safer for TTS later
        # -ac 1: mono audio (required by some TTS/STT, reduces size)
        # -y: overwrite output file without asking
        cmd = [
            "ffmpeg",
            "-i", str(video_path_obj),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100", # Keep high quality for potential TTS cloning later
            "-ac", "1",
            "-y", str(audio_output_path),
        ]
        logger.debug(f"Executing ffmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False) # Don't check=True initially

        if result.returncode != 0:
             logger.error(f"FFmpeg failed to extract audio. Return code: {result.returncode}")
             logger.error(f"FFmpeg stderr:\n{result.stderr}")
             raise AudioProcessingError(f"FFmpeg failed during audio extraction. Check logs for details.")

        # Verify output file
        if not audio_output_path.exists() or audio_output_path.stat().st_size == 0:
            logger.error(f"Audio extraction failed: Output file is empty or doesn't exist at {audio_output_path}")
            raise AudioProcessingError("Audio extraction produced an invalid file.")

        logger.info(f"Audio successfully extracted to: {audio_output_path}")
        return str(audio_output_path)

    except subprocess.CalledProcessError as e:
        # This might not be reached if check=False, but keep for safety
        logger.error(f"FFmpeg command failed: {e}")
        logger.error(f"FFmpeg stderr:\n{e.stderr}")
        raise AudioProcessingError(f"FFmpeg failed during audio extraction: {e}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred while extracting audio: {e}")
        raise AudioProcessingError(f"An unexpected error occurred during audio extraction: {e}")


def convert_audio_to_mp3(input_path: str, file_manager) -> str:
    """
    Converts the specified audio file to MP3 format using ffmpeg.
    Required for AssemblyAI transcription if the input is not already MP3.

    Args:
        input_path: Path to the input audio file (e.g., WAV).
        file_manager: An instance of the FileManager class.

    Returns:
        Path to the converted MP3 file.

    Raises:
        FileNotFoundError: If the input audio file does not exist.
        AudioProcessingError: If ffmpeg fails or the output file is invalid.
    """
    input_path_obj = Path(input_path)
    if not input_path_obj.exists():
        raise FileNotFoundError(f"Input audio file not found: {input_path}")

    # Use file_manager to get a temporary path for the output MP3
    output_path_obj = file_manager.get_temp_path("converted_audio", ".mp3")
    logger.info(f"Converting '{input_path_obj.name}' to MP3 format at '{output_path_obj.name}'...")

    try:
        # ffmpeg command:
        # -i: input file
        # -acodec libmp3lame: MP3 codec
        # -ab 192k: audio bitrate (good quality)
        # -ar 44100: sample rate (match input if possible, or standard)
        # -ac 1: mono audio (often preferred for STT)
        # -y: overwrite output file without asking
        cmd = [
            "ffmpeg",
            "-i", str(input_path_obj),
            "-acodec", "libmp3lame",
            "-ab", "192k",
            "-ar", "44100", # Match sample rate if possible
            "-ac", "1",
            "-y", str(output_path_obj),
        ]
        logger.debug(f"Executing ffmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False) # Don't check=True initially

        if result.returncode != 0:
             logger.error(f"FFmpeg failed to convert audio to MP3. Return code: {result.returncode}")
             logger.error(f"FFmpeg stderr:\n{result.stderr}")
             raise AudioProcessingError(f"FFmpeg failed during MP3 conversion. Check logs for details.")

        # Verify output file
        if not output_path_obj.exists() or output_path_obj.stat().st_size == 0:
            logger.error(f"Audio conversion failed: Output MP3 file is empty or doesn't exist at {output_path_obj}")
            raise AudioProcessingError("Audio conversion to MP3 produced an invalid file.")

        logger.info(f"Audio successfully converted to MP3: {output_path_obj}")
        return str(output_path_obj)

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg command failed: {e}")
        logger.error(f"FFmpeg stderr:\n{e.stderr}")
        raise AudioProcessingError(f"FFmpeg failed during MP3 conversion: {e}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred while converting audio to MP3: {e}")
        raise AudioProcessingError(f"An unexpected error occurred during MP3 conversion: {e}")