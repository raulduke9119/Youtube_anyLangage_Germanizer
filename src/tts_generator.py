import logging
import torch
import numpy as np
from pathlib import Path
from typing import List, Optional, Literal
import re
import time
import os
import unicodedata

# Import TTS library
try:
    from TTS.api import TTS
except ImportError:
    print("Error: TTS library not found. Please install it: pip install TTS")
    exit(1)

# Import pydub for audio manipulation
try:
    from pydub import AudioSegment
    from pydub.effects import normalize
except ImportError:
     print("Error: pydub library not found. Please install it: pip install pydub")
     exit(1)

# Assuming FileManager is defined elsewhere or passed correctly
# from .file_manager import FileManager

logger = logging.getLogger("YTGermanizerV2.TTSGenerator")

class TTSError(Exception):
    """Custom exception for TTS generation errors."""
    pass

class TTSGenerator:
    """
    Generates speech using Coqui TTS models, with specific handling for XTTS v2.
    """
    SUPPORTED_MODELS = ["xtts", "tacotron2", "bark"] # Add more if needed

    def __init__(
        self,
        model_type: Literal["xtts", "tacotron2", "bark"] = "xtts",
        use_gpu: bool = True,
        file_manager = None, # Pass FileManager instance
        # XTTS specific defaults
        xtts_model_version: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        xtts_default_speaker_wav: Optional[str] = None,
        # Other model defaults (less relevant if focusing on XTTS)
        tacotron_model: str = "tts_models/de/thorsten/tacotron2-DDC",
    ):
        if file_manager is None:
             raise ValueError("FileManager instance is required for TTSGenerator.")
        self.file_manager = file_manager

        if model_type not in self.SUPPORTED_MODELS:
            raise ValueError(f"Unsupported TTS model type: {model_type}. Supported: {self.SUPPORTED_MODELS}")
        self.model_type = model_type

        self.use_gpu = use_gpu and torch.cuda.is_available()
        logger.info(f"TTSGenerator initialized with model: {self.model_type}, GPU: {self.use_gpu}")

        self.model = None
        self.xtts_model_version = xtts_model_version
        self.tacotron_model = tacotron_model
        self.speaker_wav = xtts_default_speaker_wav # Path to the reference audio for XTTS

        # Text processing stats (optional)
        self.text_processing_stats = {'chars_removed': 0, 'replacements_made': 0}

        # Load the model immediately
        self._load_model()

    def _load_model(self):
        """Loads the specified TTS model."""
        logger.info(f"Loading TTS model: {self.model_type}...")
        start_time = time.time()
        try:
            if self.model_type == "xtts":
                self.model = TTS(model_name=self.xtts_model_version, progress_bar=True, gpu=self.use_gpu)
            elif self.model_type == "tacotron2":
                 self.model = TTS(model_name=self.tacotron_model, progress_bar=True, gpu=self.use_gpu)
            elif self.model_type == "bark":
                 # Bark doesn't have a persistent model object in the same way via TTS API
                 # Preload models if necessary (might happen automatically on first use)
                 from bark import preload_models
                 preload_models(text_use_gpu=self.use_gpu, coarse_use_gpu=self.use_gpu, fine_use_gpu=self.use_gpu)
                 self.model = "bark_loaded" # Use a placeholder to indicate loaded
            else:
                 # This case should not be reached due to the check in __init__
                 raise ValueError(f"Trying to load unsupported model type: {self.model_type}")

            load_time = time.time() - start_time
            logger.info(f"{self.model_type.upper()} model loaded successfully in {load_time:.2f} seconds.")

        except Exception as e:
            logger.exception(f"Failed to load TTS model '{self.model_type}': {e}")
            raise TTSError(f"Could not load TTS model '{self.model_type}'. Check installation and model name.")

    def set_speaker_wav(self, speaker_wav_path: Optional[str]):
        """Sets the speaker reference WAV file path for XTTS."""
        if self.model_type != "xtts":
            logger.warning("Speaker WAV is only applicable for the XTTS model.")
            return

        if speaker_wav_path:
            p = Path(speaker_wav_path)
            if not p.exists() or not p.is_file():
                logger.error(f"Speaker WAV file not found: {speaker_wav_path}")
                # Keep existing speaker_wav if the new one is invalid? Or set to None?
                # Setting to None might be safer to avoid using an invalid path.
                self.speaker_wav = None
                raise FileNotFoundError(f"Speaker WAV file not found: {speaker_wav_path}")
            if p.suffix.lower() != '.wav':
                 logger.error(f"Speaker reference must be a WAV file, got: {p.suffix}")
                 self.speaker_wav = None
                 raise ValueError("Speaker reference must be a WAV file.")
            logger.info(f"Set XTTS speaker WAV to: {speaker_wav_path}")
            self.speaker_wav = str(p.resolve())
        else:
            logger.info("Speaker WAV path cleared. XTTS might use its default voice if available.")
            self.speaker_wav = None


    def _clean_text(self, text: str) -> str:
        """Basic text cleaning for TTS."""
        if not isinstance(text, str):
            logger.error(f"Invalid input type for text cleaning: {type(text)}")
            return "" # Return empty string for invalid input

        original_len = len(text)

        # Normalize unicode characters (important for consistency)
        text = unicodedata.normalize('NFKC', text)

        # Remove potentially problematic control characters (except newline/tab)
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)

        # Specific replacements (expand as needed based on model behavior)
        replacements = {
            '„': '"', '“': '"', '”': '"', '’': "'", '‘': "'", '`': "'",
            '–': '-', '—': '-', '…': '...',
            # Keep German characters, but maybe handle ß if model struggles?
            # 'ß': 'ss', # Uncomment if needed
            # Add more replacements if specific issues are found with the model
        }
        replacements_made_count = 0
        for char, replacement in replacements.items():
            count = text.count(char)
            if count > 0:
                text = text.replace(char, replacement)
                replacements_made_count += count

        # Collapse multiple whitespace characters into a single space
        text = re.sub(r'\s+', ' ', text).strip()

        # Update stats (optional)
        self.text_processing_stats['chars_removed'] += original_len - len(text)
        self.text_processing_stats['replacements_made'] += replacements_made_count

        if original_len > 0 and len(text) == 0:
             logger.warning("Text cleaning resulted in an empty string.")

        return text

    def _split_text_for_xtts(self, text: str, max_chars: int = 250) -> List[str]:
        """
        Splits text into chunks suitable for XTTS, trying to respect sentence boundaries.
        XTTS v2 has limitations on input length (around 200-300 chars recommended).
        """
        if not text:
            return []

        # Clean text first
        text = self._clean_text(text)
        if not text:
            return []

        # Use regex to split by sentences more robustly
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If a single sentence is already too long, split it hard (less ideal)
            if len(sentence) > max_chars:
                logger.warning(f"Single sentence exceeds max_chars ({max_chars}), splitting mid-sentence: '{sentence[:100]}...'")
                # Add any existing chunk first
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                # Split the long sentence into smaller parts
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i:i + max_chars])
                continue # Move to the next sentence

            # Check if adding the next sentence exceeds the max length
            if len(current_chunk) + len(sentence) + 1 > max_chars:
                # Add the current chunk if it's not empty
                if current_chunk:
                    chunks.append(current_chunk)
                # Start a new chunk with the current sentence
                current_chunk = sentence
            else:
                # Add the sentence to the current chunk
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence

        # Add the last remaining chunk
        if current_chunk:
            chunks.append(current_chunk)

        # Filter out any potentially empty chunks after processing
        final_chunks = [chunk for chunk in chunks if chunk]
        logger.debug(f"Split text into {len(final_chunks)} chunks for XTTS.")
        return final_chunks

    def _merge_audio_files(self, audio_file_paths: List[str], final_output_path: str, silence_duration_ms: int = 300) -> str:
        """Merges multiple WAV audio files into one using pydub."""
        if not audio_file_paths:
            raise ValueError("No audio file paths provided for merging.")

        logger.info(f"Merging {len(audio_file_paths)} audio chunks into {Path(final_output_path).name}...")
        combined_audio = AudioSegment.empty()
        silence = AudioSegment.silent(duration=silence_duration_ms)

        for i, file_path in enumerate(audio_file_paths):
            try:
                segment = AudioSegment.from_wav(file_path)
                # Optional: Normalize volume of each chunk before merging
                # segment = normalize(segment)
                combined_audio += segment
                # Add silence between segments, but not after the last one
                if i < len(audio_file_paths) - 1:
                    combined_audio += silence
            except Exception as e:
                logger.error(f"Error processing audio chunk {file_path}: {e}")
                # Decide how to handle errors: skip chunk, raise error, etc.
                # For now, let's raise an error to stop the process
                raise TTSError(f"Failed to process audio chunk: {file_path}")

        try:
            # Export the combined audio
            combined_audio.export(final_output_path, format="wav")
            logger.info(f"Successfully merged audio chunks to: {final_output_path}")
            return final_output_path
        except Exception as e:
            logger.exception(f"Failed to export merged audio file: {e}")
            raise TTSError(f"Failed to export merged audio: {e}")

    def _cleanup_temp_chunks(self, chunk_files: List[str]):
        """Deletes temporary audio chunk files."""
        if not chunk_files:
            return
        logger.debug(f"Cleaning up {len(chunk_files)} temporary audio chunk files...")
        for file_path in chunk_files:
            try:
                p = Path(file_path)
                if p.exists():
                    p.unlink()
            except OSError as e:
                logger.warning(f"Could not delete temporary chunk file {file_path}: {e}")

    def generate_speech(self, text: str, language: str = "de") -> str:
        """
        Generates speech for the given text using the configured TTS model.

        Args:
            text: The text to synthesize.
            language: The language code (e.g., "de", "en"). Important for XTTS.

        Returns:
            The path to the generated WAV audio file.

        Raises:
            TTSError: If speech generation fails.
            FileNotFoundError: If speaker_wav is required but not found.
            ValueError: If required parameters are missing (e.g., speaker_wav for XTTS).
        """
        if not text:
            raise ValueError("Input text cannot be empty.")
        if not self.model:
             raise TTSError("TTS model is not loaded. Cannot generate speech.")

        # --- XTTS Specific Handling ---
        if self.model_type == "xtts":
            if not self.speaker_wav:
                 # Check again for default path as a fallback
                 default_path = Path(__file__).parent.parent / "assets/default_german_voice.wav"
                 if default_path.exists():
                      logger.warning("XTTS speaker_wav not set, using default voice from assets.")
                      self.set_speaker_wav(str(default_path))
                 else:
                      logger.error("XTTS model requires a speaker WAV file, but none is set or found.")
                      raise ValueError("Speaker WAV path is required for XTTS model.")
            elif not Path(self.speaker_wav).exists():
                 # This case should be caught by set_speaker_wav, but double-check
                 raise FileNotFoundError(f"Configured speaker WAV file not found: {self.speaker_wav}")

            # Split text for XTTS
            text_chunks = self._split_text_for_xtts(text)
            if not text_chunks:
                 logger.warning("Text resulted in no chunks after splitting for XTTS.")
                 # Create a silent audio file as placeholder?
                 silent_path = self.file_manager.get_temp_path("tts_silent_output", ".wav")
                 AudioSegment.silent(duration=100).export(silent_path, format="wav")
                 return str(silent_path)

            temp_chunk_files = []
            final_output_path = self.file_manager.get_temp_path("tts_xtts_combined", ".wav")

            logger.info(f"Generating speech with XTTS in {len(text_chunks)} chunks...")
            try:
                for i, chunk in enumerate(text_chunks):
                    chunk_start_time = time.time()
                    chunk_output_path = self.file_manager.get_temp_path(f"tts_xtts_chunk_{i+1}", ".wav")
                    temp_chunk_files.append(str(chunk_output_path))
                    logger.debug(f"Generating chunk {i+1}/{len(text_chunks)}: '{chunk[:50]}...'")

                    try:
                        # Generate speech for the chunk
                        self.model.tts_to_file(
                            text=chunk,
                            speaker_wav=self.speaker_wav,
                            language=language,
                            file_path=str(chunk_output_path)
                        )
                        # Verify chunk file
                        if not chunk_output_path.exists() or chunk_output_path.stat().st_size < 100: # Basic check
                             raise TTSError(f"Generated audio chunk {i+1} is invalid or empty.")

                        chunk_time = time.time() - chunk_start_time
                        logger.debug(f"Chunk {i+1} generated in {chunk_time:.2f}s")

                    except Exception as e:
                         logger.exception(f"Error generating TTS for chunk {i+1}: {e}")
                         raise TTSError(f"Failed to generate speech for chunk {i+1}.")

                # Merge the generated chunks
                merged_path = self._merge_audio_files(temp_chunk_files, str(final_output_path))
                return merged_path

            finally:
                 # Clean up temporary chunk files regardless of success/failure
                 self._cleanup_temp_chunks(temp_chunk_files)

        # --- Handling for other models (Tacotron2, Bark) ---
        elif self.model_type == "tacotron2":
             output_path = self.file_manager.get_temp_path("tts_tacotron", ".wav")
             logger.info("Generating speech with Tacotron2...")
             try:
                 cleaned_text = self._clean_text(text)
                 # Tacotron might handle longer inputs better, but chunking could still be beneficial
                 # For simplicity here, generate in one go. Add chunking if needed.
                 self.model.tts_to_file(
                     text=cleaned_text,
                     file_path=str(output_path),
                     speaker=None # Use default Thorsten voice
                 )
                 if not output_path.exists() or output_path.stat().st_size < 100:
                      raise TTSError("Generated Tacotron2 audio is invalid or empty.")
                 logger.info(f"Tacotron2 speech generated: {output_path}")
                 return str(output_path)
             except Exception as e:
                  logger.exception(f"Error generating Tacotron2 speech: {e}")
                  raise TTSError(f"Failed to generate Tacotron2 speech: {e}")

        elif self.model_type == "bark":
             # Bark generation requires different handling (not directly via TTS API object)
             # This implementation assumes bark library is installed and functions are available
             output_path = self.file_manager.get_temp_path("tts_bark", ".wav")
             logger.info("Generating speech with Bark...")
             try:
                 from bark import generate_audio, SAMPLE_RATE
                 from scipy.io.wavfile import write as write_wav

                 # Bark works best with shorter chunks too
                 # Reuse XTTS chunking logic or implement Bark-specific chunking
                 text_chunks = self._split_text_for_xtts(text, max_chars=150) # Bark might prefer shorter chunks
                 if not text_chunks:
                      raise ValueError("Text resulted in no chunks for Bark.")

                 all_audio_arrays = []
                 # Use a generic German history prompt if no specific speaker needed
                 # Find available prompts via bark documentation or experimentation
                 history_prompt = "v2/de_speaker_5" # Example, choose appropriate
                 logger.debug(f"Using Bark history prompt: {history_prompt}")

                 for i, chunk in enumerate(text_chunks):
                      logger.debug(f"Generating Bark chunk {i+1}/{len(text_chunks)}...")
                      audio_array = generate_audio(
                           text=self._clean_text(chunk),
                           history_prompt=history_prompt,
                           # Adjust temps for desired voice characteristics
                           text_temp=0.7,
                           waveform_temp=0.7,
                           output_full=False # Get only the audio array
                      )
                      all_audio_arrays.append(audio_array)

                 # Concatenate arrays and write to file
                 full_audio_array = np.concatenate(all_audio_arrays)
                 write_wav(str(output_path), SAMPLE_RATE, full_audio_array)

                 if not output_path.exists() or output_path.stat().st_size < 100:
                      raise TTSError("Generated Bark audio is invalid or empty.")
                 logger.info(f"Bark speech generated: {output_path}")
                 return str(output_path)

             except ImportError:
                  logger.error("Bark library not found. Cannot generate speech with Bark.")
                  raise TTSError("Bark library not installed.")
             except Exception as e:
                  logger.exception(f"Error generating Bark speech: {e}")
                  raise TTSError(f"Failed to generate Bark speech: {e}")

        else:
            # Should not be reachable
            raise TTSError(f"Speech generation not implemented for model type: {self.model_type}")