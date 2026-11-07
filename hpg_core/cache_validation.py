"""Reine Validierung persistierter Trackdaten ohne SQLite-Zugriffe."""
import math
import sys
from dataclasses import fields
from .downbeat import DOWNBEAT_RELIABLE_MIN, EXACT_BEAT_SYNC_TOLERANCE_SECONDS, REFERENCE_BEATGRID_CONFIDENCE
from .mix_candidates import MixCandidate, SCHEMA_PRIORITAET
from .models import BEATGRID_SOURCES, BEATGRID_STATUSES, Track, is_supported_phrase_unit
from .config import MIX_POINT_UNSET

TRACK_REQUIRED_FIELDS = frozenset({
    "filePath", "fileName", "artist", "title", "genre", "duration", "bpm",
    "keyNote", "keyMode", "camelotCode", "energy", "bass_intensity",
    "stem_analysis", "embedding_analysis",
    "avg_bass", "avg_mids", "avg_highs", "mix_in_point", "mix_out_point",
    "first_downbeat", "downbeat_confidence", "bar_position_status", "beatgrid_source",
    "beatgrid_status", "beatgrid_windows_checked",
    "beatgrid_max_phase_error_ms", "measurement_diagnostics", "neural_analysis", "native_phrase_analysis", "native_beat_analysis", "first_phrase", "phrase_confidence",
    "key_confidence", "lufs", "mix_in_bars", "mix_out_bars",
    "detected_genre", "genre_confidence", "genre_source", "sections",
    "phrase_unit", "phrase_unit_source", "phrase_unit_candidate",
    "phrase_unit_score", "phrase_unit_margin", "brightness", "vocal_instrumental", "danceability",
    "spectral_flatness", "percussive_ratio", "mfcc_fingerprint",
    "timbre_fingerprint", "groove_pattern", "bass_pattern", "syncopation",
    "sub_energy", "bass_punch", "ai_metadata", "rekordbox_signature",
    "analysis_mode", "analysis_coverage", "outro_covered", "lufs_status",
    "lufs_coverage_seconds", "lufs_channels", "lufs_sample_rate", "phrases",
    "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates",
})
VALID_ANALYSIS_MODES = frozenset({"rekordbox_fast_tail", "librosa_full_or_tail"})
TRACK_LIST_FIELDS = {
    "sections", "mfcc_fingerprint", "timbre_fingerprint", "analysis_coverage",
    "groove_pattern", "bass_pattern",
    "phrases", "cue_points", "phrase_grid", "mix_in_candidates", "mix_out_candidates",
}
TRACK_DICT_FIELDS = {"ai_metadata", "measurement_diagnostics", "neural_analysis", "native_phrase_analysis", "native_beat_analysis",
                     "stem_analysis", "embedding_analysis"}
TRACK_CONFIDENCE_FIELDS = {
    "downbeat_confidence", "phrase_confidence", "key_confidence",
    "genre_confidence",
}
TRACK_STRING_FIELDS = {
    field.name for field in fields(Track) if isinstance(field.default, str)
}
TRACK_BOOL_FIELDS = {
    field.name for field in fields(Track) if isinstance(field.default, bool)
}
TRACK_NUMERIC_FIELDS = {
    field.name
    for field in fields(Track)
    if isinstance(field.default, (int, float))
    and not isinstance(field.default, bool)
}


class CacheValidationError(ValueError):
    """Ein einzelner Cache-Record verletzt den Track-Datenvertrag."""


def _validate_finite_values(value, path: str) -> None:
    """Verhindert nicht-endliche Zahlen auch in verschachtelten JSON-Feldern."""
    if isinstance(value, float) and not math.isfinite(value):
        raise CacheValidationError(f"{path} ist nicht endlich")
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite_values(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_finite_values(nested, f"{path}[{index}]")


MIX_CANDIDATE_FIELDS = {field.name for field in fields(MixCandidate)}
MIX_CANDIDATE_STRING_FIELDS = {
    "section_label", "phrase_label", "camelot_lokal", "energy_trend",
}
MIX_CANDIDATE_UNIT_INTERVAL_FIELDS = {
    "neuheit", "syncopation_lokal", "percussive_ratio_lokal", "sub_energy",
    "key_confidence_lokal", "flatness_lokal",
}
MIX_CANDIDATE_FINITE_FIELDS = {"bass_rms_dbfs", "lufs_lokal"}
MIX_CANDIDATE_PERCENT_FIELDS = {"avg_mids_lokal", "avg_highs_lokal"}
MIX_CANDIDATE_INT_PERCENT_FIELDS = {"brightness_lokal", "energy_lokal"}
MIX_CANDIDATE_BOOL_FIELDS = {"traegt_allein", "kick_aktiv", "vocal_aktiv_lokal"}


def _is_finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _validate_optional_number(value, path: str, minimum=None, maximum=None) -> None:
    if value is None:
        return
    if not _is_finite_number(value):
        raise CacheValidationError(f"{path} muss eine endliche reelle Zahl oder None sein")
    if minimum is not None and value < minimum:
        raise CacheValidationError(f"{path} liegt unter {minimum}")
    if maximum is not None and value > maximum:
        raise CacheValidationError(f"{path} liegt ueber {maximum}")


def _require_dict_fields(value, path: str, required_fields: set[str]) -> dict:
    if not isinstance(value, dict):
        raise CacheValidationError(f"{path} muss ein Dictionary sein")
    missing = sorted(required_fields.difference(value))
    if missing:
        raise CacheValidationError(f"{path}.{missing[0]} fehlt")
    return value


def _validate_time(value, path: str, duration: float) -> float:
    if not _is_finite_number(value) or value < 0.0:
        raise CacheValidationError(f"{path} muss eine endliche nichtnegative Zahl sein")
    if value > duration:
        raise CacheValidationError(f"{path} liegt hinter dem Trackende")
    return float(value)


def _validate_json_scalar_or_none(value, path: str) -> None:
    if value is None or isinstance(value, (str, bool)) or _is_finite_number(value):
        return
    raise CacheValidationError(f"{path} muss ein JSON-Skalar oder None sein")


def _validate_sections(sections: list, duration: float) -> None:
    required = {"label", "start_time", "end_time", "start_bar", "end_bar", "avg_energy"}
    previous_start = None
    previous_end = None
    for index, section in enumerate(sections):
        path = f"sections[{index}]"
        section = _require_dict_fields(section, path, required)
        if not isinstance(section["label"], str):
            raise CacheValidationError(f"{path}.label muss ein String sein")
        start = _validate_time(section["start_time"], f"{path}.start_time", duration)
        end = _validate_time(section["end_time"], f"{path}.end_time", duration)
        if end < start:
            raise CacheValidationError(f"{path}.end_time liegt vor start_time")
        if (
            previous_start is not None
            and start < previous_start - VALIDATION_TIME_TOLERANCE
        ):
            raise CacheValidationError("sections muss nach start_time sortiert sein")
        if (
            previous_end is not None
            and start < previous_end - VALIDATION_TIME_TOLERANCE
        ):
            raise CacheValidationError("sections darf nicht ueberlappen")
        for field_name in ("start_bar", "end_bar"):
            value = section[field_name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CacheValidationError(f"{path}.{field_name} muss ein nichtnegativer Integer sein")
        if section["end_bar"] < section["start_bar"]:
            raise CacheValidationError(f"{path}.end_bar liegt vor start_bar")
        if (
            not _is_finite_number(section["avg_energy"])
            or not 0.0 <= section["avg_energy"] <= 100.0
        ):
            raise CacheValidationError(f"{path}.avg_energy muss in 0..100 liegen")
        _validate_finite_values(section, path)
        previous_start = start
        previous_end = end


VALIDATION_TIME_TOLERANCE = 1e-6
ANALYSIS_COVERAGE_GAP_TOLERANCE = 1.0


def _validate_analysis_coverage(coverage: list, duration: float) -> list[tuple[float, float]]:
    required = {"start", "end"}
    windows = []
    previous_start = None
    previous_end = None
    for index, window in enumerate(coverage):
        path = f"analysis_coverage[{index}]"
        window = _require_dict_fields(window, path, required)
        start = _validate_time(window["start"], f"{path}.start", duration)
        end = _validate_time(window["end"], f"{path}.end", duration)
        if end < start:
            raise CacheValidationError(f"{path}.end liegt vor start")
        if end == start:
            raise CacheValidationError(f"{path}.end muss groesser als start sein")
        if previous_start is not None and start < previous_start:
            raise CacheValidationError("analysis_coverage muss nach start sortiert sein")
        if previous_end is not None and start < previous_end - VALIDATION_TIME_TOLERANCE:
            raise CacheValidationError("analysis_coverage darf nicht ueberlappen")
        _validate_finite_values(window, path)
        windows.append((start, end))
        previous_start = start
        previous_end = end
    return windows


def _validate_phrases(phrases: list, duration: float) -> list[tuple[float, float]]:
    required = {"start_s", "end_s", "label", "mood", "kind", "fill"}
    intervals = []
    for index, phrase in enumerate(phrases):
        path = f"phrases[{index}]"
        phrase = _require_dict_fields(phrase, path, required)
        start = _validate_time(phrase["start_s"], f"{path}.start_s", duration)
        end = _validate_time(phrase["end_s"], f"{path}.end_s", duration)
        if end < start:
            raise CacheValidationError(f"{path}.end_s liegt vor start_s")
        if not isinstance(phrase["label"], str):
            raise CacheValidationError(f"{path}.label muss ein String sein")
        for field_name in ("mood", "kind", "fill"):
            value = phrase[field_name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise CacheValidationError(f"{path}.{field_name} muss ein Integer sein")
        _validate_finite_values(phrase, path)
        intervals.append((start, end))
    for index in range(1, len(intervals)):
        previous_end = intervals[index - 1][1]
        start = intervals[index][0]
        if abs(start - previous_end) > VALIDATION_TIME_TOLERANCE:
            raise CacheValidationError(
                f"phrases[{index}].start_s muss dem vorherigen end_s entsprechen"
            )
    return intervals


def _validate_cue_points(cue_points: list, duration: float) -> None:
    required = {"t", "name", "provenance"}
    for index, cue in enumerate(cue_points):
        path = f"cue_points[{index}]"
        cue = _require_dict_fields(cue, path, required)
        _validate_time(cue["t"], f"{path}.t", duration)
        if not isinstance(cue["name"], str):
            raise CacheValidationError(f"{path}.name muss ein String sein")
        if (
            not isinstance(cue["provenance"], str)
            or cue["provenance"] not in {"manual", "auto", "leer"}
        ):
            raise CacheValidationError(f"{path}.provenance ist ungueltig")
        for field_name in ("typ", "hot_cue"):
            if field_name in cue:
                _validate_json_scalar_or_none(cue[field_name], f"{path}.{field_name}")
        _validate_finite_values(cue, path)


def _validate_phrase_grid(phrase_grid: list, duration: float) -> None:
    previous = None
    for index, value in enumerate(phrase_grid):
        point = _validate_time(value, f"phrase_grid[{index}]", duration)
        if previous is not None and point <= previous:
            raise CacheValidationError("phrase_grid muss streng aufsteigend sein")
        previous = point


def _validate_coverage_sections(
    coverage: list[tuple[float, float]],
    sections: list,
    duration: float,
) -> None:
    unanalysed = sorted(
        (
            (float(section["start_time"]), float(section["end_time"]))
            for section in sections
            if section["label"] == "unanalysed"
        ),
        key=lambda interval: interval[0],
    )
    if not coverage and not unanalysed:
        return

    gaps = []
    cursor = 0.0
    for start, end in coverage:
        if start > cursor + ANALYSIS_COVERAGE_GAP_TOLERANCE:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor + ANALYSIS_COVERAGE_GAP_TOLERANCE:
        gaps.append((cursor, duration))

    if len(gaps) != len(unanalysed) or any(
        abs(gap_start - section_start) > VALIDATION_TIME_TOLERANCE
        or abs(gap_end - section_end) > VALIDATION_TIME_TOLERANCE
        for (gap_start, gap_end), (section_start, section_end)
        in zip(gaps, unanalysed)
    ):
        raise CacheValidationError(
            "analysis_coverage ist nicht konsistent mit unanalysed-Sections"
        )


def _validate_phrases_and_grid(
    phrases: list[tuple[float, float]],
    phrase_grid: list,
) -> None:
    expected = [start for start, _ in phrases]
    if phrases:
        expected.append(phrases[-1][1])
    if len(expected) != len(phrase_grid) or any(
        abs(expected_value - float(actual_value)) > VALIDATION_TIME_TOLERANCE
        for expected_value, actual_value in zip(expected, phrase_grid)
    ):
        raise CacheValidationError("phrases und phrase_grid sind inkonsistent")


def _validate_candidate_pattern(value, path: str, *, length: int, unit_interval: bool) -> None:
    if not isinstance(value, list) or len(value) not in {0, length}:
        raise CacheValidationError(f"{path} muss eine Liste der Laenge 0 oder {length} sein")
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _is_finite_number(item):
            raise CacheValidationError(f"{item_path} muss eine endliche reelle Zahl sein")
        if unit_interval and not 0.0 <= item <= 1.0:
            raise CacheValidationError(f"{item_path} liegt ausserhalb 0..1")


def _validate_candidate_mood(value, path: str) -> None:
    if not isinstance(value, dict):
        raise CacheValidationError(f"{path} muss ein Dictionary sein")
    if "brightness" in value:
        _validate_optional_number(value["brightness"], f"{path}.brightness", 0.0, 100.0)
    if "flatness" in value:
        _validate_optional_number(value["flatness"], f"{path}.flatness", 0.0, 1.0)
    if "key_mode" in value and not isinstance(value["key_mode"], str):
        raise CacheValidationError(f"{path}.key_mode muss ein String sein")
    if "pssi_mood" in value:
        _validate_optional_number(value["pssi_mood"], f"{path}.pssi_mood")


def _validate_mix_candidate(candidate, path: str, duration: float) -> dict:
    if not isinstance(candidate, dict):
        raise CacheValidationError(f"{path} muss ein Dictionary sein")
    missing = MIX_CANDIDATE_FIELDS.difference(candidate)
    if missing:
        field_name = sorted(missing)[0]
        raise CacheValidationError(f"{path}.{field_name} fehlt")

    t = candidate["t"]
    if not _is_finite_number(t) or t < 0.0:
        raise CacheValidationError(f"{path}.t muss eine endliche nichtnegative reelle Zahl sein")
    if duration > 0.0 and t > duration:
        raise CacheValidationError(f"{path}.t liegt hinter dem Trackende")

    schema = candidate["schema"]
    if (
        not isinstance(schema, list)
        or not schema
        or any(not isinstance(item, str) or item not in SCHEMA_PRIORITAET for item in schema)
    ):
        raise CacheValidationError(f"{path}.schema ist ungueltig")
    if not isinstance(candidate["provenance"], str) or not candidate["provenance"]:
        raise CacheValidationError(f"{path}.provenance muss ein nichtleerer String sein")
    _validate_optional_number(candidate["confidence"], f"{path}.confidence", 0.0, 1.0)
    if candidate["confidence"] is None:
        raise CacheValidationError(f"{path}.confidence darf nicht None sein")

    for field_name in MIX_CANDIDATE_STRING_FIELDS:
        if not isinstance(candidate[field_name], str):
            raise CacheValidationError(f"{path}.{field_name} muss ein String sein")
    if candidate["energy_trend"] not in {"", "rising", "falling", "stable"}:
        raise CacheValidationError(f"{path}.energy_trend ist ungueltig")

    _validate_candidate_pattern(
        candidate["groove_pattern_lokal"], f"{path}.groove_pattern_lokal",
        length=16, unit_interval=True,
    )
    _validate_candidate_pattern(
        candidate["bass_pattern_lokal"], f"{path}.bass_pattern_lokal",
        length=16, unit_interval=True,
    )
    _validate_candidate_pattern(
        candidate["timbre_fingerprint_lokal"], f"{path}.timbre_fingerprint_lokal",
        length=13, unit_interval=False,
    )

    for field_name in MIX_CANDIDATE_UNIT_INTERVAL_FIELDS:
        _validate_optional_number(candidate[field_name], f"{path}.{field_name}", 0.0, 1.0)
    _validate_optional_number(candidate["bass_punch"], f"{path}.bass_punch", 0.0)
    for field_name in MIX_CANDIDATE_PERCENT_FIELDS:
        _validate_optional_number(candidate[field_name], f"{path}.{field_name}", 0.0, 100.0)
    for field_name in MIX_CANDIDATE_FINITE_FIELDS:
        _validate_optional_number(candidate[field_name], f"{path}.{field_name}")

    for field_name in MIX_CANDIDATE_INT_PERCENT_FIELDS:
        value = candidate[field_name]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100
        ):
            raise CacheValidationError(f"{path}.{field_name} muss ein Integer 0..100 oder None sein")
    for field_name in MIX_CANDIDATE_BOOL_FIELDS:
        value = candidate[field_name]
        if value is not None and not isinstance(value, bool):
            raise CacheValidationError(f"{path}.{field_name} muss ein Boolean oder None sein")
    _validate_candidate_mood(candidate["mood"], f"{path}.mood")
    return {field_name: candidate[field_name] for field_name in MIX_CANDIDATE_FIELDS}


def _validate_mix_candidate_lists(filtered: dict, duration: float) -> None:
    for list_name in ("mix_in_candidates", "mix_out_candidates"):
        filtered[list_name] = [
            _validate_mix_candidate(
                candidate,
                f"{list_name}[{index}]",
                duration,
            )
            for index, candidate in enumerate(filtered.get(list_name, []))
        ]


def _require_real_in_range(
    filtered: dict, name: str, minimum: float, maximum: float, *,
    minimum_exclusive: bool = False, maximum_exclusive: bool = False,
) -> float:
    value = filtered[name]
    if not _is_finite_number(value):
        raise CacheValidationError(f"{name} muss eine endliche reelle Zahl sein")
    if (value <= minimum if minimum_exclusive else value < minimum):
        raise CacheValidationError(f"{name} liegt ausserhalb des gueltigen Bereichs")
    if (value >= maximum if maximum_exclusive else value > maximum):
        raise CacheValidationError(f"{name} liegt ausserhalb des gueltigen Bereichs")
    return float(value)


def _require_int_in_range(filtered: dict, name: str, minimum: int, maximum: int) -> int:
    value = filtered[name]
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise CacheValidationError(f"{name} muss ein Integer in {minimum}..{maximum} sein")
    return value


def _require_nonnegative_int(filtered: dict, name: str) -> int:
    value = filtered[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CacheValidationError(f"{name} muss ein nichtnegativer Integer sein")
    return value


def _validate_top_level_patterns(filtered: dict) -> None:
    for name in ("groove_pattern", "bass_pattern"):
        values = filtered[name]
        _validate_candidate_pattern(values, name, length=16, unit_interval=True)
        if values and not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise CacheValidationError(f"{name} muss L1-normalisiert sein")
    for name in ("mfcc_fingerprint", "timbre_fingerprint"):
        _validate_candidate_pattern(filtered[name], name, length=13, unit_interval=False)


def _validate_lufs_contract(filtered: dict, duration: float) -> None:
    status = filtered["lufs_status"]
    if status not in {"unknown", "complete", "invalid", "error"}:
        raise CacheValidationError("lufs_status ist ungueltig")
    lufs = filtered["lufs"]
    if not _is_finite_number(lufs):
        raise CacheValidationError("lufs muss endlich sein")
    coverage = _require_real_in_range(
        filtered, "lufs_coverage_seconds", 0.0, duration
    )
    channels = _require_nonnegative_int(filtered, "lufs_channels")
    sample_rate = _require_nonnegative_int(filtered, "lufs_sample_rate")
    if status == "complete":
        if not -70.0 <= lufs < 0.0 or coverage <= 0.0 or not 1 <= channels <= 5 or sample_rate <= 0:
            raise CacheValidationError("vollstaendiger LUFS-Record ist inkonsistent")
    elif status == "invalid":
        if lufs != 0.0 or coverage <= 0.0 or channels <= 0 or sample_rate <= 0:
            raise CacheValidationError("ungueltiger LUFS-Record ist inkonsistent")
    elif lufs != 0.0 or coverage != 0.0 or channels != 0 or sample_rate != 0:
        raise CacheValidationError(f"LUFS-Status {status} erfordert leere Messwerte")


def _validate_top_level_physics(filtered: dict) -> tuple[float, float, float]:
    duration = _require_real_in_range(
        filtered, "duration", 0.0, 7200.0, minimum_exclusive=True
    )
    _require_real_in_range(
        filtered, "bpm", 20.0, 300.0,
        minimum_exclusive=True, maximum_exclusive=True,
    )
    for name in ("energy", "bass_intensity", "brightness", "danceability"):
        _require_int_in_range(filtered, name, 0, 100)
    bands = [
        _require_real_in_range(filtered, name, 0.0, 100.0)
        for name in ("avg_bass", "avg_mids", "avg_highs")
    ]
    if any(bands) and not math.isclose(sum(bands), 100.0, rel_tol=0.0, abs_tol=0.21):
        raise CacheValidationError("avg_bass/avg_mids/avg_highs muessen zusammen etwa 100 ergeben")
    for name in ("spectral_flatness", "percussive_ratio", "syncopation", "sub_energy"):
        _require_real_in_range(filtered, name, 0.0, 1.0)
    _require_real_in_range(filtered, "bass_punch", 0.0, sys.float_info.max)
    first_downbeat = _require_real_in_range(filtered, "first_downbeat", 0.0, duration)
    first_phrase = filtered["first_phrase"]
    if not _is_finite_number(first_phrase) or (
        first_phrase != MIX_POINT_UNSET and not 0.0 <= first_phrase <= duration
    ):
        raise CacheValidationError("first_phrase muss -1 oder innerhalb der Dauer sein")
    for name in ("mix_in_bars", "mix_out_bars", "beatgrid_windows_checked"):
        _require_nonnegative_int(filtered, name)
    _validate_top_level_patterns(filtered)
    _validate_lufs_contract(filtered, duration)
    return duration, first_downbeat, float(first_phrase)


def validate_track_dict(data: dict) -> dict:
    """Validiert Typen und Kerninvarianten eines flachen Track-Records."""
    if not isinstance(data, dict):
        raise CacheValidationError("Track-Record ist kein Dictionary")

    missing = sorted(TRACK_REQUIRED_FIELDS.difference(data))
    if missing:
        raise CacheValidationError(f"Pflichtfeld {missing[0]} fehlt")

    filtered = {key: value for key, value in data.items() if key in TRACK_REQUIRED_FIELDS}
    # Bereichsfehler benennen, bevor Herkunftsprüfungen diese Werte vergleichen.
    for name in TRACK_CONFIDENCE_FIELDS:
        _require_real_in_range(filtered, name, 0.0, 1.0)
    from .measurement_contract import validate_measurement_diagnostics
    from .ai_models.cue_service import validate_neural_analysis
    from .models import bar_position_usage_blocked
    try:
        validate_measurement_diagnostics(filtered["measurement_diagnostics"])
        measured = filtered['measurement_diagnostics']
        if measured.get('version') in {6, 7, 8}:
            phrase_diagnostic = measured['phrase_unit']
            for diagnostic_key, track_key in (
                    ('unit', 'phrase_unit'), ('source', 'phrase_unit_source'),
                    ('candidate', 'phrase_unit_candidate'),
                    ('raw_score', 'phrase_unit_score'),
                    ('ranking_margin', 'phrase_unit_margin')):
                if phrase_diagnostic[diagnostic_key] != filtered[track_key]:
                    raise CacheValidationError(
                        f"measurement_diagnostics.phrase_unit.{diagnostic_key} widerspricht {track_key}"
                    )
        if bar_position_usage_blocked(measured):
            if (
                filtered["first_phrase"] != MIX_POINT_UNSET
                or filtered["phrase_confidence"] != 0.0
                or filtered["phrases"]
                or filtered["phrase_grid"]
                or filtered["mix_in_candidates"]
                or filtered["mix_out_candidates"]
                or filtered["mix_in_point"] != MIX_POINT_UNSET
                or filtered["mix_out_point"] != MIX_POINT_UNSET
            ):
                raise ValueError("Taktpositionsrotation verlangt gesperrte Phrasen- und Mixausgaben")
        if measured.get('version') in {2, 3, 4, 5, 6, 7, 8} and 'anchor' in measured:
            active = measured['anchor']
            if (active['source'] != filtered['beatgrid_source']
                    or active['anchor_s'] != filtered['first_downbeat']
                    or active['confidence'] != filtered['downbeat_confidence']
                    or measured['grid']['status'] != filtered['beatgrid_status']
                    or measured['grid']['windows_checked'] != filtered['beatgrid_windows_checked']
                    or measured['grid']['max_phase_error_ms'] != filtered['beatgrid_max_phase_error_ms']):
                raise ValueError('Aktive Ankerdiagnose widerspricht Track')
            if active['source'] != 'rekordbox' and filtered['phrases']:
                raise ValueError('PSSI erfordert bestaetigte Rekordbox-Referenz')

        from .ai_models.native_track_beats import validate_snapshot as validate_native_beats
        native_beats = filtered['native_beat_analysis']
        if native_beats:
            validate_native_beats(native_beats, duration=filtered['duration'])
        native_method = measured.get('anchor', {}).get('method')
        blocked_bar_position = bar_position_usage_blocked(measured)
        bar_status = filtered['bar_position_status']
        if ((bar_status == 'blocked') != blocked_bar_position
                or bar_status == 'reference_verified' and not (
                    filtered['beatgrid_source'] == 'rekordbox'
                    and filtered['beatgrid_status'] == 'verified'
                    and filtered['downbeat_confidence'] == 1.0
                    and measured.get('anchor', {}).get('bar_position_comparison', {}).get('status') == 'aligned')
                or bar_status == 'reference_candidate' and not (
                    filtered['beatgrid_source'] == 'rekordbox'
                    and filtered['beatgrid_status'] == 'verified'
                    and filtered['downbeat_confidence'] == 1.0
                    and measured.get('anchor', {}).get('bar_position_comparison', {}).get('status') != 'aligned')
                or bar_status == 'native_candidate' and not (
                    native_method in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                    and native_beats.get('status') == 'ok'
                    and filtered['downbeat_confidence'] == 0.)
                or native_method in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                   and bar_status != ('audio_estimate' if filtered['downbeat_confidence'] > 0.
                                      else 'native_candidate')
                or bar_status == 'audio_estimate' and not (
                    filtered['beatgrid_source'] == 'audio'
                    and filtered['downbeat_confidence'] > 0.0)
                or bar_status == 'unknown'
                   and filtered['downbeat_confidence'] >= DOWNBEAT_RELIABLE_MIN):
            raise ValueError('Taktpositionsstatus widerspricht der aktiven Analysequelle')
        if native_method in {'native_rekordbox', 'native_rekordbox_audio_offset'}:
            from .ai_models.native_beat_alignment import active_anchor
            if (native_beats.get('status') != 'ok'
                    or filtered['bpm'] != native_beats['bpm']
                    or filtered['first_downbeat'] != active_anchor(native_beats)
                    or ('audio_alignment' in native_beats) != (native_method == 'native_rekordbox_audio_offset')
                    or filtered['beatgrid_status'] != 'verified'):
                raise ValueError('Native beat provenance conflicts with active track')
            if filtered['downbeat_confidence'] > 0.:
                # Anzahl und Konfidenz prüft der Messvertrag; hier die Bindung
                # aller bestätigten Fenster an genau diese native Taktphase.
                bar = 4. * 60. / filtered['bpm']
                windows = measured['anchor']['neural']['windows']
                if any(abs((row['anchor_s'] - filtered['first_downbeat'] + bar/2)
                           % bar - bar/2) > EXACT_BEAT_SYNC_TOLERANCE_SECONDS
                       for row in windows if row['reason'] == 'confirmed'):
                    raise ValueError('Native bar confirmation conflicts with active anchor')
        from .ai_models.native_phrase_adapter import validate_snapshot, _normalize_grid_origin
        validate_snapshot(filtered['native_phrase_analysis'], duration=filtered['duration'],
            grid_verified=(filtered['beatgrid_status'] == 'verified'
                           and (filtered['downbeat_confidence'] >= DOWNBEAT_RELIABLE_MIN
                                or filtered['bar_position_status'] == 'native_candidate')),
            usage_blocked=bar_position_usage_blocked(measured))
        native = filtered['native_phrase_analysis']
        phase_usable = (
            filtered['bar_position_status'] not in {
                'reference_candidate', 'blocked', 'unknown',
            }
            and (filtered['bar_position_status'] != 'audio_estimate'
                 or filtered['downbeat_confidence'] >= DOWNBEAT_RELIABLE_MIN)
            and (filtered['beatgrid_source'] != 'rekordbox'
                 or filtered['bar_position_status'] == 'reference_verified')
        )
        if filtered['phrases'] and (
                filtered['beatgrid_source'] != 'rekordbox'
                or filtered['beatgrid_status'] != 'verified'
                or blocked_bar_position):
            raise ValueError('PSSI requires a verified, unblocked Rekordbox beatgrid')
        if native.get('status') == 'ok' and not phase_usable:
            raise ValueError('Native phrases require a usable phrase phase')
        if native.get('status') == 'ok':
            native_grid = native['input_grid']
            if native_grid['offset_ms'] * native_grid['bpm_hundredths'] >= 6_000_000:
                raise ValueError(
                    'Native phrase offset rounds to a full beat period'
                )
            from .ai_models.native_key import native_key_index
            expected_key = native_key_index(filtered['keyNote'], filtered['keyMode'])
            if (native['key_source'] != ('native_unknown_fallback_zero' if expected_key is None
                                        else 'hpg_key_native_table')
                    or native_grid['key_index'] != (0 if expected_key is None else expected_key)):
                raise ValueError('Native phrase key provenance mismatch')
            if (filtered['phrases'] or not filtered['neural_analysis']
                    or native_grid['bpm_hundredths'] != int(math.floor(filtered['bpm']*100+.5))
                    or (native_grid['basis'] == 'verified_rekordbox_grid') != (filtered['beatgrid_source'] == 'rekordbox')):
                raise ValueError('Native phrase provenance contradicts track')
            if native_grid['basis'] == 'native_verified_audio_grid':
                if (native_method not in {'native_rekordbox', 'native_rekordbox_audio_offset'}
                        or native_beats.get('status') != 'ok'):
                    raise ValueError('Native phrase grid lacks accepted native beats')
                from .ai_models.native_beat_alignment import active_anchor
                shift = (native_beats['audio_alignment']['offset_seconds']
                         if 'audio_alignment' in native_beats else 0.0)
                expected_grid = [
                    (row['pos'] / 44100.0 + shift, row['numBar'])
                    for row in native_beats['grid']
                    if 0.0 <= row['pos'] / 44100.0 + shift <= filtered['duration']
                ]
                if not expected_grid:
                    raise ValueError('Native phrase grid lacks source beats')
                expected_times, expected_positions, extension = _normalize_grid_origin(
                    [row[0] for row in expected_grid], [row[1] for row in expected_grid],
                    bpm=filtered['bpm'])
                if (abs(active_anchor(native_beats) - filtered['first_downbeat']) > 1e-9
                        or native_grid['source_beat_count'] != len(expected_grid)
                        or native_grid['origin_extension_beats'] != extension
                        or native_grid['beat_count'] != len(expected_times)
                        or native_grid['bar_position'] != expected_positions[0]
                        or abs(native_grid['first_tick_s'] - expected_times[0]) > 1e-9
                        or abs(native_grid['last_tick_s'] - expected_times[-1]) > 1e-9
                        or any(not any(abs(phrase[key] - stamp) <= 1e-9
                                       for stamp in expected_times)
                               for phrase in native['phrases']
                               for key in ('start_s', 'end_s'))):
                    raise ValueError('Native phrase boundaries do not follow accepted native beats')
        validate_neural_analysis(filtered["neural_analysis"], track_duration_s=filtered['duration'])
        if filtered['neural_analysis']:
            suffix = '|neural:' + filtered['neural_analysis']['fingerprint']
            if not isinstance(filtered['rekordbox_signature'], str) or not filtered['rekordbox_signature'].endswith(suffix):
                raise ValueError('neural_analysis passt nicht zur Quellidentität')
    except ValueError as error:
        raise CacheValidationError(str(error)) from error
    if filtered.get("ai_metadata"):
        from .ai_engine import validate_ai_metadata
        if not validate_ai_metadata(filtered["ai_metadata"], duration=filtered.get("duration")):
            raise CacheValidationError("ai_metadata verletzt den KI-Vertrag")
    for required in ("filePath", "fileName"):
        if not isinstance(filtered.get(required), str) or not filtered[required]:
            raise CacheValidationError(f"Pflichtfeld {required} fehlt oder ist ungueltig")

    for name in TRACK_STRING_FIELDS:
        if not isinstance(filtered[name], str):
            raise CacheValidationError(f"{name} muss ein String sein")
    if filtered["bar_position_status"] not in {
            "reference_verified", "reference_candidate", "native_candidate",
            "audio_estimate", "blocked", "unknown"}:
        raise CacheValidationError("Ungültiger Taktpositionsstatus")
    for name in TRACK_BOOL_FIELDS:
        if not isinstance(filtered[name], bool):
            raise CacheValidationError(f"{name} muss ein Boolean sein")

    for name in TRACK_LIST_FIELDS:
        if name in filtered and not isinstance(filtered[name], list):
            raise CacheValidationError(f"{name} muss eine Liste sein")
    for name in TRACK_DICT_FIELDS:
        if name in filtered and not isinstance(filtered[name], dict):
            raise CacheValidationError(f"{name} muss ein Dictionary sein")

    for name in TRACK_NUMERIC_FIELDS:
        if name in filtered and (
            isinstance(filtered[name], bool)
            or not isinstance(filtered[name], (int, float))
        ):
            raise CacheValidationError(f"{name} muss numerisch sein")

    for name, value in filtered.items():
        if name not in {"mix_in_candidates", "mix_out_candidates"}:
            _validate_finite_values(value, name)
    duration, _first_downbeat, _first_phrase = _validate_top_level_physics(filtered)
    from .ai_models.deep_features import source_duration_tolerance, validate as validate_deep_feature
    try:
        for kind, field in (('stems', 'stem_analysis'), ('embedding', 'embedding_analysis')):
            snapshot = filtered[field]
            validate_deep_feature(
                snapshot, kind=kind, duration=duration,
                duration_tolerance=source_duration_tolerance(filtered['filePath']),
            )
    except (ValueError, TypeError, KeyError) as error:
        raise CacheValidationError(str(error)) from error

    source = filtered.get("beatgrid_source", "unknown")
    status = filtered.get("beatgrid_status", "unknown")
    if source not in BEATGRID_SOURCES:
        raise CacheValidationError("beatgrid_source ist ungueltig")
    if status not in BEATGRID_STATUSES:
        raise CacheValidationError("beatgrid_status ist ungueltig")
    windows = filtered.get("beatgrid_windows_checked", 0)
    if isinstance(windows, bool) or not isinstance(windows, int) or windows < 0:
        raise CacheValidationError("beatgrid_windows_checked ist ungueltig")
    phase_error = filtered.get("beatgrid_max_phase_error_ms", -1.0)
    if not _is_finite_number(phase_error) or (
        phase_error != MIX_POINT_UNSET and phase_error < 0.0
    ):
        raise CacheValidationError("beatgrid_max_phase_error_ms ist ungueltig")
    if status == "verified" and (
        source not in {"rekordbox", "audio"}
        or windows < 3
        or phase_error < 0.0
        or phase_error > EXACT_BEAT_SYNC_TOLERANCE_SECONDS * 1000.0
    ):
        raise CacheValidationError("verifiziertes Beatgrid hat unvollstaendige Messwerte")
    if source == "rekordbox" and status == "verified" and filtered.get(
        "downbeat_confidence"
    ) != REFERENCE_BEATGRID_CONFIDENCE:
        raise CacheValidationError("verifiziertes Rekordbox-Beatgrid braucht Referenzkonfidenz")

    mix_in = filtered["mix_in_point"]
    mix_out = filtered["mix_out_point"]
    for name, value in (("mix_in_point", mix_in), ("mix_out_point", mix_out)):
        if not _is_finite_number(value) or (
            value != MIX_POINT_UNSET and not 0.0 <= value <= duration
        ):
            raise CacheValidationError(f"{name} muss -1 oder innerhalb der Dauer sein")
    if mix_in >= 0 and mix_out >= 0 and not mix_in < mix_out:
        raise CacheValidationError("Mix-In muss vor Mix-Out liegen")
    phrase_unit = filtered["phrase_unit"]
    if (
        not is_supported_phrase_unit(phrase_unit)
    ):
        raise CacheValidationError("phrase_unit muss 8, 16 oder 32 sein")
    phrase_unit_source = filtered["phrase_unit_source"]
    if (type(phrase_unit_source) is not str
            or phrase_unit_source not in {"genre_prior", "audio_novelty", "configured"}):
        raise CacheValidationError("phrase_unit_source ist ungueltig")
    phrase_unit_candidate = filtered["phrase_unit_candidate"]
    if (phrase_unit_candidate is not None
            and not is_supported_phrase_unit(phrase_unit_candidate)):
        raise CacheValidationError("phrase_unit_candidate muss 8, 16, 32 oder None sein")
    phrase_unit_score = filtered["phrase_unit_score"]
    phrase_unit_margin = filtered["phrase_unit_margin"]
    if phrase_unit_candidate is None:
        if phrase_unit_score is not None or phrase_unit_margin is not None:
            raise CacheValidationError("Novelty-Score ohne Phrasenkandidat")
    else:
        if phrase_unit_score is None or not _is_finite_number(phrase_unit_score):
            raise CacheValidationError("phrase_unit_score muss endlich sein")
        if phrase_unit_margin is not None and (
            not _is_finite_number(phrase_unit_margin) or phrase_unit_margin < 0.0
        ):
            raise CacheValidationError("phrase_unit_margin muss endlich und nichtnegativ sein")
    if phrase_unit_source == "audio_novelty" and (
        phrase_unit_candidate != phrase_unit or phrase_unit_score is None or phrase_unit_margin is None
    ):
        raise CacheValidationError("audio_novelty erfordert vollstaendige Messwerte")
    _validate_sections(filtered["sections"], duration)
    coverage = _validate_analysis_coverage(filtered["analysis_coverage"], duration)
    phrases = _validate_phrases(filtered["phrases"], duration)
    _validate_cue_points(filtered["cue_points"], duration)
    _validate_phrase_grid(filtered["phrase_grid"], duration)
    _validate_coverage_sections(coverage, filtered["sections"], duration)
    if filtered["outro_covered"] and (
        not coverage
        or duration - coverage[-1][1] > ANALYSIS_COVERAGE_GAP_TOLERANCE
    ):
        raise CacheValidationError(
            "outro_covered erfordert Analyse-Coverage bis zum Trackende"
        )
    native_phrases = filtered['native_phrase_analysis'].get('phrases', [])
    active_intervals = phrases or [(p['start_s'], p['end_s']) for p in native_phrases]
    _validate_phrases_and_grid(active_intervals, filtered["phrase_grid"])
    _validate_mix_candidate_lists(filtered, duration)
    if filtered["analysis_mode"] not in VALID_ANALYSIS_MODES:
        raise CacheValidationError("analysis_mode ist ungueltig")
    return filtered
