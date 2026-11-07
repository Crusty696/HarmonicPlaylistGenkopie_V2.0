"""Reiner Plan-zu-Render-Vertrag, unabhängig von Audio-I/O und DSP."""
import math
import numbers
from dataclasses import dataclass
from .config import MAX_TRANSITION_OVERLAP_SECONDS
from .downbeat import DOWNBEAT_RELIABLE_MIN

FILTER_RIDE_HP_HZ = 800.0    # Hochpass-Sweep beim Ausblenden (filter_ride)


SMOOTH_BLEND_LP_HZ = 300.0   # Tiefpass auf Track A (smooth_blend)


BREAKDOWN_HP_HZ = 250.0      # Bass-Kill auf Track A (breakdown_bridge)


PRO_EQ_HIGH_HZ = 2500.0     # Grenze zwischen Mitten und Hoehen


SUPPORTED_TRANSITION_TYPES = frozenset({
    "smooth_blend",
    "bass_swap",
    "pro_eq_swap",
    "breakdown_bridge",
    "drop_cut",
    "filter_ride",
    "halftime_switch",
    "echo_out",
    "cold_cut",
})


@dataclass
class EqCrossfadeConfig:
    """Parameter fuer den EQ-Crossfade."""
    cf_frames: int
    sr: int
    bass_cutoff_hz: float
    transition_type: str
    bpm_a: float = 120.0  # AUDIT-FIX R-04: fuer beat-synchrone echo_out-Delays
    bass_swap_fraction: float | None = None


@dataclass
class TransitionClipSpec:
    """Parameter fuer einen Transition-Preview-Clip."""
    track_a_path: str            # Voller Dateipfad zu Track A
    track_b_path: str            # Voller Dateipfad zu Track B
    mix_out_sec: float           # Position in Track A, wo Crossfade beginnt
    mix_in_sec: float            # Position in Track B, wo Crossfade beginnt
    crossfade_sec: float         # Laenge des Crossfade-Bereichs (Sekunden)
    transition_type: str = "smooth_blend"  # bass_swap / smooth_blend / filter_ride / ...
    pre_roll_sec: float = 30.0   # Sekunden von Track A VOR dem Crossfade
    post_roll_sec: float = 30.0  # Sekunden von Track B NACH dem Crossfade
    bass_cutoff_hz: float = 200.0
    target_sr: int = 44100
    bpm_a: float = 120.0         # BPM von Track A (fuer Time-Stretching)
    bpm_b: float = 120.0         # BPM von Track B (fuer Time-Stretching)
    # Plan-Vertrag: BPM B / BPM A. None bleibt nur fuer direkte, planlose
    # Aufrufer zulaessig; from_plan uebergibt immer den geplanten Wert.
    tempo_ratio: float | None = None
    # Downbeat-Feature 2026-07-17: bekannte erste Downbeats (Sekunden) beider
    # Tracks — ermoeglicht exaktes Beat-Alignment ohne Laufzeit-Schaetzung.
    # 0.0 ist ein LEGITIMER Anker (Track startet auf der "1").
    #
    # AUDIT-FIX D-03 (2026-08-14): ZWEI getrennte Verlaesslichkeits-Stufen,
    # weil die Eigenschaetzung genau eine der beiden Groessen belastbar liefert.
    #   downbeat_reliable_*  — die BEAT-Phase stimmt (Flam-Kriterium).
    #       Gilt ab downbeat_confidence >= DOWNBEAT_RELIABLE_MIN. Gemessen an
    #       35 ANLZ-Referenzen: Sub-Beat-Fehler Median 16 ms, Max 43 ms,
    #       also unter der hoerbaren Grenze von 1/8 Beat (54 ms).
    #   bar_phase_reliable_* — zusaetzlich stimmt die TAKT-Phase (welcher
    #       Beat ist die "1"). Das leistet nur das Rekordbox-ANLZ-Beatgrid
    #       (Konfidenz exakt 1.0); das eigene 4-Bin-Voting lag bei 9 von 19
    #       Schaetzungen um ganze Beats daneben, ohne dass die Konfidenz das
    #       getrennt haette (bester Fehlgriff: 0.87 bei 1 Beat Versatz).
    # Folge: mit Eigenschaetzung wird auf BEAT-Ebene aligned (Kick auf Kick),
    # auf TAKT-Ebene nur mit beidseitigem Referenz-Beatgrid.
    first_downbeat_a: float = 0.0
    first_downbeat_b: float = 0.0
    downbeat_reliable_a: bool = False
    downbeat_reliable_b: bool = False
    bar_phase_reliable_a: bool = False
    bar_phase_reliable_b: bool = False
    phase_method_a: str = 'bass_fold'
    phase_method_b: str = 'bass_fold'
    beatgrid_status_a: str = "unknown"
    beatgrid_status_b: str = "unknown"
    analysis_mode_a: str = "unknown"
    analysis_mode_b: str = "unknown"
    strict_beat_sync: bool = False
    # Lautheits-Normalisierung (Research 2026-02-28: verhindert Lautheitssprunge)
    normalize_rms: bool = True          # RMS-Normalisierung vor Crossfade
    normalize_target_db: float = -14.0  # Ziel-Pegel in dBRMS (EBU R128: -14 LUFS)
    use_compressor: bool = False        # Optionaler pedalboard Compressor (experimentell)
    # AUDIT-FIX R-07 (2026-07-26): echte gemessene Track-LUFS (pyloudnorm,
    # BS.1770) aus der Analyse — praeziser als der ungewichtete RMS-Messwert
    # des Renderers. 0.0 = nicht gemessen (Sentinel) -> RMS-Fallback.
    lufs_a: float = 0.0
    lufs_b: float = 0.0
    # Optionaler Stem-Kandidat aus TransitionPlan; fehlend = Mittelpunkt.
    bass_swap_fraction: float | None = None

    @classmethod
    def from_plan(cls, plan, from_track, to_track):
        """Erzeugt eine Render-Spezifikation ohne zweite Timing-Berechnung."""
        def usable_downbeat(track) -> float | None:
            anchor = getattr(track, "first_downbeat", None)
            duration = getattr(track, "duration", None)
            if (isinstance(anchor, bool) or not isinstance(anchor, numbers.Real)
                    or isinstance(duration, bool) or not isinstance(duration, numbers.Real)):
                return None
            anchor, duration = float(anchor), float(duration)
            if not math.isfinite(anchor) or not math.isfinite(duration) or duration <= 0.0:
                return None
            return anchor if 0.0 <= anchor < duration else None

        def _phase_reliability(track) -> tuple[bool, bool]:
            confidence = float(getattr(track, "downbeat_confidence", 0.0) or 0.0)
            source = getattr(track, "beatgrid_source", "unknown")
            status = getattr(track, "beatgrid_status", "unknown")
            has_anchor = usable_downbeat(track) is not None
            reference_grid = (
                source == "rekordbox"
                and status == "verified"
                and has_anchor
            )
            # Native Rekordbox-Taktzahlen kommen aus dem separaten Analyselauf,
            # nicht aus dem Datenbankimport. Herkunft und ggf. Audio-Zeitkorrektur
            # vollständig prüfen, bevor dieselben Taktzahlen zum Renderer gehen.
            from .ai_models.native_track_beats import has_verified_grid
            native_grid = has_verified_grid(track)
            # Beatgrid-Herkunft und Bar-1-Status bleiben getrennt: ein
            # technisch bestaetigtes Rekordbox-Grid erlaubt Beat-Sync; Takt-1
            # nutzt die ausdrücklich freigegebene native Position oder reference_verified.
            # Auch model_audio_rotation bleibt Audioherkunft: Sie kann den
            # Beatanker fuer Beat-Alignment liefern, belegt aber keine
            # unabhaengige musikalische Takt-1 und setzt bar_phase nicht frei.
            # Ein Diagnose-Mismatch sperrt diese Audio-Beatphase nicht: die
            # Messkonfidenz qualifiziert den Anker; der strikte Renderpfad
            # misst und korrigiert die Kicklage anschliessend erneut.
            measured_audio = (
                source == "audio"
                and confidence >= DOWNBEAT_RELIABLE_MIN
                and has_anchor
            )
            return (
                reference_grid or native_grid or measured_audio,
                (native_grid or (reference_grid
                 and getattr(track, "reference_bar_position_verified", False)))
                and not getattr(track, "bar_position_usage_blocked", False),
            )

        downbeat_a, bar_a = _phase_reliability(from_track)
        downbeat_b, bar_b = _phase_reliability(to_track)
        def phase_method(track):
            from .ai_models.native_track_beats import has_verified_grid
            return (track.native_beat_analysis.get('phase_method', 'bass_fold')
                    if has_verified_grid(track) else 'bass_fold')
        # Ein Plan-Render ist strikt beat-synchron. Fehlende/Null-BPM duerfen
        # deshalb nicht still als 120 BPM behandelt werden: das wuerde einen
        # plausibel aussehenden, aber auf einem erfundenen Raster ausgerichteten
        # Preview erzeugen.
        raw_bpm_a = getattr(from_track, "bpm", None)
        raw_bpm_b = getattr(to_track, "bpm", None)
        if (isinstance(raw_bpm_a, bool) or not isinstance(raw_bpm_a, numbers.Real)
                or isinstance(raw_bpm_b, bool) or not isinstance(raw_bpm_b, numbers.Real)):
            raise ValueError("TransitionPlan braucht numerische BPM fuer beide Tracks")
        try:
            bpm_a = float(raw_bpm_a)
            bpm_b = float(raw_bpm_b)
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("TransitionPlan braucht gueltige BPM fuer beide Tracks") from exc
        if (not math.isfinite(bpm_a) or bpm_a <= 0.0
                or not math.isfinite(bpm_b) or bpm_b <= 0.0):
            raise ValueError("TransitionPlan braucht endliche positive BPM fuer beide Tracks")
        tempo_ratio = getattr(plan, "tempo_ratio", bpm_b / bpm_a)
        if tempo_ratio is None:
            raise ValueError("TransitionPlan.tempo_ratio darf nicht None sein")
        spec = cls(
            track_a_path=from_track.filePath,
            track_b_path=to_track.filePath,
            mix_out_sec=plan.mix_out_a,
            mix_in_sec=plan.mix_in_b,
            crossfade_sec=plan.overlap,
            transition_type=plan.transition_type,
            target_sr=plan.target_sr,
            bpm_a=bpm_a,
            bpm_b=bpm_b,
            tempo_ratio=tempo_ratio,
            bass_swap_fraction=getattr(plan, "bass_swap_fraction", None),
            first_downbeat_a=usable_downbeat(from_track) or 0.0,
            first_downbeat_b=usable_downbeat(to_track) or 0.0,
            downbeat_reliable_a=downbeat_a,
            downbeat_reliable_b=downbeat_b,
            bar_phase_reliable_a=bar_a,
            bar_phase_reliable_b=bar_b,
            phase_method_a=phase_method(from_track),
            phase_method_b=phase_method(to_track),
            beatgrid_status_a=getattr(from_track, "beatgrid_status", "unknown"),
            beatgrid_status_b=getattr(to_track, "beatgrid_status", "unknown"),
            analysis_mode_a=getattr(from_track, "analysis_mode", "unknown"),
            analysis_mode_b=getattr(to_track, "analysis_mode", "unknown"),
            strict_beat_sync=True,
            lufs_a=float(getattr(from_track, "lufs", 0.0) or 0.0),
            lufs_b=float(getattr(to_track, "lufs", 0.0) or 0.0),
        )
        validate_transition_clip_spec(spec)
        return spec


def validate_transition_clip_spec(spec: TransitionClipSpec) -> None:
    """Validiert den Rendervertrag, ohne Timingwerte still zu veraendern."""
    for name in ("mix_out_sec", "mix_in_sec"):
        value = getattr(spec, name)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError(f"{name} muss eine endliche nichtnegative Zahl sein")
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} muss eine endliche nichtnegative Zahl sein"
            ) from exc
        if not math.isfinite(numeric) or numeric < 0.0:
            raise ValueError(f"{name} muss eine endliche nichtnegative Zahl sein")

    overlap = spec.crossfade_sec
    if isinstance(overlap, bool) or not isinstance(overlap, numbers.Real):
        raise ValueError("crossfade_sec muss endlich und positiv sein")
    try:
        overlap = float(overlap)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("crossfade_sec muss endlich und positiv sein") from exc
    if (
        not math.isfinite(overlap)
        or not 0.0 < overlap <= MAX_TRANSITION_OVERLAP_SECONDS
    ):
        raise ValueError(
            "crossfade_sec muss groesser 0 und hoechstens "
            f"{MAX_TRANSITION_OVERLAP_SECONDS:g} Sekunden sein"
        )

    if (
        isinstance(spec.target_sr, bool)
        or not isinstance(spec.target_sr, int)
        or spec.target_sr <= 0
    ):
        raise ValueError("target_sr muss eine positive ganze Zahl sein")
    if spec.transition_type not in SUPPORTED_TRANSITION_TYPES:
        raise ValueError(
            f"Nicht unterstuetzter transition_type: {spec.transition_type!r}"
        )

    # Diese Uebergangspfade verwenden feste Filtergrenzen. Eine positive,
    # aber zu niedrige Ziel-Samplerate liess scipy erst waehrend des Renderns
    # mit einer schwer zuzuordnenden Nyquist-Fehlermeldung abbrechen.
    fixed_filter_hz = {
        "smooth_blend": SMOOTH_BLEND_LP_HZ,
        "filter_ride": FILTER_RIDE_HP_HZ,
        "breakdown_bridge": BREAKDOWN_HP_HZ,
        "pro_eq_swap": PRO_EQ_HIGH_HZ,
    }.get(spec.transition_type)
    if fixed_filter_hz is not None and fixed_filter_hz >= spec.target_sr / 2.0:
        raise ValueError(
            f"target_sr muss fuer {spec.transition_type} groesser als "
            f"{fixed_filter_hz * 2:g} Hz sein"
        )

    for name in ("pre_roll_sec", "post_roll_sec"):
        value = getattr(spec, name)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError(f"{name} muss eine endliche nichtnegative Zahl sein")
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} muss eine endliche nichtnegative Zahl sein"
            ) from exc
        if not math.isfinite(numeric) or numeric < 0.0:
            raise ValueError(f"{name} muss eine endliche nichtnegative Zahl sein")

    for name in ("bpm_a", "bpm_b"):
        value = getattr(spec, name)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError(f"{name} muss eine endliche positive Zahl sein")
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{name} muss eine endliche positive Zahl sein") from exc
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"{name} muss eine endliche positive Zahl sein")

    if spec.tempo_ratio is not None:
        if (isinstance(spec.tempo_ratio, bool)
                or not isinstance(spec.tempo_ratio, numbers.Real)):
            raise ValueError("tempo_ratio muss eine endliche positive Zahl sein")
        try:
            tempo_ratio = float(spec.tempo_ratio)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("tempo_ratio muss eine endliche positive Zahl sein") from exc
        if not math.isfinite(tempo_ratio) or tempo_ratio <= 0.0:
            raise ValueError("tempo_ratio muss eine endliche positive Zahl sein")
        expected_ratio = float(spec.bpm_b) / float(spec.bpm_a)
        if not math.isclose(tempo_ratio, expected_ratio, rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError(
                "tempo_ratio widerspricht den BPM-Werten des Rendervertrags"
            )

    if spec.bass_swap_fraction is not None:
        value = spec.bass_swap_fraction
        if (isinstance(value, bool) or not isinstance(value, numbers.Real)
                or not math.isfinite(float(value)) or not 0.0 < float(value) < 1.0):
            raise ValueError("bass_swap_fraction muss innerhalb der Blende liegen")
        if spec.transition_type not in {"bass_swap", "pro_eq_swap"}:
            raise ValueError("bass_swap_fraction erfordert bass_swap oder pro_eq_swap")

    cutoff = spec.bass_cutoff_hz
    if isinstance(cutoff, bool) or not isinstance(cutoff, numbers.Real):
        raise ValueError("bass_cutoff_hz muss endlich und innerhalb Nyquist liegen")
    try:
        cutoff = float(cutoff)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(
            "bass_cutoff_hz muss endlich und innerhalb Nyquist liegen"
        ) from exc
    if (not math.isfinite(cutoff) or cutoff <= 0.0
            or cutoff >= spec.target_sr / 2.0):
        raise ValueError("bass_cutoff_hz muss endlich und innerhalb Nyquist liegen")
    if spec.transition_type == "pro_eq_swap" and cutoff >= PRO_EQ_HIGH_HZ:
        raise ValueError("bass_cutoff_hz muss unter der Mitten-/Hoehengrenze liegen")

    for name in ("first_downbeat_a", "first_downbeat_b", "normalize_target_db",
                 "lufs_a", "lufs_b"):
        value = getattr(spec, name)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError(f"{name} muss eine endliche Zahl sein")
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{name} muss eine endliche Zahl sein") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"{name} muss eine endliche Zahl sein")

    for name in ("downbeat_reliable_a", "downbeat_reliable_b",
                 "bar_phase_reliable_a", "bar_phase_reliable_b",
                 "strict_beat_sync", "normalize_rms", "use_compressor"):
        if type(getattr(spec, name)) is not bool:
            raise ValueError(f"{name} muss boolesch sein")
