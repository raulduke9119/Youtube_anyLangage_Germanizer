import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger("YTGermanizerV2.FileManager")

class FileManager:
    """
    Manages file operations, temporary files, and output directories for the pipeline.
    """
    def __init__(self, base_dir: str = "processing_files"):
        """
        Initializes the FileManager instance.

        Args:
            base_dir: The base directory for all generated files (default: "processing_files").
                      Will be created if it doesn't exist.
        """
        self.base_dir = Path(base_dir).resolve()
        self.temp_dir = self.base_dir / "temp"
        self.output_dir = self.base_dir / "output"
        self._init_directories()
        logger.info(f"FileManager initialized: base_dir='{self.base_dir}', temp_dir='{self.temp_dir}', output_dir='{self.output_dir}'")

    def _init_directories(self):
        """Initializes the base, temporary, and output directories."""
        try:
            for directory in [self.base_dir, self.temp_dir, self.output_dir]:
                directory.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Ensured directory exists: {directory}")
        except Exception as e:
            logger.exception(f"Critical error initializing directories: {e}")
            raise RuntimeError(f"Could not create required directories under {self.base_dir}") from e

    def _sanitize_filename_part(self, part: str) -> str:
        """Removes or replaces characters unsafe for filenames."""
        # Remove path separators and control characters
        sanitized = re.sub(r'[\\/*?:"<>|\x00-\x1F]', '_', part)
        # Replace multiple underscores/spaces with a single underscore
        sanitized = re.sub(r'[\s_]+', '_', sanitized)
        # Limit length to avoid issues on some filesystems
        return sanitized[:100]

    def get_temp_path(self, prefix: str, suffix: str) -> Path:
        """
        Generates a unique temporary file path within the temp directory.

        Args:
            prefix: A descriptive prefix for the filename.
            suffix: The file extension (e.g., ".wav", ".mp4").

        Returns:
            A Path object representing the unique temporary file path.
        """
        timestamp = int(time.time() * 1000)
        safe_prefix = self._sanitize_filename_part(prefix)
        # Ensure suffix starts with a dot
        safe_suffix = suffix if suffix.startswith('.') else f".{suffix}"
        safe_suffix = "".join(c if c.isalnum() or c == '.' else '_' for c in safe_suffix) # Basic suffix sanitize

        filename = f"{safe_prefix}_{timestamp}{safe_suffix}"
        path = self.temp_dir / filename
        # Parent directory should exist from init, but double-check is cheap
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Generated temp path: {path}")
        return path

    def get_output_path(self, prefix: str, suffix: str) -> Path:
        """
        Generates a unique output file path within the output directory.

        Args:
            prefix: A descriptive prefix for the filename.
            suffix: The file extension (e.g., ".wav", ".mp4").

        Returns:
            A Path object representing the unique output file path.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") # Use readable timestamp
        safe_prefix = self._sanitize_filename_part(prefix)
        safe_suffix = suffix if suffix.startswith('.') else f".{suffix}"
        safe_suffix = "".join(c if c.isalnum() or c == '.' else '_' for c in safe_suffix)

        filename = f"{safe_prefix}_{timestamp}{safe_suffix}"
        path = self.output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Generated output path: {path}")
        return path

    def cleanup_temp_files(self):
        """Removes all files and subdirectories within the temporary directory."""
        logger.info(f"Cleaning up temporary directory: {self.temp_dir}")
        if not self.temp_dir.exists():
            logger.warning(f"Temporary directory {self.temp_dir} does not exist, skipping cleanup.")
            return
        try:
            for item in self.temp_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        logger.debug(f"Deleted temp file: {item}")
                    elif item.is_dir():
                        shutil.rmtree(item)
                        logger.debug(f"Deleted temp directory: {item}")
                except Exception as e:
                    # Log error but continue cleanup if possible
                    logger.warning(f"Could not delete temp item {item}: {e}")
            logger.info("Temporary directory cleanup finished.")
        except Exception as e:
            # Log error if iterating the directory fails
            logger.error(f"Error during temp file cleanup process: {e}")

    def cleanup_old_outputs(self, max_files_to_keep: int = 10):
        """Removes the oldest output files, keeping only the specified number."""
        if max_files_to_keep <= 0:
             logger.info("max_files_to_keep is non-positive, skipping old output cleanup.")
             return

        logger.info(f"Cleaning up old output files in: {self.output_dir} (keeping max {max_files_to_keep})")
        if not self.output_dir.exists():
            logger.warning(f"Output directory {self.output_dir} does not exist, skipping cleanup.")
            return
        try:
            # Get only files, ignore directories
            files = [f for f in self.output_dir.glob('*') if f.is_file()]
            # Sort by modification time, oldest first
            files.sort(key=lambda x: x.stat().st_mtime)

            files_to_delete_count = len(files) - max_files_to_keep
            if files_to_delete_count > 0:
                logger.info(f"Found {len(files)} output files, deleting {files_to_delete_count} oldest...")
                for i in range(files_to_delete_count):
                    file_path = files[i]
                    try:
                        logger.debug(f"Deleting old output file: {file_path}")
                        file_path.unlink()
                    except Exception as e:
                         logger.warning(f"Could not delete old output file {file_path}: {e}")
                logger.info(f"Kept the latest {max_files_to_keep} output files.")
            else:
                 logger.info(f"Found {len(files)} output files, no cleanup needed based on max_files_to_keep={max_files_to_keep}.")
        except Exception as e:
            logger.error(f"Error during old output cleanup: {e}")

# Add imports used within the class methods that were missing at the top level
import re
from datetime import datetime