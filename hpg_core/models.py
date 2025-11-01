from dataclasses import dataclass

@dataclass
class Track:
    # Core Info
    filePath: str
    fileName: str

    # ID3 Tag Info
    artist: str = "Unknown"
    title: str = "Unknown"
    genre: str = "Unknown"

    # Analysis Info
    duration: float = 0.0
    bpm: float = 0.0
    keyNote: str = ""
    keyMode: str = ""
    camelotCode: str = ""
    energy: int = 0
    bass_intensity: int = 0

    # Structural Info
    mix_in_point: float = 0.0
    mix_out_point: float = 0.0

    # Mix Points in Bars (für DJ-Anzeige)
    mix_in_bars: int = 0
    mix_out_bars: int = 0
