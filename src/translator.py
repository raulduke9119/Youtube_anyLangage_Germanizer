import logging
import re
from deep_translator import GoogleTranslator
from typing import List

logger = logging.getLogger("YTGermanizerV2.Translator")

class TranslationError(Exception):
    """Custom exception for translation errors."""
    pass

def chunk_text(text: str, max_length: int = 4500) -> List[str]:
    """
    Splits text into chunks suitable for translation APIs, respecting sentence boundaries.

    Args:
        text: The input text string.
        max_length: The approximate maximum character length for each chunk.

    Returns:
        A list of text chunks.
    """
    if not text:
        return []

    # Use regex to split by sentences (handles various punctuation)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Check if adding the next sentence exceeds the max length
        if len(current_chunk) + len(sentence) + 1 > max_length:
            # If the current chunk is not empty, add it to the list
            if current_chunk:
                chunks.append(current_chunk)
            # Start a new chunk with the current sentence
            # If a single sentence is longer than max_length, it becomes its own chunk (API might handle it)
            if len(sentence) > max_length:
                 logger.warning(f"Single sentence exceeds max_length ({max_length} chars): '{sentence[:100]}...'")
                 chunks.append(sentence)
                 current_chunk = "" # Reset chunk as this long sentence is handled
            else:
                 current_chunk = sentence
        else:
            # Add the sentence to the current chunk
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    # Add the last remaining chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    logger.debug(f"Text split into {len(chunks)} chunks for translation.")
    return chunks


def translate_text(text: str, target_lang: str = "de", source_lang: str = "auto") -> str:
    """
    Translates the given text to the target language using GoogleTranslator.

    Args:
        text: The input text to translate.
        target_lang: The target language code (e.g., "de").
        source_lang: The source language code ("auto" for detection).

    Returns:
        The translated text.

    Raises:
        TranslationError: If the translation process fails.
    """
    if not text:
        logger.warning("translate_text called with empty input.")
        return ""

    try:
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        text_chunks = chunk_text(text) # Split text into manageable chunks

        if not text_chunks:
             logger.warning("Text chunking resulted in no chunks.")
             return ""

        logger.info(f"Translating {len(text_chunks)} chunks from '{source_lang}' to '{target_lang}'...")

        translated_chunks = []
        for i, chunk in enumerate(text_chunks, 1):
            logger.debug(f"Translating chunk {i}/{len(text_chunks)} ({len(chunk)} chars)...")
            try:
                translated = translator.translate(chunk)
                if translated is None: # Check for None response
                     logger.warning(f"Translation for chunk {i} returned None. Original: '{chunk[:50]}...'")
                     # Optionally, keep the original chunk or skip it
                     # translated_chunks.append(f"[Translation Failed: {chunk[:50]}...]")
                     continue # Skip this chunk
                translated_chunks.append(translated)
                # Optional: Add a small delay between chunks if hitting rate limits
                # time.sleep(0.1)
            except Exception as chunk_error:
                 logger.error(f"Error translating chunk {i}: {chunk_error}. Original: '{chunk[:50]}...'")
                 # Optionally, add a placeholder or skip the chunk
                 # translated_chunks.append(f"[Translation Error: {chunk[:50]}...]")
                 continue # Skip chunk on error

        if not translated_chunks:
             raise TranslationError("Translation resulted in no translated content after processing chunks.")

        full_translated_text = " ".join(translated_chunks).strip()
        logger.info("Translation completed successfully.")
        logger.debug(f"Translated text preview: {full_translated_text[:100]}...")
        return full_translated_text

    except Exception as e:
        logger.exception(f"Translation failed: {e}")
        raise TranslationError(f"Translation failed: {e}")