# Harmonic Playlist Generator (HPG) v3.0

HPG is a desktop application for DJs that simplifies the process of creating harmonically and rhythmically coherent playlists. The app analyzes a user-provided collection of audio files, extracts key musical features, and generates an optimally sorted playlist.

## Features

*   **Audio Import:** Load a folder of audio files via drag-and-drop or a file dialog.
*   **Enhanced Audio Analysis:** Automatically extracts:
    *   BPM (Beats Per Minute)
    *   Key (Tonart) and Camelot Code
    *   ID3 Tags: Artist, Title, Genre (using `mutagen`)
    *   Song Duration
    *   RMS Energy
    *   Bass Intensity
    *   Mix-In and Mix-Out Points for seamless transitions
*   **Advanced Playlist Generation:** Generates playlists based on various strategies:
    *   **Harmonic Flow:** Prioritizes harmonically compatible tracks (using the Camelot wheel system).
    *   **Warm-Up:** Sorts tracks by ascending BPM.
    *   **Cool-Down:** Sorts tracks by descending BPM.
    *   (Future strategies like Peak-Time, Energy Wave, Consistent can be added)
*   **Dynamic BPM Tolerance:** Adjust the BPM tolerance to control how strictly BPMs are matched between tracks.
*   **Caching System:** Analyzed track data is cached in an SQLite database (`hpg_cache_v3.db`) to speed up subsequent analyses.
*   **Playlist Export:** The generated track order can be exported as a standard `.m3u` playlist file.

## How to Install

1.  **Prerequisites:** Ensure you have Python 3.9+ installed.

2.  **Clone the repository (or download the source code):**
    ```bash
    git clone <repository_url>
    cd HarmonicPlaylistGenerator_v5
    ```

3.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    ```

4.  **Activate the virtual environment:**
    *   On Windows:
        ```bash
        .\venv\Scripts\activate
        ```
    *   On macOS/Linux:
        ```bash
        source venv/bin/activate
        ```

5.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## How to Use

1.  **Run the application:**
    ```bash
    python main.py
    ```

2.  **Select Music:** Drag and drop your music folder onto the application window, or click the "Select Music Folder" button.

3.  **Choose Strategy & Tolerance:** Select your desired playlist generation strategy (e.g., "Harmonic Flow", "Warm-Up", "Cool-Down") and adjust the BPM tolerance using the provided controls.

4.  **Analysis:** The application will automatically analyze all found audio files. A progress bar will show the current status and any analysis errors.

5.  **Review Results:** Once the analysis is complete, a sorted playlist will be displayed in a table with detailed track information.

6.  **Export:** Click the "Export as .m3u Playlist" button to save your new playlist. Any export errors will be reported.

## Technology Stack

*   **Language:** Python 3.9+
*   **UI Framework:** PyQt6
*   **Core Libraries:**
    *   `librosa` for advanced audio analysis
    *   `numpy` for numerical operations
    *   `mutagen` for ID3 tag extraction
*   **Caching:** `sqlite3`