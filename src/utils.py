import logging
import shutil
import subprocess
from pathlib import Path
import sys # Import sys for sys.exit
from typing import Optional, List # Add missing imports

logger = logging.getLogger("YTGermanizerV2.Utils") # Use a specific logger

# Logger setup function
def setup_logging(level=logging.INFO, log_file_name="yt_germanizer_v2.log"):
    """
    Configures the root logger for the application.

    Args:
        level: The logging level (e.g., logging.INFO, logging.DEBUG).
        log_file_name: The name for the log file.

    Returns:
        The configured logger instance.
    """
    # Use the root logger for the application to ensure consistency
    logger = logging.getLogger("YTGermanizerV2")
    # Prevent duplicate handlers if called multiple times
    if logger.hasHandlers():
        # Check if handlers are already configured to avoid redundant setup
        # This simple check might not be perfect but prevents basic duplication
        if any(isinstance(h, logging.StreamHandler) for h in logger.handlers) and \
           any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            logger.debug("Logger already seems configured. Skipping setup.")
            return logger
        logger.handlers.clear()

    logger.propagate = False # Don't pass logs to the root logger
    logger.setLevel(logging.DEBUG) # Set logger to lowest level to allow handlers to filter

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout) # Explicitly use stdout
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", # Simpler format for console
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level) # Console shows messages at specified level or higher
    logger.addHandler(console_handler)

    # File Handler (DEBUG level to capture everything)
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file_path = log_dir / log_file_name
        file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)-8s - %(name)-25s - %(funcName)-20s - %(message)s", # More detailed format
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG) # Log everything to the file
        logger.addHandler(file_handler)
        logger.info(f"Logging initialized. Console Level: {logging.getLevelName(level)}. Log file: {log_file_path}")
    except Exception as e:
        logger.error(f"Failed to initialize file logging: {e}", exc_info=False)

    # Capture warnings issued by other libraries
    logging.captureWarnings(True)
    warnings_logger = logging.getLogger("py.warnings")
    if not warnings_logger.handlers: # Avoid adding handlers multiple times
         warnings_logger.addHandler(console_handler)
         warnings_logger.addHandler(file_handler)
    warnings_logger.setLevel(logging.WARNING)

    # Silence overly verbose loggers from dependencies
    verbose_loggers = ["httpx", "httpcore", "yt_dlp", "TTS", "numba", "pydub.converter", "urllib3"]
    for logger_name in verbose_loggers:
        dep_logger = logging.getLogger(logger_name)
        if dep_logger.level < logging.WARNING:
             dep_logger.setLevel(logging.WARNING)

    return logger

# FFmpeg check function
def check_ffmpeg():
    """
    Checks if ffmpeg is installed and accessible in the system's PATH.

    Raises:
        EnvironmentError: If ffmpeg is not found or seems non-functional.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        error_msg = "FFmpeg not found. Please install FFmpeg and ensure it's in your system's PATH."
        logger.error(error_msg)
        raise EnvironmentError(error_msg)
    else:
        try:
            result = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, check=True, timeout=5)
            version_line = result.stdout.splitlines()[0] if result.stdout else "N/A"
            logger.info(f"FFmpeg found at '{ffmpeg_path}': {version_line}")
        except subprocess.TimeoutExpired:
             logger.error("ffmpeg -version command timed out. FFmpeg might be unresponsive.")
             raise EnvironmentError("FFmpeg found but timed out. Check FFmpeg installation.")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
             logger.error(f"FFmpeg check failed when running '{ffmpeg_path} -version': {e}")
             logger.error(f"Stderr: {getattr(e, 'stderr', 'N/A')}")
             raise EnvironmentError("FFmpeg found but failed execution check. Check FFmpeg installation and permissions.")
        except Exception as e:
             logger.exception(f"An unexpected error occurred during FFmpeg check: {e}")
             raise EnvironmentError(f"Unexpected error during FFmpeg check: {e}")

# --- Interactive Input Functions ---

def ask_user_input(prompt: str, default: Optional[str] = None) -> str:
    """Asks the user for input with an optional default value."""
    prompt_text = f"{prompt}"
    if default:
        prompt_text += f" [{default}]"
    prompt_text += ": "
    while True:
        user_input = input(prompt_text).strip()
        if user_input:
            return user_input
        elif default is not None:
            return default
        else:
            print("Input cannot be empty. Please try again.")


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    """Asks a yes/no question."""
    options = "(Y/n)" if default_yes else "(y/N)"
    prompt_text = f"{prompt} {options}: "
    while True:
        user_input = input(prompt_text).strip().lower()
        if not user_input:
            return default_yes
        if user_input in ['y', 'yes']:
            return True
        if user_input in ['n', 'no']:
            return False
        print("Invalid input. Please enter 'y' or 'n'.")

def ask_choice(prompt: str, choices: List[str], default_choice: Optional[str] = None) -> str:
    """Asks the user to choose from a list of options."""
    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        print(f"{i}. {choice}")

    default_index = -1
    if default_choice and default_choice in choices:
        default_index = choices.index(default_choice) + 1

    prompt_text = "Enter your choice number"
    if default_index > 0:
        prompt_text += f" [{default_index}]"
    prompt_text += ": "

    while True:
        user_input = input(prompt_text).strip()
        if not user_input and default_index > 0:
            return choices[default_index - 1]
        try:
            choice_index = int(user_input)
            if 1 <= choice_index <= len(choices):
                return choices[choice_index - 1]
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(choices)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def ask_file_path(prompt: str, must_exist: bool = True, is_dir: bool = False, default: Optional[str] = None) -> Optional[str]:
    """Asks the user for a file or directory path with validation."""
    prompt_text = f"{prompt}"
    if default:
        prompt_text += f" [{default}]"
    prompt_text += ": "

    while True:
        user_input = input(prompt_text).strip()
        path_str = user_input if user_input else default

        if not path_str:
             if not must_exist: # Allow empty if not required
                  return None
             else:
                  print("Path cannot be empty.")
                  continue # Re-prompt if required and empty

        path_obj = Path(path_str).expanduser().resolve() # Expand ~ and get absolute path

        if must_exist:
            if not path_obj.exists():
                print(f"Error: Path does not exist: {path_obj}")
                if default and path_str == default: # Prevent infinite loop if default is bad
                     default = None # Clear default if it's invalid
                     prompt_text = f"{prompt}: " # Update prompt text
                continue
            if is_dir and not path_obj.is_dir():
                print(f"Error: Path is not a directory: {path_obj}")
                continue
            if not is_dir and not path_obj.is_file():
                print(f"Error: Path is not a file: {path_obj}")
                continue

        # Basic check for WAV extension if asking for a file (can be refined)
        if not is_dir and path_obj.suffix.lower() != '.wav':
             if ask_yes_no(f"Warning: File '{path_obj.name}' does not have a .wav extension. Continue anyway?", default_yes=False):
                  return str(path_obj)
             else:
                  continue # Re-prompt

        return str(path_obj)

# Add imports used within the class methods that were missing at the top level
import re
from datetime import datetime
from typing import Optional, List # Add Optional and List