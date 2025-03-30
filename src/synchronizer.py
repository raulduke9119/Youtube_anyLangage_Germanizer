import logging
from pathlib import Path
import os
from typing import Optional

# Import moviepy components
try:
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, AudioClip, concatenate_audioclips
    )
    from moviepy.video.fx.all import speedx
    from moviepy.audio.fx.all import volumex, audio_fadein, audio_fadeout
except ImportError:
    print("Error: moviepy library not found. Please install it: pip install moviepy")
    exit(1)

# Assuming FileManager is defined elsewhere or passed correctly
# from .file_manager import FileManager

logger = logging.getLogger("YTGermanizerV2.Synchronizer")

class SyncError(Exception):
    """Custom exception for synchronization errors."""
    pass

class Synchronizer:
    """
    Synchronizes the original video (visuals only) with the newly generated audio track.
    Attempts to handle duration mismatches intelligently.
    """
    def __init__(self, file_manager):
        if file_manager is None:
             raise ValueError("FileManager instance is required for Synchronizer.")
        self.file_manager = file_manager
        # Configuration options (can be made parameters later)
        self.MAX_SPEED_ADJUSTMENT = 0.07 # Max 7% speed change for video
        self.FADE_DURATION = 0.15 # Seconds for audio fades
        self.SIGNIFICANT_DIFF_THRESHOLD = 0.5 # Seconds difference to trigger adjustment

    def _adjust_audio_duration(self, audio_clip: AudioFileClip, target_duration: float) -> AudioFileClip:
        """Adjusts audio duration by trimming or adding silence with fades."""
        duration_diff = audio_clip.duration - target_duration
        abs_diff = abs(duration_diff)
        logger.debug(f"Audio duration: {audio_clip.duration:.2f}s, Target: {target_duration:.2f}s, Diff: {duration_diff:.2f}s")

        if abs_diff < self.SIGNIFICANT_DIFF_THRESHOLD:
             logger.info("Audio duration difference is small, no major adjustment needed.")
             # Still might need slight trim/pad if exact match is desired by moviepy
             return audio_clip.subclip(0, target_duration)

        if duration_diff > 0:  # Audio is longer than video
            logger.info(f"Audio is longer by {abs_diff:.2f}s. Trimming audio...")
            # Trim audio and apply fade out
            trimmed_audio = audio_clip.subclip(0, target_duration)
            adjusted_audio = trimmed_audio.fx(audio_fadeout, self.FADE_DURATION)
            logger.debug(f"Trimmed audio duration: {adjusted_audio.duration:.2f}s")
            return adjusted_audio
        else:  # Audio is shorter than video
            logger.info(f"Audio is shorter by {abs_diff:.2f}s. Padding with silence...")
            silence_duration = abs(duration_diff)
            # Create silence clip - ensure it has 2 channels if original audio is stereo
            # Note: We extracted audio as mono, so silence should be mono too.
            # If stereo is needed later, adjust channel count here.
            # silence = AudioClip(lambda t: [0], duration=silence_duration, fps=audio_clip.fps) # Mono
            # Let moviepy handle silence creation during concatenation if possible
            # For explicit silence:
            temp_silence_path = self.file_manager.get_temp_path("silence_padding", ".wav")
            # Create a short silent WAV file using pydub (assuming mono, 44100Hz)
            from pydub import AudioSegment
            silent_segment = AudioSegment.silent(duration=int(silence_duration * 1000), frame_rate=44100)
            silent_segment.export(temp_silence_path, format="wav")
            silence_clip = AudioFileClip(str(temp_silence_path))


            # Apply fade out to original audio and fade in to silence
            faded_audio = audio_clip.fx(audio_fadeout, self.FADE_DURATION)
            faded_silence = silence_clip.fx(audio_fadein, self.FADE_DURATION)

            # Concatenate
            adjusted_audio = concatenate_audioclips([faded_audio, faded_silence])
            logger.debug(f"Padded audio duration: {adjusted_audio.duration:.2f}s")

            # Clean up temporary silence file
            try:
                 silence_clip.close() # Close file handle before deleting
                 Path(temp_silence_path).unlink()
                 logger.debug(f"Cleaned up temporary silence file: {temp_silence_path}")
            except Exception as e:
                 logger.warning(f"Could not delete temporary silence file {temp_silence_path}: {e}")

            return adjusted_audio

    def sync_audio_with_video(self, video_path: str, audio_path: str) -> str:
        """
        Combines the video (visuals) with the new audio track.

        Args:
            video_path: Path to the original video file.
            audio_path: Path to the newly generated audio file (WAV).

        Returns:
            Path to the final synchronized video file (MP4).

        Raises:
            FileNotFoundError: If input files do not exist.
            SyncError: If synchronization fails.
        """
        video_path_obj = Path(video_path)
        audio_path_obj = Path(audio_path)

        if not video_path_obj.exists():
            raise FileNotFoundError(f"Input video file not found: {video_path}")
        if not audio_path_obj.exists():
            raise FileNotFoundError(f"Input audio file not found: {audio_path}")

        logger.info(f"Starting synchronization for video '{video_path_obj.name}' and audio '{audio_path_obj.name}'")

        video_clip = None
        new_audio_clip = None
        final_video = None

        try:
            # Load video (without its original audio) and the new audio
            logger.debug("Loading video clip...")
            video_clip = VideoFileClip(str(video_path_obj))
            logger.debug("Loading new audio clip...")
            new_audio_clip = AudioFileClip(str(audio_path_obj))

            video_duration = video_clip.duration
            audio_duration = new_audio_clip.duration
            logger.info(f"Original video duration: {video_duration:.2f}s")
            logger.info(f"New audio duration: {audio_duration:.2f}s")

            duration_diff = audio_duration - video_duration

            # --- Adjust Durations ---
            if abs(duration_diff) > self.SIGNIFICANT_DIFF_THRESHOLD:
                 logger.info(f"Significant duration difference detected ({duration_diff:.2f}s). Adjusting...")

                 # Option 1: Adjust Audio (Trim or Pad) - Generally preferred
                 adjusted_audio = self._adjust_audio_duration(new_audio_clip, video_duration)
                 final_audio = adjusted_audio
                 final_video_base = video_clip # Keep original video speed

                 # Option 2: Adjust Video Speed (Use with caution)
                 # speed_factor = audio_duration / video_duration
                 # if abs(speed_factor - 1.0) > self.MAX_SPEED_ADJUSTMENT:
                 #      logger.warning(f"Required speed factor ({speed_factor:.3f}) exceeds limit ({1.0 + self.MAX_SPEED_ADJUSTMENT:.3f}). Clamping.")
                 #      speed_factor = max(1.0 - self.MAX_SPEED_ADJUSTMENT, min(speed_factor, 1.0 + self.MAX_SPEED_ADJUSTMENT))
                 #
                 # logger.info(f"Adjusting video speed by factor: {speed_factor:.3f}")
                 # final_video_base = video_clip.fx(speedx, factor=speed_factor)
                 # final_audio = new_audio_clip # Use original audio if adjusting video speed

            else:
                 logger.info("Durations are close. Performing minimal adjustment if needed.")
                 # Ensure audio matches video duration exactly for moviepy
                 final_audio = new_audio_clip.subclip(0, video_duration)
                 final_video_base = video_clip

            # --- Apply Fades and Volume ---
            # Apply short fades to the final audio to prevent clicks
            final_audio = final_audio.fx(audio_fadein, self.FADE_DURATION).fx(audio_fadeout, self.FADE_DURATION)

            # Optional: Normalize audio volume (can make TTS sound more consistent)
            # final_audio = final_audio.fx(volumex, 1.0) # Example: Set to target volume level
            # Or use a normalization function if available

            # --- Combine and Write Output ---
            logger.info("Setting final audio to video...")
            final_video = final_video_base.set_audio(final_audio)

            output_path = self.file_manager.get_output_path("final_video", ".mp4")
            temp_audio_path = self.file_manager.get_temp_path("temp_audio_sync", ".aac") # Use AAC for MP4

            logger.info(f"Writing final synchronized video to: {output_path}")

            # Define ffmpeg parameters for good quality and compatibility
            # Preset 'fast' is a good balance of speed and quality
            # CRF 23 is standard for H.264
            # AAC audio codec is standard for MP4
            ffmpeg_params = [
                '-preset', 'fast',
                '-crf', '23',
                '-threads', str(min(os.cpu_count() or 1, 8)), # Use multiple threads
                '-strict', '-2', # Needed for AAC codec sometimes
                '-acodec', 'aac',
                '-b:a', '192k', # Audio bitrate
                '-ar', '44100', # Audio sample rate
                '-ac', '2' if final_audio.nchannels > 1 else '1' # Match audio channels
            ]

            final_video.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac', # Specify AAC here as well
                temp_audiofile=str(temp_audio_path),
                remove_temp=True,
                logger='bar', # Show moviepy progress bar
                ffmpeg_params=ffmpeg_params
            )

            # --- Verification ---
            if not output_path.exists() or output_path.stat().st_size < 1024:
                 raise SyncError(f"Output video file seems invalid or empty: {output_path}")

            # Verify audio track exists in the output (optional but recommended)
            try:
                 logger.debug(f"Verifying audio track in final video: {output_path}")
                 check_clip = VideoFileClip(str(output_path))
                 has_audio = check_clip.audio is not None
                 check_clip.close()
                 if not has_audio:
                      raise SyncError("Output video was created but has no audio track.")
                 logger.debug("Audio track verified in output video.")
            except Exception as verify_err:
                 logger.warning(f"Could not verify audio track in output video: {verify_err}")
                 # Don't raise error here, but log warning

            logger.info(f"Video synchronization completed successfully: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.exception(f"An error occurred during synchronization: {e}")
            raise SyncError(f"Synchronization failed: {e}")
        finally:
            # --- Cleanup Moviepy Objects ---
            # Ensure all moviepy objects are closed to release file handles
            if final_video:
                try: final_video.close()
                except Exception: pass
            elif final_video_base: # Close base if final wasn't created
                 try: final_video_base.close()
                 except Exception: pass
            elif video_clip: # Close original if base wasn't created
                 try: video_clip.close()
                 except Exception: pass

            if final_audio:
                 try: final_audio.close()
                 except Exception: pass
            elif new_audio_clip: # Close original audio if final wasn't created/used
                 try: new_audio_clip.close()
                 except Exception: pass
            # Also close adjusted_audio if it was created and different from final_audio
            # (In current logic, adjusted_audio becomes final_audio or isn't used if video speed changes)

            # Cleanup temporary audio file used by moviepy if it wasn't removed
            if 'temp_audio_path' in locals() and temp_audio_path.exists():
                 try:
                      temp_audio_path.unlink()
                      logger.debug(f"Cleaned up moviepy temp audio: {temp_audio_path}")
                 except OSError as e:
                      logger.warning(f"Could not delete moviepy temp audio {temp_audio_path}: {e}")