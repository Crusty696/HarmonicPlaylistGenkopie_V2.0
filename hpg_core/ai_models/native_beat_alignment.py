"""Getrennte Audio-Zeitkorrektur; native Taktzahlen und Rohpositionen bleiben erhalten."""
import math

from ..downbeat import EXACT_BEAT_SYNC_TOLERANCE_SECONDS, BEATGRID_MIN_FOLD_LOCK


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def stable_model_window(native, start, width):
    """Fenster vor der Audioprüfung auswählen, ohne deren Phasenfehler zu kennen.

    Unregelmäßige Modellbeats in Breaks eignen sich nicht zur Kickbestätigung.
    100-Hz-Modellraster: zwei Quantisierungsschritte plus 2% Tempotoleranz.
    """
    period = 60. / native['bpm']
    verification = native.get('verification')
    rows = verification['beats'] if verification else native.get('model_beats', [])
    times = [r[0] for r in rows if start <= r[0] < start + width]
    return (len(times) >= 8 and times[0] - start <= period
            and start + width - times[-1] <= period
            and all(abs(b-a-period) <= .02 + .02*period for a, b in zip(times, times[1:])))


def single_window_evidence_plan(native, duration, span, *, eligible_starts=None):
    """Sechs disjunkte Fenster vor jeder Audiomessung wählen.

    Modell8 beobachtet je Segment höchstens 60s. Bestätigungen liegen in
    beobachteten Bereichen; Kalibrierungen liegen außerhalb aller Bereiche.
    Keine Auswahl anhand des später gemessenen Phasenfehlers.
    """
    if native.get('verification') or (
            eligible_starts is not None and native.get('selection', {}).get('chunked')):
        # Alle sechs Abschnitte vor jeder Phasenmessung aus tatsächlich
        # modellbeobachteten, regelmäßigen Beats wählen; nie nach Restfehler.
        candidates = [float(start) for start in range(math.floor(duration-span)+1)
                      if (eligible_starts is None or start in eligible_starts)
                      if stable_model_window(native, float(start), span)]
        selected = []
        # Feste innere Quantile vermeiden Fade-In/Outro als Kickreferenz.
        # Der lokale Kandidaten- und Rendercheck prüft spätere Mixstellen
        # zusätzlich; kein Fenster wird nach seinem Phasenfehler ersetzt.
        for fraction in (.2, .5, .8, .1, .35, .65):
            target = duration*fraction
            available = [start for start in candidates if all(
                start+span <= other or start >= other+span for other in selected)]
            if not available:
                return None
            selected.append(min(available, key=lambda start: (abs(start-target), start)))
        return tuple(selected[:3]), tuple(selected[3:])
    if native.get('selection', {}).get('chunked', True):
        return None
    coverage = native.get('model_coverage')
    segments = native.get('model_coverage_segments') or ([coverage] if coverage else [])
    if not segments or duration < 6*span:
        return None
    observed_candidates = [float(start) for start in range(math.floor(duration-span)+1)
                           if (eligible_starts is None or start in eligible_starts)
                           if any(segment['start_s'] <= start
                                  and start+span <= segment['end_s']
                                  for segment in segments)
                           and stable_model_window(native, float(start), span)]
    confirmation = []
    for fraction in (.2, .5, .8):
        target = duration*fraction
        available = [start for start in observed_candidates if all(
            start+span <= other or start >= other+span for other in confirmation)]
        if not available:
            return None
        confirmation.append(min(available, key=lambda start: (abs(start-target), start)))
    candidates = [float(start) for start in range(math.floor(duration-span)+1)
                  if (eligible_starts is None or start in eligible_starts)
                  if all(start+span <= segment['start_s'] or
                         start >= segment['end_s'] for segment in segments)]
    calibration = []
    for target in (0., duration/2-span/2, duration-span):
        available = [start for start in candidates if all(
            start+span <= other or start >= other+span for other in calibration)]
        if not available:
            return None
        calibration.append(min(available, key=lambda start: (abs(start-target), start)))
    return tuple(sorted(calibration)), tuple(confirmation)


def validate_alignment(native, alignment):
    if type(alignment) is not dict or set(alignment) != {'offset_seconds', 'calibration', 'confirmation'}:
        raise ValueError('Invalid native audio alignment')
    shift = alignment['offset_seconds']
    period = 60. / native['bpm']
    tolerance = EXACT_BEAT_SYNC_TOLERANCE_SECONDS
    if (not _finite_number(shift)
            or not tolerance < abs(shift) < period / 4
            or native['first_downbeat'] + shift < 0):
        raise ValueError('Invalid native phase correction')
    intervals = []
    calibrated_errors = []
    for group in ('calibration', 'confirmation'):
        rows = alignment[group]
        if type(rows) is not list or len(rows) != 3:
            raise ValueError('Three disjoint audio windows required')
        for row in rows:
            keys = {'offset_seconds', 'duration_seconds', 'phase_seconds', 'fold_lock',
                    'phase_error_ms', 'reason', 'signed_phase_error_ms'}
            if type(row) is not dict or set(row) != keys or row['reason'] != 'measured':
                raise ValueError('Invalid native audio evidence')
            if any(not _finite_number(row[k])
                   for k in keys - {'reason'}):
                raise ValueError('Nonfinite native audio evidence')
            start, width = row['offset_seconds'], row['duration_seconds']
            if group == 'confirmation' and not stable_model_window(native, start, width):
                raise ValueError('Native confirmation lacks stable model beats')
            if (start < 0 or width < 8 * period or start + width > native['frames']/44100 + 1e-6
                    or not BEATGRID_MIN_FOLD_LOCK <= row['fold_lock'] <= 1
                    or not 0 <= row['phase_seconds'] < period):
                raise ValueError('Invalid native audio window')
            if any(start < end and start + width > begin for begin, end in intervals):
                raise ValueError('Native confirmation windows overlap')
            intervals.append((start, start + width))
            correction = shift if group == 'confirmation' else 0.
            tick = min((r['pos']/44100 + correction for r in native['grid']),
                       key=lambda t: abs(t - start))
            signed = (row['phase_seconds'] - (tick-start) + period/2) % period - period/2
            if (abs(signed*1000-row['signed_phase_error_ms']) > .002
                    or abs(abs(signed)*1000-row['phase_error_ms']) > .002):
                raise ValueError('Native phase evidence inconsistent')
            residual = signed - shift if group == 'calibration' else signed
            if abs(residual) > tolerance + 1e-6:
                raise ValueError('Native corrected phase exceeds sync tolerance')
            if group == 'calibration':
                calibrated_errors.append(signed)
    # Der gespeicherte Versatz muss aus den Messungen stammen, nicht aus einem
    # nachträglich gewählten Taktanker. Median bei drei konsistenten Fenstern.
    if abs(sorted(calibrated_errors)[1] - shift) > 1e-6:
        raise ValueError('Native correction differs from measured median')


def active_anchor(native):
    alignment = native.get('audio_alignment')
    if alignment is None:
        return native['first_downbeat']
    validate_alignment(native, alignment)
    return native['first_downbeat'] + alignment['offset_seconds']
