# YT Germanizer v0.1

Dieses Projekt übersetzt YouTube-Videos und erstellt eine neue deutsche Tonspur (Dubbing). Es verwendet AssemblyAI für die Transkription der Originalsprache und Coqui XTTS v2 für die Generierung der deutschen Sprachausgabe.

## Features

*   **Modulare Struktur:** Der Code ist in logische Module unterteilt (`src/`).
*   **Interaktive Konfiguration:** Das Hauptskript fragt beim Start nach allen notwendigen Parametern (URL, Sprache, API-Key etc.).
*   **Hochwertige TTS:** Nutzt Coqui XTTS v2 für natürlich klingende deutsche Sprachausgabe mit Voice Cloning über eine Referenz-WAV-Datei.
*   **Automatisierte Einrichtung:** Ein Installationsskript (`src/install.sh`) hilft bei der Erstellung der virtuellen Umgebung und der Installation von Abhängigkeiten.

## Setup

1.  **Voraussetzungen:**
    *   Python 3.10
    *   Git
    *   FFmpeg (muss systemweit installiert und im PATH verfügbar sein)

2.  **Repository klonen (oder dieses Verzeichnis verwenden):**
    ```bash
    # Falls du das Repository geklont hast:
    # git clone <repository_url>
    # cd Germanizer_v0.1
    ```
    Wenn du diesen Ordner bereits hast, navigiere einfach hinein:
    ```bash
    cd Germanizer_v0.1
    ```

3.  **Installation ausführen:**
    Das Installationsskript erstellt eine virtuelle Umgebung (standardmäßig `../germanizer_venv`), installiert die Python-Pakete und konfiguriert den AssemblyAI API-Key.
    ```bash
    # Vom Germanizer_v0.1 Verzeichnis ausführen:
    ./src/install.sh
    ```
    Folge den Anweisungen des Skripts (insbesondere zur Eingabe des AssemblyAI API-Keys, falls dieser nicht als Umgebungsvariable gesetzt ist).

4.  **Virtuelle Umgebung aktivieren:**
    Nachdem das `install.sh`-Skript durchgelaufen ist, musst du die erstellte virtuelle Umgebung aktivieren. Der Name der Umgebung wird vom Skript ausgegeben (z.B. `germanizer_venv`).
    ```bash
    # Vom Germanizer_v0.1 Verzeichnis ausführen:
    source ../<venv_name>/bin/activate
    # Beispiel: source ../germanizer_venv/bin/activate
    ```
    Dein Terminal-Prompt sollte sich ändern und den Namen der Umgebung anzeigen.

## Konfiguration

*   **AssemblyAI API Key:** Das `install.sh`-Skript speichert den Key in `src/.env`. Du kannst ihn dort bei Bedarf manuell ändern.
*   **XTTS Speaker WAV:** Wenn du das `xtts`-Modell verwendest (Standard), benötigt es eine Referenz-Audiodatei (`.wav`, ca. 10-30 Sekunden) für das Voice Cloning.
    *   Das Skript `yt_germanizer_v2.py` fragt interaktiv nach dem Pfad zu dieser Datei.
    *   Alternativ kannst du eine Datei `default_german_voice.wav` im (noch zu erstellenden) `assets`-Verzeichnis innerhalb von `Germanizer_v0.1` platzieren. Das Skript fragt dann, ob diese Standardstimme verwendet werden soll.

## Benutzung

1.  **Virtuelle Umgebung aktivieren** (falls noch nicht geschehen):
    ```bash
    # Vom Germanizer_v0.1 Verzeichnis ausführen:
    source ../<venv_name>/bin/activate
    ```
2.  **Hauptskript ausführen:**
    ```bash
    # Vom Germanizer_v0.1 Verzeichnis ausführen:
    python yt_germanizer_v2.py
    ```
3.  **Interaktiven Anweisungen folgen:** Gib die gefragten Informationen (URL, Sprache etc.) ein.
4.  Die verarbeiteten Dateien werden in `Germanizer_v0.1/processing_files/` gespeichert (temporäre Dateien in `temp/`, das finale Video in `output/`). Logdateien findest du in `Germanizer_v0.1/logs/`.

## Wichtige Abhängigkeiten

*   Python 3.10
*   FFmpeg
*   PyTorch (CPU oder GPU-Version)
*   TTS (Coqui TTS)
*   AssemblyAI SDK (`assemblyai`)
*   MoviePy
*   pydub
*   yt-dlp
*   deep-translator
*   uvm. (siehe `requirements.txt`)