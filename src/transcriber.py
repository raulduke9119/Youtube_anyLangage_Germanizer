import logging
import requests
import time
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Assuming FileManager and audio_processor are defined elsewhere or passed correctly
# from .file_manager import FileManager
# from .audio_processor import convert_audio_to_mp3, AudioProcessingError

logger = logging.getLogger("YTGermanizerV2.Transcriber")

# Define Utterance dataclass here or import if defined centrally
@dataclass
class Utterance:
    """Represents a single utterance in the transcription."""
    speaker: str
    text: str
    start: int  # milliseconds
    end: int    # milliseconds
    confidence: float
    words: List[Dict[str, Any]]
    gender: str # Added gender based on speaker analysis

class TranscriptionError(Exception):
    """Custom exception for transcription-related errors."""
    pass

def upload_audio(audio_path: str, api_key: str, file_manager) -> str:
    """
    Uploads the specified audio file to the AssemblyAI API.

    Args:
        audio_path: Path to the audio file (MP3 format recommended).
        api_key: AssemblyAI API key.
        file_manager: FileManager instance (used for potential temp file cleanup on error).


    Returns:
        The upload URL provided by AssemblyAI.

    Raises:
        FileNotFoundError: If the input audio file does not exist.
        TranscriptionError: If the upload fails due to API errors or network issues.
    """
    audio_path_obj = Path(audio_path)
    if not audio_path_obj.exists():
        raise FileNotFoundError(f"Audio file for upload not found: {audio_path}")

    try:
        logger.info(f"Uploading audio file: {audio_path_obj.name} ({audio_path_obj.stat().st_size / 1024:.2f} KB)")
        headers = {"authorization": api_key}
        upload_endpoint = "https://api.assemblyai.com/v2/upload"

        # Stream the upload
        with open(audio_path_obj, "rb") as f:
            # Use a session for potential connection reuse and better error handling
            with requests.Session() as session:
                response = session.post(
                    upload_endpoint,
                    headers=headers,
                    data=f,
                    timeout=(15, 300) # (connect timeout, read timeout) - allow long read for upload
                )

        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        upload_url = response.json().get("upload_url")

        if not upload_url:
             logger.error(f"Upload response did not contain 'upload_url'. Response: {response.text}")
             raise TranscriptionError("Failed to get upload URL from AssemblyAI response.")

        logger.info(f"Audio uploaded successfully. URL obtained.")
        logger.debug(f"Upload URL: {upload_url}")
        return upload_url

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during audio upload: {e}")
        raise TranscriptionError(f"Network error during audio upload: {e}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error during audio upload: {e.response.status_code} - {e.response.text}")
        raise TranscriptionError(f"HTTP error {e.response.status_code} during audio upload.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during audio upload: {e}")
        raise TranscriptionError(f"Failed to upload audio: {e}")

def get_speaker_config(utterances: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes utterances to determine speaker count and assigns default gender.
    NOTE: AssemblyAI does not provide reliable gender detection. Defaulting to 'male'.
          This could be enhanced with a separate gender detection model if needed.

    Args:
        utterances: List of utterance dictionaries from AssemblyAI.

    Returns:
        A dictionary containing speaker count and speaker info (ID -> gender, order).
    """
    if not utterances:
        return {"speaker_count": 0, "speaker_info": {}}

    speakers = sorted(list(set(u["speaker"] for u in utterances if u.get("speaker")))) # Get unique speaker IDs (A, B, C...)
    speaker_count = len(speakers)
    logger.info(f"Detected {speaker_count} speakers in the transcription.")

    speaker_info = {}
    # Assign default gender and order based on speaker ID (A=1, B=2, etc.)
    for i, speaker_id in enumerate(speakers):
         # Defaulting gender to male as AssemblyAI doesn't provide it reliably.
         # A more advanced implementation could use voice analysis.
        speaker_info[speaker_id] = {"gender": "male", "order": i + 1}
        logger.debug(f"Speaker Config: ID={speaker_id}, Gender=male (default), Order={i+1}")

    return {"speaker_count": speaker_count, "speaker_info": speaker_info}


def transcribe_audio(
    audio_path: str,
    language_code: str,
    api_key: str,
    file_manager, # Pass FileManager instance
    audio_processor, # Pass audio_processor module/functions
    speakers_expected: Optional[int] = None,
    enable_detailed_transcription: bool = False # Option for word timings etc.
) -> List[Utterance]:
    """
    Transcribes the given audio file using the AssemblyAI API.

    Args:
        audio_path: Path to the audio file.
        language_code: Language code for transcription (e.g., "en", "de").
        api_key: AssemblyAI API key.
        file_manager: FileManager instance for managing temporary files.
        audio_processor: Module containing `convert_audio_to_mp3`.
        speakers_expected: Optional hint for the number of speakers.
        enable_detailed_transcription: If True, request word timings and confidence.

    Returns:
        A list of Utterance objects representing the transcription.

    Raises:
        FileNotFoundError: If the input audio file does not exist.
        TranscriptionError: If transcription fails.
        AudioProcessingError: If audio conversion fails.
    """
    audio_path_obj = Path(audio_path)
    if not audio_path_obj.exists():
        raise FileNotFoundError(f"Audio file for transcription not found: {audio_path}")

    upload_audio_path = str(audio_path_obj)
    needs_cleanup = False

    try:
        # --- Convert to MP3 if necessary ---
        # AssemblyAI works best with MP3, although it supports others.
        if audio_path_obj.suffix.lower() != ".mp3":
            logger.info(f"Input audio is not MP3 ({audio_path_obj.suffix}). Converting...")
            try:
                upload_audio_path = audio_processor.convert_audio_to_mp3(str(audio_path_obj), file_manager)
                needs_cleanup = True # Mark the converted file for cleanup
                logger.info(f"Audio converted to MP3 for upload: {upload_audio_path}")
            except Exception as e: # Catch potential AudioProcessingError
                 logger.error(f"Failed to convert audio to MP3: {e}")
                 raise # Re-raise the original error (could be AudioProcessingError)

        # --- Upload Audio ---
        upload_url = upload_audio(upload_audio_path, api_key, file_manager)

        # --- Configure Transcription Job ---
        headers = {
            "authorization": api_key,
            "content-type": "application/json",
        }
        transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
        data = {
            "audio_url": upload_url,
            "language_code": language_code,
            # Add more features as needed
            "punctuate": True,
            "format_text": True, # Formats numbers, etc.
        }

        if speakers_expected is not None and speakers_expected > 0:
            data["speaker_labels"] = True
            # Only provide speakers_expected if > 1, as 1 is implicit
            if speakers_expected > 1:
                 data["speakers_expected"] = speakers_expected
                 logger.info(f"Enabling speaker diarization (expected: {speakers_expected}).")
            else:
                 logger.info("Speaker count hint is 1, speaker_labels enabled without count.")
        else:
            logger.info("Speaker count not specified. Diarization will attempt automatic detection if enabled by default or if >1 speaker found.")
            # Optionally enable speaker_labels anyway for auto-detection
            data["speaker_labels"] = True


        if enable_detailed_transcription:
             data["word_boost"] = [] # Example: Add important keywords if needed
             data["disfluencies"] = True # Capture filler words like "uh", "um"
             # Note: Requesting detailed info increases processing time/cost slightly

        # --- Start Transcription ---
        logger.info("Submitting transcription job to AssemblyAI...")
        logger.debug(f"Transcription request data: {data}")
        try:
            response = requests.post(transcript_endpoint, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            transcript_info = response.json()
            transcript_id = transcript_info.get("id")
            if not transcript_id:
                 logger.error(f"Failed to get transcript ID from response: {transcript_info}")
                 raise TranscriptionError("AssemblyAI did not return a transcript ID.")
            logger.info(f"Transcription job submitted successfully. ID: {transcript_id}")
        except requests.exceptions.RequestException as e:
             logger.error(f"Network error submitting transcription job: {e}")
             raise TranscriptionError(f"Network error submitting transcription job: {e}")
        except requests.exceptions.HTTPError as e:
             logger.error(f"HTTP error submitting transcription job: {e.response.status_code} - {e.response.text}")
             raise TranscriptionError(f"HTTP error {e.response.status_code} submitting job.")

        # --- Poll for Completion ---
        polling_endpoint = f"{transcript_endpoint}/{transcript_id}"
        polling_interval = 5 # Start with 5 seconds
        max_attempts = 720 # Approx 1 hour (720 * 5s = 3600s)
        attempts = 0

        logger.info("Polling for transcription results...")
        while attempts < max_attempts:
            attempts += 1
            try:
                poll_response = requests.get(polling_endpoint, headers=headers, timeout=30)
                poll_response.raise_for_status()
                transcription = poll_response.json()
                status = transcription.get("status")

                logger.debug(f"Polling attempt {attempts}/{max_attempts}: Status = {status}")

                if status == "completed":
                    logger.info("Transcription completed successfully.")
                    # --- Process Results ---
                    if "error" in transcription and transcription["error"]:
                         logger.error(f"Transcription completed with error: {transcription['error']}")
                         raise TranscriptionError(f"Transcription failed: {transcription['error']}")

                    # Check if speaker labels were actually produced
                    has_utterances = "utterances" in transcription and transcription["utterances"]
                    if data.get("speaker_labels") and has_utterances:
                        logger.info("Processing results with speaker diarization.")
                        speaker_config = get_speaker_config(transcription["utterances"])
                        utterances_list = []
                        for utt in transcription["utterances"]:
                            speaker_id = utt.get("speaker", "Unknown") # Handle missing speaker ID
                            speaker_info = speaker_config["speaker_info"].get(speaker_id, {"gender": "male", "order": 99})
                            utterances_list.append(
                                Utterance(
                                    speaker=speaker_id,
                                    text=utt.get("text", ""),
                                    start=utt.get("start", 0),
                                    end=utt.get("end", 0),
                                    confidence=utt.get("confidence", 0.0),
                                    words=utt.get("words", []),
                                    gender=speaker_info["gender"],
                                )
                            )
                        if not utterances_list:
                             logger.warning("Transcription complete but no utterances found in the result.")
                             # Fallback to full text if needed?
                             full_text = transcription.get("text", "")
                             if full_text:
                                  logger.warning("Falling back to single utterance with full text.")
                                  audio_duration_ms = int(transcription.get("audio_duration", 0) * 1000)
                                  return [Utterance("A", full_text, 0, audio_duration_ms, 1.0, [], "male")]
                             else:
                                  return [] # Return empty list if really nothing there
                        return utterances_list
                    else:
                        # No speaker labels or no utterances returned
                        logger.info("Processing results as single speaker.")
                        full_text = transcription.get("text")
                        if not full_text:
                             logger.warning("Transcription complete but no text found.")
                             return []
                        # Estimate duration if available
                        audio_duration_ms = int(transcription.get("audio_duration", 0) * 1000)
                        # Create a single utterance spanning the whole audio
                        return [
                            Utterance(
                                speaker="A", # Default single speaker ID
                                text=full_text,
                                start=0,
                                end=audio_duration_ms,
                                confidence=transcription.get("confidence", 1.0), # Overall confidence if available
                                words=transcription.get("words", []), # Word timings if requested/available
                                gender="male", # Default gender
                            )
                        ]

                elif status == "error":
                    error_msg = transcription.get("error", "Unknown error during transcription.")
                    logger.error(f"Transcription job failed: {error_msg}")
                    raise TranscriptionError(f"Transcription failed: {error_msg}")
                elif status in ["queued", "processing"]:
                    # Wait and poll again
                    time.sleep(polling_interval)
                    # Optional: Implement backoff for polling interval
                    # polling_interval = min(polling_interval * 1.2, 30) # Increase delay up to 30s
                else:
                    logger.warning(f"Unknown transcription status received: {status}")
                    time.sleep(polling_interval) # Wait before retrying

            except requests.exceptions.RequestException as e:
                 logger.warning(f"Network error during polling (attempt {attempts}): {e}. Retrying...")
                 time.sleep(polling_interval * 2) # Longer wait after network error
            except requests.exceptions.HTTPError as e:
                 logger.warning(f"HTTP error during polling (attempt {attempts}): {e.response.status_code}. Retrying...")
                 time.sleep(polling_interval * 2) # Longer wait after HTTP error

        # If loop finishes without completion
        logger.error(f"Transcription job did not complete after {max_attempts} attempts.")
        raise TranscriptionError("Transcription timed out.")

    except Exception as e:
        # Log any unexpected errors during the process
        logger.exception(f"An unexpected error occurred in transcribe_audio: {e}")
        # Re-raise as TranscriptionError for consistent handling
        raise TranscriptionError(f"An unexpected error occurred during transcription: {e}")

    finally:
        # --- Cleanup Converted MP3 ---
        if needs_cleanup and Path(upload_audio_path).exists():
            try:
                Path(upload_audio_path).unlink()
                logger.info(f"Cleaned up temporary MP3 file: {upload_audio_path}")
            except OSError as e:
                logger.warning(f"Could not delete temporary MP3 file {upload_audio_path}: {e}")