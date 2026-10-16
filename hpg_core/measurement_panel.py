"""Schreibgeschützte Diagnoseansicht ausschließlich aus RAM-Snapshots."""
from copy import deepcopy
from dataclasses import dataclass
import math

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QLabel, QPushButton, QTableView,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .measurement_contract import validate_measurement_diagnostics
from .downbeat import DOWNBEAT_RELIABLE_MIN
from .models import bar_position_usage_blocked


_CODES = {
    "native_rekordbox": "Native Rekordbox-Analyse",
    "native_rekordbox_audio_offset": "Native Rekordbox-Analyse mit Audio-Zeitkorrektur",
    "native_adopted": "Nativer Anker übernommen",
    "native_offset_adopted": "Nativer Anker mit bestätigtem Zeitversatz übernommen",
    "unknown": "Unbekannt", "reference_verified": "Referenz bestätigt",
    "reference_candidate": "Referenz-Taktposition ungeprüft",
    "invalidinput": "Ungültige Eingabe", "inputshort": "Eingabe zu kurz",
    "fewbeats": "Zu wenige Beats", "incommensurate": "Beatabstände nicht vereinbar",
    "noactivity": "Keine messbare Aktivität", "weakfold": "Schwache Faltungsbindung",
    "fold_alignment": "Beat-Raster widerspricht Faltungsphase",
    "voteweak": "Schwache Taktabstimmung", "estimationerror": "Schätzung fehlgeschlagen",
    "external_vote_conflict": "Audio-Taktphase weicht vom Modell-Takt ab",
    "ok": "Schätzung abgeschlossen", "nowindows": "Keine Messfenster",
    "duplicategrid": "Doppelte Gitterpunkte", "variablegrid": "Veränderliche Gitterabstände",
    "tempomismatch": "Tempoabweichung", "missingreference": "Referenz fehlt",
    "fewwindows": "Zu wenige geprüfte Fenster", "gridcoverage": "Rekordbox-Grid deckt Messfenster nicht ab",
    "verified": "Verifiziert",
    "phasemismatch": "Phasenabweichung", "measured": "Gemessen",
    "unverifiable": "Nicht verifizierbar", "unsupported": "Nicht unterstützt",
    "mismatch": "Abweichung", "decode_error": "Fenster nicht dekodiert",
    "input": "Eingabeprüfung", "beat_tracking": "Beat-Erkennung",
    "features": "Merkmalberechnung", "trim": "Beschneiden der Beatfolge",
    "voting": "Taktabstimmung", "fold": "Phasenfaltung",
    "result": "Ergebnis", "reference": "Referenzprüfung",
    "reference_preferred": "Rekordbox-Referenz bevorzugt",
    "baseline_preferred": "Audio-Baseline bevorzugt",
    "no_candidates": "Keine Modellkandidaten",
    "insufficient_evidence": "Zu wenig Modellevidenz",
    "bar_conflict": "Modell-Taktphasen widersprechen sich",
    "insufficient_windows": "Zu wenige Modellfenster",
    "final_grid_error": "Abschließende Gridprüfung fehlgeschlagen",
    "final_grid_rejected": "Abschließendes Beatgrid verworfen",
    "adopted": "Modellanker übernommen",
    "bar_rotation_adopted": "Audio-bestätigte Taktrotation übernommen",
    "phase_offset_adopted": "Audio-bestätigter Zeitversatz übernommen",
    "aligned": "Beatphase ausgerichtet",
    "consistent_offset": "Konsistenter Beatphasen-Versatz",
    "variable_phase": "Wechselnde Beatphase",
    "candidate_rotation": "Modellkandidat: andere Taktposition",
    "rotation_disagreement": "Taktpositionskandidaten widersprechen sich",
    "invalid_reference": "Ungültige Rekordbox-Taktfolge",
    "window_count": "Nicht drei getrennte Modellfenster",
    "window_overlap": "Modellfenster überlappen oder sind ungültig",
    "insufficient_matches": "Zu wenige direkte Beat-Treffer",
    "time_mismatch": "Modell-Beats zeitlich nicht direkt zugeordnet",
    "invalid_events": "Ungültige Modell-Beats",
    "unavailable": "Modellfenster nicht verfügbar",
    "audio": "Audio",
    "rekordbox": "Rekordbox",
    "dsp": "Audio-DSP",
    "neural_audio": "Audio-Modell",
    "model_audio_rotation": "Modell-/Audio-Taktkorrektur",
    "model_audio_phase_offset": "Modell-/Audio-Phasenkorrektur",
    "window_unavailable": "Zeitfenster nicht verfügbar",
    "model_unavailable": "Modell nicht verfügbar",
    "ambiguous": "Takt mehrdeutig",
    "tempo_mismatch": "Tempoabweichung",
    "weak_audio": "Audio-Evidenz schwach",
    "confirmed": "Audio lokal bestätigt",
    "audio_error": "Audio-Prüfung fehlgeschlagen",
    "audio_confirmed": "Zusätzliche Audio-Prüfung bestätigt",
    "audio_phase_conflict": "Audio-Taktphase widerspricht Kandidat",
    "not_attempted": "Nicht ausgeführt",
    "no_rotation_candidate": "Keine Rotation zu prüfen",
    "invalid_candidate": "Ungültiger Rotationskandidat",
    "incomplete_model_evidence": "Unvollständige Modellevidenz",
    "final_grid_rejected": "Gesamtgrid verworfen",
    "final_grid_error": "Gesamtgridprüfung fehlgeschlagen",
    "rejected": "Nicht bestätigt",
    "error": "Fehler",
}
_INPUT_STATUS = {
    "ok": "Eingabe verfügbar", "unavailable": "Eingabe nicht verfügbar",
    "missing_model": "Modell fehlt", "unsupported_model": "Modell nicht unterstützt",
    "model_error": "Modellfehler", "service_error": "Dienstfehler",
    "decode_error": "Dekodierung fehlgeschlagen",
}
_UNKNOWN = "Unbekannt – möglicherweise alte Analyse"
_INVALID = "Unverifiziert – ungültige Diagnose"
_HEADERS = ("Track", "Dateipfad (nur RAM)", "Gridstatus", "Geprüfte Fenster", "Max. Phasenfehler (ms)")


def _number(value):
    # Null ist eine Messung; None und der -1-Sentinel sind keine Messung.
    return "Nicht gemessen" if value is None or value == -1 else f"{value:.3f}"


def _code(value):
    return _CODES.get(value, "Unbekannt")


def _anchor_summary(diagnostic, bar_position_status="unknown"):
    """Beschreibt nur die validierte, persistierte Ankerentscheidung."""
    anchor = diagnostic.get("anchor")
    if anchor is None:
        return "Ankerentscheidung: Nicht verfügbar (ältere Diagnose); Rasterfreigabe unbekannt."

    confidence = anchor["confidence"]
    grid_verified = diagnostic["grid"]["status"] == "verified"
    usage_blocked = bar_position_usage_blocked(diagnostic)
    raster_usable = (
        confidence >= DOWNBEAT_RELIABLE_MIN
        and grid_verified
        and not usage_blocked
        and bar_position_status not in {"reference_candidate", "native_candidate"}
        and (anchor["source"] != "rekordbox"
             or bar_position_status == "reference_verified")
    )
    method = _code(anchor["method"])
    confidence_text = _number(confidence)
    neural_reason = _code(anchor["neural"]["reason"])
    reference = anchor.get("reference")
    path_match = reference.get("path_match", "unknown") if isinstance(reference, dict) else "unknown"
    match_text = {
        "exact_path": "exakter Pfad",
        "volume_rebind": "Laufwerkswechsel, Metadatenabgleich",
        "unknown": "Zuordnungsart unbekannt",
    }.get(path_match, "Zuordnungsart unbekannt")
    if anchor["method"] in {"model_audio_rotation", "model_audio_phase_offset"}:
        provenance = (
            "Der aktive Anker wurde nach Bestätigung durch beide Modelle, sechs "
            "disjunkte Audiofenster und das verifizierte Gesamtgrid korrigiert. "
            + (
                "Die Taktposition blieb unverändert; nur der konstante Zeitversatz "
                "wurde korrigiert. "
                if anchor["method"] == "model_audio_phase_offset" else
                "Die Taktposition wurde zusätzlich rotiert. "
            )
            + "Das beweist keine unabhängige musikalische Takt-1-Genauigkeit."
        )
        consequence = (
            "Phrase-/Mixraster: auf dem korrigierten Audioanker technisch freigegeben; "
            "Rekordbox-PSSI und Rekordbox-Render-Sync bleiben gesperrt."
        )
    elif anchor["method"] in {"native_rekordbox", "native_rekordbox_audio_offset"}:
        provenance = (
            "Beatfolge und Taktzahlen stammen aus der nativen Rekordbox-Verarbeitung. "
            + ("Ein separat gemessener Audio-Zeitversatz korrigiert den aktiven Anker; "
               "die native Rohfolge bleibt erhalten. "
               if anchor["method"] == "native_rekordbox_audio_offset" else "")
            + "Konfidenz 1 bezeichnet hier die native Herkunft, keine gemessene musikalische Trefferquote. "
            "Takt 1 ist nicht unabhängig geprüft."
        )
        consequence = (
            "Phrase-/Mixraster: technisch freigegeben; jede Hörprobe benötigt weiterhin die lokale Synchronprüfung."
            if raster_usable else
            "Phrase-/Mixraster: nicht freigegeben; dieser Anker wird dafür nicht verwendet."
        )
    elif anchor["source"] == "rekordbox":
        provenance = (
            "Rekordbox bezeichnet die Herkunft; auch ein verifiziertes Grid ist "
            "keine unabhängige Ground Truth für Takt 1."
        )
        consequence = (
            "Phrase-/Mixraster: vorsorglich wegen einer konsistenten Modell-Taktrotation gesperrt; "
            "Beat-Sync bleibt davon getrennt."
            if usage_blocked else
            "Phrase-/Mixraster: technisch freigegeben; musikalische Takt-1-Genauigkeit "
            "bleibt ungeprüft."
            if raster_usable else
            "Phrase-/Mixraster: nicht freigegeben; dieser Anker wird dafür nicht verwendet."
        )
    else:
        provenance = "Takt 1 ist nicht unabhängig geprüft."
        consequence = (
            "Phrase-/Mixraster: vorsorglich wegen einer konsistenten Modell-Taktrotation gesperrt; "
            "Beat-Sync bleibt davon getrennt."
            if usage_blocked else
            "Phrase-/Mixraster: technisch freigegeben; musikalische Takt-1-Genauigkeit "
            "bleibt ungeprüft."
            if raster_usable else
            "Phrase-/Mixraster: nicht freigegeben; dieser Anker wird dafür nicht verwendet."
        )
    return (
        f"Anker: {_code(anchor['source'])} / {method}; Bar-1-Status: {_code(bar_position_status)}; "
        f"Konfidenz {confidence_text}; "
        f"Resolvergrund: {neural_reason}; Rekordbox-Pfad: {match_text}. "
        f"{provenance} {consequence}"
    )


def _reference_grid_summary(diagnostic):
    """Zeigt den Rekordbox-Referenzversuch getrennt vom aktiven Grid."""
    anchor = diagnostic.get("anchor")
    reference = anchor.get("reference") if isinstance(anchor, dict) else None
    measurement = reference.get("measurement") if isinstance(reference, dict) else None
    grid = measurement.get("grid") if isinstance(measurement, dict) else None
    if not isinstance(grid, dict):
        return "Rekordbox-Referenzversuch: nicht verfügbar."

    status = grid.get("status", "unknown")
    reason = grid.get("reason", "unknown")
    pattern = grid.get("phase_pattern", "unknown")
    center_ms = grid.get("phase_center_ms")
    if status == "verified":
        if (isinstance(anchor, dict)
                and anchor.get("method") in {"model_audio_rotation", "model_audio_phase_offset"}):
            if anchor.get("method") == "model_audio_phase_offset":
                return (
                    "Rekordbox-Referenzgrid bleibt wegen Zeitversatz als Rohreferenz "
                    "verworfen. Der bestätigte Audioanker korrigiert nur die "
                    "Beatphase; Taktposition und Roh-Bar-Labels bleiben unverändert."
                )
            comparison = anchor.get("bar_position_comparison")
            rotation = comparison.get("rotation_beats") if isinstance(comparison, dict) else None
            rotation_text = f"{rotation} Beat" if rotation == 1 else f"{rotation} Beats"
            return (
                "Rekordbox-Referenzgrid ist zeitlich innerhalb der Phasengrenze "
                f"verifiziert; seine Taktposition wurde um {rotation_text} "
                "durch die bestätigte Modell-/Audio-Korrektur ersetzt. Der aktive "
                "Anker bleibt Audioherkunft."
            )
        return "Rekordbox-Referenzgrid: innerhalb der bestehenden Phasengrenze verifiziert."
    if pattern == "consistent_offset" and center_ms is not None:
        comparison = anchor.get("bar_position_comparison") if isinstance(anchor, dict) else None
        confirmation = comparison.get("audio_confirmation") if isinstance(comparison, dict) else None
        if (isinstance(anchor, dict)
                and anchor.get("method") in {"model_audio_rotation", "model_audio_phase_offset"}
                and isinstance(confirmation, dict)
                and confirmation.get("status") == "audio_confirmed"):
            correction = (
                "Der reine Zeitversatz wurde im aktiven HPG-Audioanker korrigiert; "
                "Taktposition und Rekordbox-Rohticks bleiben unverändert."
                if anchor.get("method") == "model_audio_phase_offset" else
                "Eine Taktrotation wurde mit getrennten Audiomodellfenstern bestätigt "
                "und nur im aktiven HPG-Audioanker berücksichtigt; Rekordbox-Rohticks "
                "bleiben unverändert."
            )
            return (
                f"Rekordbox-Referenzgrid wegen konstantem Beatphasenversatz verworfen "
                f"(Audio minus Grid {_number(center_ms)} ms). {correction}"
            )
        return (
            f"Rekordbox-Referenzgrid als Anker verworfen: konsistenter zeitlicher Beatphasenversatz, "
            f"Audio minus Grid {_number(center_ms)} ms; Status {_code(status)} "
            f"({_code(reason)}). Deshalb wurde der Audioanker gewählt; "
            "der Rekordbox-Rohanker bleibt Diagnose."
        )
    if pattern == "variable_phase":
        return (
            f"Rekordbox-Referenzgrid verworfen: wechselnde Beatphase; Status {_code(status)} "
            f"({_code(reason)}). Der aktive Anker ist separat ausgewiesen."
        )
    return (
        f"Rekordbox-Referenzgrid nicht übernommen: Status {_code(status)} "
        f"({_code(reason)}); Phasenmuster {_code(pattern)}."
    )


def _neural_windows_summary(diagnostic):
    """Zeigt begrenzte Fenstermessungen ohne freie Fehlertexte."""
    anchor = diagnostic.get("anchor")
    if anchor is None:
        return "Modellfenster: nicht verfügbar (ältere Diagnose)."
    windows = anchor["neural"]["windows"]
    if not windows:
        return "Modellfenster: keine Fenster protokolliert."
    summaries = []
    for window in windows:
        model_id = window["model_id"]
        model = {"model7": "Beat-Modell 7", "model8": "Beat-Modell 8"}.get(
            model_id, "Modell nicht bekannt"
        )
        audio_reason = window["downbeat"].get("reason")
        audio_text = (f"Audio: {_code(audio_reason)}; " if audio_reason else "")
        summaries.append(
            f"{model}, Start {_number(window['start_s'])} s, "
            f"Dauer {_number(window['duration_s'])} s: {_code(window['reason'])}; "
            f"{audio_text}{_INPUT_STATUS[window['input_status']]}"
        )
    return "Modellfenster: " + " | ".join(summaries)


def _native_grid_summary(diagnostic):
    """Erklärt die native Rasterentscheidung aus der gespeicherten Diagnose."""
    decision = diagnostic.get("native_grid")
    if not isinstance(decision, dict):
        return "Native Rasterentscheidung: nicht verfügbar (ältere Diagnose)."
    status = {
        "accepted": "übernommen",
        "rejected": "verworfen",
        "unavailable": "nicht verfügbar",
        "disabled": "deaktiviert",
    }.get(decision["status"], "unbekannt")
    reason = {
        "verified": "Raster bestand die Audio-Synchronprüfung",
        "audio_offset_confirmed": "Zeitversatz wurde mit separaten Fenstern bestätigt",
        "grid_unverified": "Raster bestand die Audio-Synchronprüfung nicht",
        "variable_grid_unsupported": "variabler Beatabstand wird vom konstanten Renderer-Raster nicht unterstützt",
        "offset_out_of_range": "gemessener Zeitversatz lag außerhalb des zulässigen Bereichs",
        "offset_confirmation_windows_missing": "unabhängige Bestätigungsfenster fehlten",
        "offset_audio_confirmation_failed": "separate Audio-Bestätigung scheiterte",
        "offset_audio_decode_failed": "Audio für die Zeitversatz-Bestätigung war nicht lesbar",
        "native_unavailable": "native Verarbeitung lieferte kein Raster",
        "unsupported_duration": "Trackdauer liegt außerhalb der nativen Grenzen",
        "disabled": "native Verarbeitung ist abgeschaltet",
    }.get(decision["reason"], "Grund unbekannt")
    return f"Native Beatentscheidung: {status}; {reason}."


def _bar_position_summary(diagnostic):
    anchor = diagnostic.get("anchor")
    comparison = anchor.get("bar_position_comparison") if isinstance(anchor, dict) else None
    if not isinstance(comparison, dict):
        return "Taktpositionsvergleich: unbekannt (ältere Diagnose)."
    status = comparison["status"]
    rotation = comparison["rotation_beats"]
    if status == "aligned":
        if comparison.get("reason") == "offset_compensated":
            result = (
                "Modellpositionen stimmen nach Berücksichtigung des gemessenen "
                "Zeitversatzes mit den PQTZ-Taktpositionen überein; das rohe "
                "Rekordbox-Grid bleibt unverändert und unverifiziert."
            )
        else:
            result = "Modellpositionen stimmen mit Rekordbox überein."
    elif status == "candidate_rotation":
        result = (
            f"Modellkandidat: {rotation} Beat(s) gegenüber Rekordbox rotiert. "
            "Vorsorgliche Sperre für PSSI/Phrasenraster, Mixpunkte und Takt-1-Export; "
            "Beat-Sync und Rekordbox-Rohanker bleiben erhalten."
        )
        if comparison.get("reason") == "offset_compensated":
            result += (
                " Der Positionsvergleich berücksichtigt den separat gemessenen "
                "konstanten Zeitversatz; Ankerkorrektur und Audio-Bestätigung "
                "bleiben aus."
            )
    elif status == "conflict":
        result = "Modellpositionen widersprechen sich."
    else:
        result = f"Taktpositionsvergleich unbekannt: {_code(comparison['reason'])}."
    confirmation = comparison["audio_confirmation"]
    if confirmation["status"] == "audio_confirmed":
        if comparison.get("reason") == "offset_compensated":
            audio = (
                " Die drei separaten Bestätigungsfenster je Modell und das "
                "Gesamtgrid bestanden; der aktive Anker verwendet die bestätigte "
                "Audio-Taktposition, die Rekordbox-Rohticks bleiben unverändert."
            )
        else:
            audio = (
                " Zusätzliche DSP-Prüfung in sechs Modellfenstern und Gesamtgridprüfung "
                "bestanden; aktive Rekordbox-Entscheidung bleibt unverändert."
            )
    elif confirmation["status"] in {"rejected", "error"}:
        audio = (
            f" Zusätzliche DSP-Prüfung nicht bestätigt: {_code(confirmation['reason'])}; "
            "aktive Rekordbox-Entscheidung bleibt unverändert."
        )
    else:
        audio = " Keine zusätzliche DSP-Prüfung ausgeführt."
    return result + audio + " Keine unabhängige musikalische Ground Truth."


@dataclass(frozen=True)
class _Snapshot:
    name: str
    path: str
    diagnostic: dict | None
    bar_position_status: str
    phrase_unit: int | None
    phrase_unit_source: str
    phrase_unit_candidate: int | None
    phrase_unit_score: float | None
    phrase_unit_margin: float | None
    tempo_diagnostic: dict | None
    track_bpm: float | None
    rekordbox_bpm: float | None
    deep_summary: str = ""


def _deep_summary(track):
    """Nur gespeicherte Verträge lesen; keine Modelle oder Audiodateien laden."""
    from .ai_models.deep_features import validate as validate_feature
    from .ai_models.native_track_beats import validate_snapshot as validate_beats
    from .ai_models.native_phrase_adapter import validate_snapshot as validate_phrases

    duration = getattr(track, "duration", None)
    parts = []
    statuses = {"disabled": "deaktiviert", "unavailable": "nicht verfügbar",
                "unsupported": "nicht unterstützt", "skipped": "übersprungen"}
    for field, label, kind in (
        ("native_beat_analysis", "Native Beatverarbeitung", "beats"),
        ("native_phrase_analysis", "Native Phrasen", "phrases"),
        ("stem_analysis", "Stem-Merkmale", "stems"),
        ("embedding_analysis", "Klang-Embedding", "embedding"),
    ):
        value = getattr(track, field, {})
        if value == {}:
            parts.append(f"{label}: nicht gespeichert.")
            continue
        try:
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                raise ValueError("Invalid duration")
            if kind == "beats":
                validate_beats(value, duration=duration)
            elif kind == "phrases":
                validate_phrases(value, duration=duration,
                    grid_verified=getattr(track, "beatgrid_status", None) == "verified",
                    usage_blocked=bar_position_usage_blocked(getattr(track, "measurement_diagnostics", {})))
            else:
                validate_feature(value, kind=kind, duration=duration)
            if value["status"] != "ok":
                text = statuses[value["status"]]
            elif kind == "beats":
                text = f"{len(value['grid'])} Beatpunkte; native Taktzahlen, musikalisch ungeprüft"
            elif kind == "phrases":
                text = f"{len(value['phrases'])} Abschnitte; keine kalibrierte Trefferwahrscheinlichkeit"
            elif kind == "stems":
                text = (f"{duration:.1f} s abgedeckt, 1-s-Raster; "
                        f"{value['data']['provider_request']} angefordert, Ausführungsgerät unbestätigt; "
                        "unkalibriert, keine harte Vocal-Sperre")
            else:
                visualization = value["data"].get("visualization")
                projection_status = (
                    visualization["status"] if type(visualization) is dict
                    else "nicht vorhanden"
                )
                energy_model = value["data"].get("danceability")
                if type(energy_model) is dict and energy_model.get("status") == "ok":
                    energy_values = energy_model["values"]
                    energy_text = (
                        f"; Rekordbox-Danceability-Diagnose {sum(energy_values) / len(energy_values):.3f} "
                        "(unkalibriert)"
                    )
                else:
                    energy_text = "; Rekordbox-Danceability-Modell nicht verfügbar"
                text = (f"{duration:.1f} s abgedeckt, {len(value['data']['windows'])} Fenster; "
                        f"normalisiert, UMAP-Projektion {projection_status}; "
                        "Kosinusvergleich nur Diagnose, kein Rangfolgengewicht" + energy_text)
            parts.append(f"{label}: {text}.")
        except (ValueError, TypeError, KeyError, OverflowError):
            # Keine fremden Fehlertexte oder ungeprüften Messwerte ausgeben.
            parts.append(f"{label}: ungültige gespeicherte Diagnose.")
    return " ".join(parts)


def _snapshot(track):
    # Keine Trackreferenz behalten und keine Quelle nachladen.
    name = deepcopy(getattr(track, "fileName", ""))
    path = deepcopy(getattr(track, "filePath", ""))
    bar_position_status = deepcopy(getattr(track, "bar_position_status", "unknown"))
    if bar_position_status not in {
            "reference_verified", "reference_candidate", "native_candidate",
            "audio_estimate", "blocked", "unknown"}:
        bar_position_status = "unknown"
    try:
        diagnostic = deepcopy(getattr(track, "measurement_diagnostics", {}))
        validate_measurement_diagnostics(diagnostic)
    except Exception:
        # Fremde Payloads und Fehlermeldungen niemals anzeigen.
        diagnostic = None
    phrase_unit = deepcopy(getattr(track, "phrase_unit", None))
    if type(phrase_unit) is not int or phrase_unit not in {8, 16, 32}:
        phrase_unit = None
    phrase_unit_source = deepcopy(getattr(track, "phrase_unit_source", ""))
    if (type(phrase_unit_source) is not str
            or phrase_unit_source not in {"genre_prior", "audio_novelty", "configured"}):
        phrase_unit_source = "unknown"
    phrase_unit_candidate = deepcopy(getattr(track, "phrase_unit_candidate", None))
    if type(phrase_unit_candidate) is not int or phrase_unit_candidate not in {8, 16, 32}:
        phrase_unit_candidate = None
    phrase_unit_score = deepcopy(getattr(track, "phrase_unit_score", None))
    if (type(phrase_unit_score) not in (int, float)
            or not math.isfinite(phrase_unit_score)):
        phrase_unit_score = None
    phrase_unit_margin = deepcopy(getattr(track, "phrase_unit_margin", None))
    if (type(phrase_unit_margin) not in (int, float)
            or not math.isfinite(phrase_unit_margin) or phrase_unit_margin < 0.0):
        phrase_unit_margin = None
    phrase_diagnostic = (
        diagnostic.get("phrase_unit")
        if isinstance(diagnostic, dict) and diagnostic.get("version") in {6, 7, 8}
        else None
    )
    if isinstance(phrase_diagnostic, dict):
        phrase_unit = phrase_diagnostic["unit"]
        phrase_unit_source = phrase_diagnostic["source"]
        phrase_unit_candidate = phrase_diagnostic["candidate"]
        phrase_unit_score = phrase_diagnostic["raw_score"]
        phrase_unit_margin = phrase_diagnostic["ranking_margin"]
    tempo_diagnostic = (
        deepcopy(diagnostic.get("tempo"))
        if isinstance(diagnostic, dict) and diagnostic.get("version") in {7, 8}
        else None
    )
    track_bpm = deepcopy(getattr(track, "bpm", None))
    if (type(track_bpm) not in (int, float)
            or not math.isfinite(track_bpm) or track_bpm <= 0.0):
        track_bpm = None
    anchor_diagnostic = diagnostic.get("anchor") if isinstance(diagnostic, dict) else None
    reference_diagnostic = (
        anchor_diagnostic.get("reference")
        if isinstance(anchor_diagnostic, dict) else None
    )
    rekordbox_bpm = (
        deepcopy(reference_diagnostic.get("bpm"))
        if isinstance(reference_diagnostic, dict) else None
    )
    if (type(rekordbox_bpm) not in (int, float)
            or not math.isfinite(rekordbox_bpm) or rekordbox_bpm <= 0.0):
        rekordbox_bpm = None
    return _Snapshot(name if isinstance(name, str) else "",
                     path if isinstance(path, str) else "", diagnostic,
                     bar_position_status, phrase_unit, phrase_unit_source, phrase_unit_candidate,
                     phrase_unit_score, phrase_unit_margin, tempo_diagnostic,
                     track_bpm, rekordbox_bpm, _deep_summary(track))


def _phrase_unit_summary(snapshot):
    labels = {
        "genre_prior": "Genre-Prior",
        "audio_novelty": "Audio-Novelty-Messung",
        "configured": "Vorgegeben",
    }
    if snapshot.phrase_unit is None:
        return "Phrasenlänge: nicht verfügbar."
    source = labels.get(snapshot.phrase_unit_source, "Herkunft unbekannt")
    evidence = ""
    if snapshot.phrase_unit_candidate is not None:
        score = _number(snapshot.phrase_unit_score)
        margin = _number(snapshot.phrase_unit_margin)
        evidence = (
            f" Bester Novelty-Kandidat: {snapshot.phrase_unit_candidate} Takte; "
            f"Rohkorrelation {score}; Ranking-Abstand zum Zweitkandidaten {margin}."
        )
    return f"Phrasenlänge: {snapshot.phrase_unit} Takte ({source}).{evidence}"


def _tempo_summary(snapshot):
    diagnostic = snapshot.tempo_diagnostic
    if not isinstance(diagnostic, dict):
        return "Tempoentscheidung: nicht gespeichert."
    model_bpm = _number(diagnostic.get("model_bpm"))
    refined_bpm = _number(diagnostic.get("refined_bpm"))
    spread_ratio = diagnostic.get("model_spread")
    spread = _number(spread_ratio * 100.0) if (
        type(spread_ratio) in (int, float) and math.isfinite(spread_ratio)
    ) else _number(None)
    def sample_summary(sample):
        bpm_value = sample["bpm"]
        delta_text = ""
        median_value = diagnostic.get("model_bpm")
        if type(median_value) in (int, float) and math.isfinite(median_value):
            delta_text = f" (Delta zum Median: {_number(bpm_value - median_value)} BPM)"
        return (
            f"{_code(sample['model_id'])}@{_number(sample['start_s'])} s="
            f"{_number(bpm_value)} BPM{delta_text}"
        )

    model_samples = diagnostic.get("model_samples", [])
    if model_samples:
        samples = ", ".join(sample_summary(sample) for sample in model_samples)
    elif diagnostic.get("reason") == "reference_verified":
        samples = "nicht zur Tempoentscheidung verwendet: Rekordbox-Referenzgrid verifiziert"
    else:
        samples = "keine gültigen Modellfenster"
    return (
        f"Tempoentscheidung: {_code(diagnostic['status'])} ({_code(diagnostic['reason'])}); "
        f"Rekordbox-Tempo: {_number(snapshot.rekordbox_bpm)} BPM; "
        f"Tracktempo: {_number(snapshot.track_bpm)} BPM; "
        f"Modellmedian: {model_bpm} BPM; Audioverfeinerung: {refined_bpm} BPM; "
        f"Modellstreuung: {spread} %. Fensterwerte: {samples}."
    )


class _TrackModel(QAbstractTableModel):
    def __init__(self, snapshots, parent=None):
        super().__init__(parent)
        self._snapshots = snapshots

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._snapshots)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        record = self._snapshots[index.row()]
        diag = record.diagnostic
        if index.column() < 2:
            return (record.name, record.path)[index.column()]
        if diag is None:
            return _INVALID if index.column() == 2 else "Nicht gemessen"
        if not diag:
            return _UNKNOWN if index.column() == 2 else "Nicht gemessen"
        grid = diag["grid"]
        if role == Qt.ItemDataRole.ToolTipRole:
            downbeat = diag["downbeat"]
            return (f"Taktphase: {_code(downbeat['reason'])} ({downbeat['reason']}), "
                    f"Schritt: {_code(downbeat['stage'])} ({downbeat['stage']}); "
                    f"Beatgrid: {_code(grid['status'])} ({grid['status']}), "
                    f"{_code(grid['reason'])} ({grid['reason']}). "
                    f"{_anchor_summary(diag, record.bar_position_status)} {_reference_grid_summary(diag)} "
                    "Gespeicherte Messdiagnose, keine erneute Prüfung.")
        return (_code(grid["status"]), str(grid["windows_checked"]),
                _number(grid["max_phase_error_ms"]))[index.column() - 2]


class MeasurementDialog(QDialog):
    """Alle übergebenen Tracks anzeigen; Details nur für die aktuelle Auswahl."""
    def __init__(self, tracks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Messdiagnosen")
        self.resize(1000, 650)
        self._snapshots = tuple(_snapshot(track) for track in tracks)
        layout = QVBoxLayout(self)
        self.status_label = QLabel(
            f"{len(self._snapshots)} Tracks – gespeicherte RAM-Diagnosen, nicht frisch geprüft."
            if self._snapshots else "Keine analysierten Tracks übergeben. Keine Messdiagnosen verfügbar.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.track_table = QTableView(self)
        self.track_table.setModel(_TrackModel(self._snapshots, self))
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.setColumnWidth(0, 220)
        self.track_table.setColumnWidth(1, 280)
        self.track_table.setColumnWidth(2, 270)
        layout.addWidget(self.track_table)
        self.detail_label = QLabel("Keine Trackauswahl.")
        self.detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        self.window_table = QTableWidget(0, 7, self)
        self.window_table.setHorizontalHeaderLabels([
            "Offset (s)", "Dauer (s)", "Lokale Phase (s)", "Faltungsbindung (Fold-Lock)",
            "Phasenfehler (ms)", "Signierter Phasenfehler (Audio minus Grid, ms)", "Fenstergrund"])
        self.window_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.window_table)
        self.decode_label = QLabel("Keine Trackauswahl.")
        self.decode_label.setTextFormat(Qt.TextFormat.PlainText)
        self.decode_label.setWordWrap(True)
        layout.addWidget(self.decode_label)
        close = QPushButton("Schließen", self)
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.track_table.selectionModel().selectionChanged.connect(self._show_selection)
        if self._snapshots:
            self.track_table.selectRow(0)

    def _show_selection(self, *_):
        self.window_table.setRowCount(0)
        selected = self.track_table.selectionModel().selectedRows()
        if not selected:
            self.detail_label.setText("Keine Trackauswahl.")
            self.decode_label.setText("Keine Trackauswahl.")
            return
        snapshot = self._snapshots[selected[0].row()]
        diag = snapshot.diagnostic
        if not diag:
            status = _INVALID if diag is None else _UNKNOWN
            self.detail_label.setText(f"{status} {_phrase_unit_summary(snapshot)} {snapshot.deep_summary}")
            self.detail_label.setToolTip(self.detail_label.text())
            self.decode_label.setText("Dekodierdiagnose nicht verfügbar.")
            return
        downbeat, grid = diag["downbeat"], diag["grid"]
        retry_reason = downbeat.get("retry_reason")
        retry_text = (
            f"Retry-Grund: {_code(retry_reason)} ({retry_reason}). "
            if retry_reason else ""
        )
        self.detail_label.setText(
            f"{_phrase_unit_summary(snapshot)} {_tempo_summary(snapshot)} "
            f"Downbeat: {_code(downbeat['reason'])}; Schritt: {_code(downbeat['stage'])}. "
            f"{retry_text}"
            f"Faltungsbindung: {_number(downbeat.get('fold_lock'))}; "
            f"lokale Phase: {_number(downbeat.get('phase_seconds'))} s. "
            f"Grid: {_code(grid['status'])}; {_code(grid['reason'])}; "
            f"maximaler Phasenfehler: {_number(grid['max_phase_error_ms'])} ms; "
            f"Phasenmuster: {_code(grid.get('phase_pattern', 'unknown'))}; "
            f"Zentrum Audio minus Grid: {_number(grid.get('phase_center_ms'))} ms. "
            "Die Audio-Beatphase ist keine unabhängige musikalische Takt-1-Referenz. "
            f"{_anchor_summary(diag, snapshot.bar_position_status)} {_reference_grid_summary(diag)} "
            f"{_native_grid_summary(diag)} {_bar_position_summary(diag)} "
            f"{_neural_windows_summary(diag)} {snapshot.deep_summary}")
        self.detail_label.setToolTip(
            f"Grund {downbeat['reason']}: {_code(downbeat['reason'])}; "
            f"{retry_text}"
            f"Schritt {downbeat['stage']}: {_code(downbeat['stage'])}. "
            "Fold-Lock beschreibt die Faltungsbindung (0 bis 1), nicht die musikalische Qualität.")
        windows = grid["window_diagnostics"]
        self.window_table.setRowCount(len(windows))
        for row, window in enumerate(windows):
            values = [_number(window[key]) for key in (
                "offset_seconds", "duration_seconds", "phase_seconds", "fold_lock", "phase_error_ms")]
            values.append(_number(window.get("signed_phase_error_ms")))
            values.append(_code(window["reason"]))
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(f"{_code(window['reason'])} ({window['reason']}); "
                                "Phase ist fensterlokal. Signiertes Residuum = Audio minus Grid. "
                                "Nicht gemessen ist nicht Null.")
                self.window_table.setItem(row, column, item)
        failures = grid["decode_failures"]
        self.decode_label.setText(
            "Nicht dekodierte Fenster – Offsets: " + ", ".join(
                f"{_number(failure['offset_seconds'])} s" for failure in failures)
            if failures else "Keine gespeicherten Dekodierfehler.")
        self.decode_label.setToolTip("decode_error: Fenster konnte nicht dekodiert werden; keine Fehlertexte gespeichert.")
