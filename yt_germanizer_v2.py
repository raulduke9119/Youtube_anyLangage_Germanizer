import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import torch # Check for GPU availability early
import sys
from types import SimpleNamespace # To hold config values easily

# --- Module Imports ---
# Create src directory if it doesn't exist
src_path = Path(__file__).parent / "src"
src_path.mkdir(exist_ok=True)
# Add src to sys.path to allow direct imports
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import core processing modules
from downloader import download_video
from audio_processor import extract_audio, convert_audio_to_mp3, AudioProcessingError
from transcriber import transcribe_audio, Utterance as TranscriberUtterance, TranscriptionError
from translator import translate_text, TranslationError
from tts_generator import TTSGenerator, TTSError
from synchronizer import Synchronizer, SyncError
from file_manager import FileManager
from utils import (
    check_ffmpeg, setup_logging, ask_user_input, ask_yes_no,
    ask_choice, ask_file_path
)

# --- Global Logger ---
# Initial setup, will be reconfigured in main based on user choice
logger = setup_logging(level=logging.WARNING) # Start with WARNING to avoid noise during setup

# --- Main Application Logic ---

def get_user_config() -> SimpleNamespace:
    """Interactively gathers configuration from the user."""
    print("\n--- YT Germanizer v2 Configuration ---")

    config = SimpleNamespace() # Use SimpleNamespace to store config values

    # 1. Video URL
    config.url = ask_user_input("Enter the YouTube video URL")

    # 2. Source Language
    lang_choices = ["en", "es", "fr", "it", "de", "pt", "pl", "ru", "ja", "zh-cn"]
    config.language = ask_choice("Select the source language of the video", lang_choices, default_choice="en")

    # 3. TTS Model
    tts_choices = ["xtts", "tacotron2", "bark"]
    config.tts_model = ask_choice("Select the TTS model for German speech", tts_choices, default_choice="xtts")

    # 4. Speaker WAV (only if XTTS is chosen)
    config.speaker_wav = None
    if config.tts_model == 'xtts':
        print("\nXTTS model requires a reference WAV file (10-30s) for voice cloning.")
        default_wav_path = Path(__file__).parent / "assets/default_german_voice.wav"
        default_wav_str = str(default_wav_path) if default_wav_path.exists() else None

        use_default = False
        if default_wav_str:
             use_default = ask_yes_no(f"Use default voice '{default_wav_path.name}' found in assets?", default_yes=True)

        if use_default:
             config.speaker_wav = default_wav_str
        else:
             config.speaker_wav = ask_file_path(
                 "Enter the path to your speaker WAV file",
                 must_exist=True,
                 is_dir=False,
                 default=None # No default if not using the asset one
             )
             # Re-prompt if path is invalid (ask_file_path handles existence check)
             while config.speaker_wav is None:
                  print("Speaker WAV file is required for XTTS.")
                  config.speaker_wav = ask_file_path(
                      "Enter the path to your speaker WAV file",
                      must_exist=True,
                      is_dir=False
                  )

    # 5. AssemblyAI API Key
    config.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not config.api_key:
        config.api_key = ask_user_input("Enter your AssemblyAI API key (or set ASSEMBLYAI_API_KEY env var)")
    else:
        print(f"Using AssemblyAI API key found in environment variable.")
        if ask_yes_no("Do you want to enter a different API key?", default_yes=False):
             config.api_key = ask_user_input("Enter your AssemblyAI API key")

    # 6. GPU Usage
    gpu_available = torch.cuda.is_available()
    if gpu_available:
        config.use_gpu = ask_yes_no("Use GPU for processing (recommended)?", default_yes=True)
    else:
        print("CUDA not available. GPU processing disabled.")
        config.use_gpu = False

    # 7. Log Level
    log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    config.log_level = ask_choice("Select the logging level", log_levels, default_choice="INFO")

    # 8. Cleanup
    config.skip_cleanup = ask_yes_no("Skip cleanup of temporary files after processing?", default_yes=False)

    print("\n--- Configuration Complete ---")
    # Log the chosen config
    logger.info("User Configuration:")
    for key, value in vars(config).items():
         # Avoid logging full API key
         log_value = "****" + value[-4:] if key == 'api_key' and value else value
         logger.info(f"  {key}: {log_value}")
    print("-" * 30)

    return config

def run_pipeline(config: SimpleNamespace):
    """Executes the video processing pipeline with the given configuration."""
    logger.info("Starting YT Germanizer v2 Pipeline...")
    try:
        check_ffmpeg()
    except EnvironmentError as e:
         logger.error(f"Prerequisite check failed: {e}")
         print(f"\n❌ Error: {e}. Please ensure FFmpeg is installed and in your PATH.")
         return # Stop execution if ffmpeg is missing

    file_manager = FileManager() # Uses default base dir "processing_files"

    video_path = None
    audio_path = None
    tts_audio_path = None
    final_video_path = None
    pipeline_successful = False

    try:
        # --- Step 1: Download Video ---
        logger.info("[Step 1/6] Downloading video...")
        print("\n[1/6] Downloading video...")
        video_path = download_video(config.url, file_manager)
        logger.info(f"Video downloaded to: {video_path}")
        print(f"      Downloaded: {Path(video_path).name}")

        # --- Step 2: Extract Audio ---
        logger.info("[Step 2/6] Extracting audio...")
        print("[2/6] Extracting audio...")
        audio_path = extract_audio(video_path, file_manager)
        logger.info(f"Audio extracted to: {audio_path}")
        print(f"      Extracted: {Path(audio_path).name}")

        # --- Step 3: Transcribe Audio ---
        logger.info("[Step 3/6] Transcribing audio...")
        print("[3/6] Transcribing audio (this may take a while)...")
        # Pass audio_processor module for MP3 conversion within transcribe_audio
        import audio_processor
        utterances: list[TranscriberUtterance] = transcribe_audio(
            audio_path=audio_path,
            language_code=config.language,
            api_key=config.api_key,
            file_manager=file_manager,
            audio_processor=audio_processor
            # speakers_expected=None, # Add interactive prompt later if needed
        )
        if not utterances: raise ValueError("Transcription returned no utterances.")
        transcribed_text = " ".join(u.text for u in utterances if isinstance(u, TranscriberUtterance))
        logger.info(f"Transcription complete: {len(utterances)} utterances.")
        logger.debug(f"Transcription Text: {transcribed_text}")
        print(f"      Transcription complete ({len(utterances)} utterances).")

        # --- Step 4: Translate Text ---
        logger.info("[Step 4/6] Translating text...")
        print("[4/6] Translating text...")
        translated_text = translate_text(transcribed_text, target_lang="de", source_lang=config.language)
        if not translated_text: raise ValueError("Translation returned empty text.")
        logger.info("Translation complete.")
        logger.debug(f"Translated Text: {translated_text}")
        print(f"      Translation complete.")

        # --- Step 5: Generate TTS Audio ---
        logger.info("[Step 5/6] Generating TTS audio...")
        print(f"[5/6] Generating TTS audio using {config.tts_model} (this can take time)...")
        tts_generator = TTSGenerator(
            model_type=config.tts_model,
            use_gpu=config.use_gpu,
            file_manager=file_manager
        )
        if config.tts_model == 'xtts':
            tts_generator.set_speaker_wav(config.speaker_wav)

        tts_audio_path = tts_generator.generate_speech(translated_text, language="de")
        if not Path(tts_audio_path).exists() or Path(tts_audio_path).stat().st_size == 0:
             raise FileNotFoundError(f"TTS generation failed or produced an empty file: {tts_audio_path}")
        logger.info(f"TTS audio generated: {tts_audio_path}")
        print(f"      TTS audio generated: {Path(tts_audio_path).name}")

        # --- Step 6: Synchronize Video and Audio ---
        logger.info("[Step 6/6] Synchronizing video and audio...")
        print("[6/6] Synchronizing video and audio...")
        synchronizer = Synchronizer(file_manager=file_manager)
        final_video_path = synchronizer.sync_audio_with_video(video_path, tts_audio_path)
        logger.info(f"Synchronization complete. Final video: {final_video_path}")
        print(f"      Synchronization complete.")

        logger.info("Pipeline finished successfully!")
        print(f"\n✅ Success! Final video saved to: {final_video_path}")
        pipeline_successful = True

    # Specific error handling for different stages
    except FileNotFoundError as e:
         logger.error(f"File not found error during pipeline: {e}")
         print(f"\n❌ Error: A required file was not found ({e}). Check paths and permissions.")
    except (AudioProcessingError, TranscriptionError, TranslationError, TTSError, SyncError) as e:
         logger.error(f"Error in pipeline step: {e}")
         print(f"\n❌ Error: {e}")
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"An unexpected error occurred during the pipeline: {e}")
        print(f"\n❌ An unexpected error occurred: {e}. Check logs/yt_germanizer_v2.log for details.")
    finally:
        # --- Cleanup ---
        if not config.skip_cleanup:
            print("\nPerforming cleanup...")
            # Pass the specific file manager instance used in the pipeline
            if 'file_manager' in locals():
                 file_manager.cleanup_temp_files()
                 # Only clean old outputs if the pipeline was successful? Or always?
                 # Cleaning always might remove useful outputs from failed runs.
                 # Let's clean only on success for now.
                 if pipeline_successful:
                      file_manager.cleanup_old_outputs()
                 else:
                      logger.info("Skipping old output cleanup due to pipeline failure.")
            else:
                 logger.warning("FileManager not initialized, cannot perform cleanup.")
            logger.info("Cleanup finished.")
        else:
            logger.info("Skipping cleanup as requested.")
            print("Cleanup skipped.")


def main():
    """Main function to get config and run the pipeline."""
    # Load .env file if it exists
    load_dotenv()

    # Get configuration interactively
    try:
        config = get_user_config()
    except EOFError: # Handle Ctrl+D or premature end of input
         print("\nConfiguration aborted.")
         return 1
    except KeyboardInterrupt: # Handle Ctrl+C
         print("\nConfiguration cancelled by user.")
         return 1

    # Reconfigure logging based on user choice AFTER getting config
    global logger
    logger = setup_logging(level=getattr(logging, config.log_level.upper()))

    # Validate API Key again after potential interactive input
    if not config.api_key:
        logger.error("AssemblyAI API key is missing.")
        print("\n❌ Error: AssemblyAI API key is required.")
        return 1

    # Run the main processing pipeline
    try:
        run_pipeline(config)
        return 0 # Indicate success
    except KeyboardInterrupt:
         print("\nPipeline interrupted by user.")
         # Perform cleanup even if interrupted? Maybe based on a flag?
         # For now, let cleanup run in the finally block of run_pipeline
         return 1
    except Exception:
         # Errors are logged within run_pipeline's try/except block
         return 1 # Indicate failure


if __name__ == "__main__":
    # Initialize logger with default level first
    logger = setup_logging()
    exit_code = main()
    sys.exit(exit_code) # Use sys.exit for cleaner exit code handling