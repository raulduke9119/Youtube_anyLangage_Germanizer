#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- YT Germanizer Installation Script (inside src) ---"

# --- Configuration ---
BASE_VENV_NAME="germanizer_venv"
PYTHON_VERSION="python3.10"
# Get the directory where this script is located (src)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
# Project directory is one level up from src
PROJECT_DIR=$(dirname "${SCRIPT_DIR}")
ENV_FILE=".env" # .env file inside src directory
ENV_FILE_PATH="${SCRIPT_DIR}/${ENV_FILE}"

# --- Check for Python 3.10 ---
echo "Checking for ${PYTHON_VERSION}..."
if ! command -v ${PYTHON_VERSION} &> /dev/null
then
    echo "Error: ${PYTHON_VERSION} could not be found."
    echo "Please install Python 3.10 and ensure it's in your PATH."
    exit 1
fi
echo "${PYTHON_VERSION} found: $(command -v ${PYTHON_VERSION})"

# --- Find available venv name (in the parent directory) ---
VENV_DIR_PATH="${PROJECT_DIR}/${BASE_VENV_NAME}"
COUNTER=0
while [ -d "${VENV_DIR_PATH}" ]; do
    echo "Directory '${VENV_DIR_PATH}' already exists."
    COUNTER=$((COUNTER + 1))
    VENV_DIR_PATH="${PROJECT_DIR}/${BASE_VENV_NAME}${COUNTER}"
done
VENV_NAME=$(basename "${VENV_DIR_PATH}") # Get just the directory name for messages
echo "Creating virtual environment named '${VENV_NAME}' in '${PROJECT_DIR}'..."

# --- Create Virtual Environment ---
${PYTHON_VERSION} -m venv "${VENV_DIR_PATH}"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment '${VENV_DIR_PATH}'."
    exit 1
fi

# --- Activate Virtual Environment ---
# Note: Activation only lasts for the duration of this script execution.
echo "Activating virtual environment..."
source "${VENV_DIR_PATH}/bin/activate"

# --- Upgrade Pip ---
echo "Upgrading pip..."
pip install --upgrade pip
if [ $? -ne 0 ]; then
    echo "Error: Failed to upgrade pip."
    deactivate || true
    exit 1
fi

# --- Install Dependencies ---
echo "Installing Python dependencies..."
echo "Note: Installing PyTorch and TTS. This might take a while."
# List of dependencies provided by the user
pip install \
    TTS \
    moviepy \
    assemblyai \
    torchaudio \
    requests \
    transformers \
    torch \
    scipy \
    librosa \
    soundfile \
    pydub \
    git+https://github.com/suno-ai/bark.git \
    opencv-python \
    yt-dlp \
    deep-translator \
    python-dotenv \
    numpy
if [ $? -ne 0 ]; then
    echo "Error: Failed to install Python dependencies."
    deactivate || true
    exit 1
fi
echo "Dependencies installed successfully."

# --- Check/Set AssemblyAI API Key ---
echo "Checking for AssemblyAI API Key..."
API_KEY_SET=false
# Check environment variable first
if [ -n "${ASSEMBLYAI_API_KEY}" ]; then
    echo "ASSEMBLYAI_API_KEY environment variable is already set."
    API_KEY_VALUE=$ASSEMBLYAI_API_KEY
    API_KEY_SET=true
else
    echo "ASSEMBLYAI_API_KEY environment variable is not set."
    # Check .env file inside src directory
    if [ -f "${ENV_FILE_PATH}" ]; then
        echo "Checking ${ENV_FILE_PATH} file..."
        API_KEY_VALUE=$(grep -E "^\\s*ASSEMBLYAI_API_KEY\\s*=" "${ENV_FILE_PATH}" | cut -d '=' -f 2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [ -n "${API_KEY_VALUE}" ]; then
            echo "Found API Key in ${ENV_FILE_PATH}."
            API_KEY_SET=true
        else
            echo "${ENV_FILE_PATH} found, but ASSEMBLYAI_API_KEY is missing or empty."
        fi
    else
        echo "${ENV_FILE_PATH} file not found."
    fi
fi

# If key is still not set, prompt the user
if [ "$API_KEY_SET" = false ]; then
    echo "Please enter your AssemblyAI API Key:"
    read -p "API Key: " USER_API_KEY
    while [ -z "${USER_API_KEY}" ]; do
        echo "API Key cannot be empty. Please try again."
        read -p "API Key: " USER_API_KEY
    done
    API_KEY_VALUE=$USER_API_KEY

    # Save to .env file inside src directory
    echo "Saving API Key to ${ENV_FILE_PATH}..."
    if [ -f "${ENV_FILE_PATH}" ] && grep -q -E "^\\s*ASSEMBLYAI_API_KEY\\s*=" "${ENV_FILE_PATH}"; then
        echo "Updating existing key in ${ENV_FILE_PATH}."
        sed -i.bak "s|^\\s*ASSEMBLYAI_API_KEY\\s*=.*|ASSEMBLYAI_API_KEY=${API_KEY_VALUE}|" "${ENV_FILE_PATH}"
        rm -f "${ENV_FILE_PATH}.bak"
    else
        echo "Adding key to ${ENV_FILE_PATH}."
        # Ensure newline before adding if file exists but key doesn't
        [ -f "${ENV_FILE_PATH}" ] && echo "" >> "${ENV_FILE_PATH}"
        echo "ASSEMBLYAI_API_KEY=${API_KEY_VALUE}" >> "${ENV_FILE_PATH}"
    fi
    echo "API Key saved."
fi

# Export the key for the current session (optional but helpful for immediate testing)
echo "Exporting ASSEMBLYAI_API_KEY for the current session..."
export ASSEMBLYAI_API_KEY="${API_KEY_VALUE}"

# --- Completion Message ---
echo ""
echo "--- Installation Complete! ---"
echo ""
echo "Virtual environment '${VENV_NAME}' created in '${PROJECT_DIR}' and dependencies installed."
echo "AssemblyAI API Key is configured in '${ENV_FILE_PATH}'."
echo ""
echo "To activate the virtual environment in your terminal (from the project root directory '${PROJECT_DIR}'), run:"
echo "source ${VENV_NAME}/bin/activate"
echo ""
echo "You can then run the application (from the project root directory) using:"
echo "python yt_germanizer_v2.py"
echo ""

# Deactivate the environment activated by the script
deactivate || true

exit 0