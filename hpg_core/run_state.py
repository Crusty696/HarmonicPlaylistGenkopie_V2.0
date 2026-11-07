"""Qt-freie Zustände und Meldungen eines Anwendungslaufs."""
from enum import Enum
from typing import NamedTuple


class RunState(str, Enum):
    """Einzige Wahrheit fuer den Lebenszyklus eines Analyse-Laufs."""

    IDLE = "idle"
    AUDIO = "audio"
    AI = "ai"
    PLAYLIST = "playlist"
    PREVIEW = "preview"
    CANCELLING = "cancelling"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    CANCELLED = "cancelled"


class AnalysisIssue(NamedTuple):
    """Unveraenderlicher, thread-sicherer Befund eines Analyse-Laufs."""

    code: str
    path: str
    message: str


class LegacyReorderRequest(NamedTuple):
    playlist: tuple
    quality_metrics: dict
    transition_recommendations: tuple
    bpm_tolerance: float
    scoring_context: dict


def map_phase_progress(percent: float, start: float, end: float) -> int:
    """Mappt lokale 0..100-Prozente monoton in einen globalen Abschnitt."""
    bounded = max(0.0, min(100.0, float(percent)))
    return int(round(start + (end - start) * bounded / 100.0))


ACTIVE_RUN_STATES = {
    RunState.AUDIO,
    RunState.AI,
    RunState.PLAYLIST,
    RunState.PREVIEW,
    RunState.CANCELLING,
}


RUN_STATE_GUIDANCE = {
    RunState.IDLE: "Bibliothek auswählen · Analyse starten",
    RunState.AUDIO: "Analyse läuft · Messungen werden ermittelt",
    RunState.AI: "Beschreibungen werden ergänzt",
    RunState.PLAYLIST: "Playlist und Übergänge werden bewertet",
    RunState.PREVIEW: "Übergangsvorschau wird vorbereitet",
    RunState.CANCELLING: "Abbruch läuft · Ressourcen werden freigegeben",
    RunState.SUCCESS: "Ergebnis bereit · Übergänge prüfen und exportieren",
    RunState.PARTIAL: "Teilergebnis · Hinweise und ungeplante Übergänge prüfen",
    RunState.ERROR: "Fehler · Meldung prüfen und erneut starten",
    RunState.CANCELLED: "Abgebrochen · Einstellungen prüfen und erneut starten",
}
