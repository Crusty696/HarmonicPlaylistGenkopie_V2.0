"""
hpg_core/downbeat.py — Downbeat-Erkennung (die "1") fuer 4/4-Elektronik.

Ansatz nach Vande Veire & De Bie (EURASIP 2018, "From raw audio to a seamless
mix" — dort 98,1% korrekte Downbeat-Phase auf elektronischer Musik) als
leichtgewichtige Eigenimplementierung ohne neue Dependencies:

1. Beat-Raster via librosa.beat.beat_track (BPM-Prior aus der Analyse)
2. Leise Beats trimmen (Intro/Breakdown verwaessern das Voting)
3. Pro Beat drei z-normierte Indizien fuer "das ist eine 1":
   - Bass-Onset-Staerke (Hockman et al., ISMIR 2012: Low-Frequency-Onsets
     allein erreichen 72,8% — Kicks/Basswechsel markieren die 1)
   - Chroma-Novelty an der Beatgrenze (Davies/Plumbley-Prinzip:
     Harmoniewechsel fallen auf die 1)
   - Loudness-Akzent relativ zu den Nachbar-Beats
4. Phase-Voting ueber die 4 Hypothesen (Beat-Index mod 4) ueber den GANZEN
   Track — Einzel-Beat-Klassifikation darf mittelmaessig sein, die Summe
   ueber hunderte Takte ist robust und liefert EINE konsistente Phase.
5. Sub-Beat-Feinausrichtung ueber die beat-synchrone Faltung der nullphasig
   tiefpassgefilterten Huellkurve (D-03): das Voting bestimmt WELCHER Beat
   die "1" ist, die Faltung WO im Beat sie genau liegt.

Plan + Quellen: docs/plans/2026-07-17-downbeat-erkennung.md
"""

from __future__ import annotations

import logging

import numpy as np
import librosa
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfiltfilt

from .config import HOP_LENGTH, METER

logger = logging.getLogger(__name__)

# Konfidenz-Skala von ``Track.downbeat_confidence``
# ------------------------------------------------
# 1.0 ist EXKLUSIV dem Rekordbox-ANLZ-Beatgrid vorbehalten. Nur dort ist auch
# die TAKT-Phase (welcher Beat ist die "1") belegt; die Eigenschaetzung ist
# deshalb hart unter 1.0 gedeckelt.
REFERENCE_BEATGRID_CONFIDENCE = 1.0
SELF_ESTIMATE_CONFIDENCE_MAX = 0.99

# AUDIT-FIX D-03 (2026-08-14): kalibrierte Mindest-Konfidenz fuer ein
# Beat-Phase-Alignment aus der EIGENSCHAETZUNG.
# Kalibriert an 35 Tracks mit Rekordbox-ANLZ-Beatgrid als Ground Truth
# (Paare aus Konfidenz und tatsaechlichem Phasenfehler); 19 davon liefern
# ueberhaupt eine Eigenschaetzung, 16 werden vom Kommensurabilitaets-Gate
# (D-02) verworfen. Hoerbare Grenze: 1/8 Beat (54 ms bei 138 BPM) — darueber
# sind zwei Kicks nicht mehr ein Kick mit Flam, sondern zwei Kicks.
# Gemessene Trennung auf den 19 Schaetzungen:
#   Konfidenz >= 0.30  -> 12 Tracks, Sub-Beat-Fehler Median 16 ms, Max 43 ms
#   Konfidenz <= 0.241 -> enthaelt ALLE drei Ausreisser (83 / 153 / 188 ms)
# Die Luecke 0.241 .. 0.391 ist eindeutig; 0.30 liegt geometrisch mittig
# (sqrt(0.241 * 0.391) = 0.307).
DOWNBEAT_RELIABLE_MIN = 0.30

# Analytischer Deckel der rohen Voting-Margin: die vier Votes sind Summen
# z-normierter Groessen und summieren sich damit exakt zu 0. Unter dieser
# Nebenbedingung ist max (v1-v2)/sum|v| = 2/3 (angenommen bei
# v = (S, -S/3, -S/3, -S/3)). Ohne Ruecknormierung erreicht die
# Eigenschaetzung deshalb NIE mehr als 0.667 — ein Artefakt der Normierung,
# kein Qualitaetsurteil. Gemessen: perfekter Klick-Track 0.50, bester echter
# Track 0.651.
_VOTE_MARGIN_CAP = 2.0 / 3.0

# Sub-Beat-Feinausrichtung (Faltung): Tiefband-Grenze und Huellkurven-Glaettung
_FOLD_LOWPASS_HZ = 150.0
_FOLD_SMOOTH_SEC = 0.005
_FOLD_BINS = 1024
# Attack-Punkt = Ruecklauf vom Profil-Maximum bis unter diesen Anteil des
# Profil-Hubs. 0.15 traf die ANLZ-Referenz am besten (Median 16 ms).
_FOLD_ATTACK_FRACTION = 0.15
# Mindestzahl gefalteter Beats, damit das Mittel nicht von Einzelereignissen
# dominiert wird
_FOLD_MIN_BEATS = 8

# Beats unterhalb dieses Anteils der Maximal-Loudness werden nicht gewertet
# (Vande Veire trimmt Intro/Outro vor dem Voting)
_TRIM_RATIO = 0.3

# Gewichte der drei Indizien (Bass, Chroma-Novelty, Loudness-Akzent)
_WEIGHTS = (1.0, 1.0, 0.5)

# Mindestanzahl auswertbarer Beats fuer ein belastbares Voting
_MIN_BEATS = 16

# AUDIT-FIX D-02 (2026-08-14): Maximal zulaessige relative Abweichung des
# librosa-Beat-Rasters von einem GANZZAHLIGEN Vielfachen bzw. Teiler des
# Beat-Abstands, der sich aus `bpm` ergibt.
# Kalibriert an 34 echten Psytrance-AIFFs (D:/beatport_tracks_2025-08):
# 23 Tracks lagen auf <=3,8 % beim Verhaeltnis 1, 11 Tracks waren mit 1,32 bis
# 1,49 (fast immer 3:2 — 138-BPM-Tracks getrackt als ~93 BPM) inkommensurabel;
# der naechste ganzzahlige Bezug lag dort >=24 % entfernt. Die Luecke zwischen
# 3,8 % und 24 % ist eindeutig, 10 % liegt mit Faktor 2,6 Abstand zu beiden
# Seiten darin.
_GRID_TEMPO_TOLERANCE = 0.10


def _grid_is_commensurate(grid_ibi: float, expected_ibi: float) -> bool:
    """Liegt das getrackte Beat-Raster auf dem Gitter aus ``bpm``?

    Toleriert ganzzahlige Vielfache und Teiler: trackt librosa nur jeden
    zweiten Beat oder gleich ganze Takte, liegen die gefundenen Beats immer
    noch AUF dem Zielgitter. Verworfen wird nur ein inkommensurables Raster
    (typisch 3:2), dessen Beats zwischen die Zielbeats fallen — dort ist die
    ``% 4``-Phase auf dem Zielgitter nicht definiert.
    """
    if grid_ibi <= 0 or expected_ibi <= 0:
        return False
    ratio = grid_ibi / expected_ibi
    k = round(ratio) if ratio >= 1.0 else round(1.0 / ratio)
    if k < 1:
        return False
    normalized = ratio / k if ratio >= 1.0 else ratio * k
    return abs(normalized - 1.0) <= _GRID_TEMPO_TOLERANCE


def _bar_phase_confidence(votes: np.ndarray) -> float:
    """Ehrliche 0..1-Konfidenz der TAKT-Phase aus dem 4-Bin-Voting.

    Die rohe Margin (v1-v2)/sum|v| kann wegen sum(votes)==0 nie ueber
    ``_VOTE_MARGIN_CAP`` = 2/3 steigen. Ohne Ruecknormierung ist jedes Gate
    oberhalb 2/3 fuer eine Eigenschaetzung unerreichbar — genau daran hingen
    die frueheren ">= 0.9"-Gates, die damit faktisch "nur Rekordbox" hiessen.
    """
    if votes.size < 2:
        return 0.0
    spread = float(np.sum(np.abs(votes)))
    if spread < 1e-9:
        return 0.0
    order = np.argsort(votes)[::-1]
    margin = float(votes[order[0]] - votes[order[1]]) / spread
    return float(np.clip(margin / _VOTE_MARGIN_CAP, 0.0, 1.0))


def _beat_phase_from_fold(
    y: np.ndarray, sr: int, ibi: float
) -> tuple[float | None, float]:
    """Sub-Beat-Phase per beat-synchroner Faltung der Tiefband-Huellkurve.

    AUDIT-FIX D-03 (2026-08-14): Der vorherige Feinschliff snappte den Anker
    auf den staerksten Bass-Onset-FRAME. Das ist doppelt ungenau:
      1. Die Frame-Aufloesung betraegt HOP_LENGTH/sr = 46 ms — allein das
         Raster verfehlt die hoerbare Grenze von 54 ms fast schon.
      2. ``librosa.onset.onset_strength`` hat eine systematische Latenz
         (Fensterbreite + Anstiegszeit des Sub-Bass). An 35 Tracks mit
         ANLZ-Ground-Truth lag die daraus gewonnene Phase im Median 116 ms
         HINTER dem echten Beatgrid — bei jeder getesteten Hop-Groesse gleich.
    Gemessen ueber alle 19 Eigenschaetzungen: Sub-Beat-Fehler Median 129 ms
    (alt) gegen 16 ms (Faltung).

    Verfahren:
      * Tiefpass 150 Hz mit ``sosfiltfilt`` — NULLPHASIG, also ohne
        Gruppenlaufzeit, die man hinterher wegschaetzen muesste.
      * Betrag, zentriert geglaettet (ebenfalls verzoegerungsfrei).
      * Falten aller Samples auf eine Beat-Periode ueber die exakte
        Fliesskomma-Phase (``t % ibi``) statt ueber ganzzahlige Blockgroessen:
        so entsteht keine Drift ueber die Tracklaenge.
      * Attack-Punkt statt Maximum: das Huellkurven-Maximum eines Kicks liegt
        im Koerper, nicht im Einsatz (gemessen 84 ms zu spaet). Gesucht ist
        der Ruecklauf vom Maximum unter ``_FOLD_ATTACK_FRACTION`` des Hubs.

    Returns:
        (beat_phase_seconds in [0, ibi), lock 0..1) oder (None, 0.0).
        ``lock`` ist der relative Hub des gefalteten Profils: 0 = keine
        beat-synchrone Struktur, ~1 = klarer, immer gleicher Transient.
    """
    if ibi <= 0 or y is None or sr <= 0:
        return None, 0.0
    if len(y) < _FOLD_MIN_BEATS * ibi * sr:
        return None, 0.0
    nyquist = sr / 2.0
    if _FOLD_LOWPASS_HZ >= nyquist:
        return None, 0.0
    sos = butter(4, _FOLD_LOWPASS_HZ / nyquist, btype="low", output="sos")
    env = np.abs(sosfiltfilt(sos, y.astype(np.float64)))
    smooth = max(3, int(_FOLD_SMOOTH_SEC * sr) | 1)
    env = uniform_filter1d(env, size=smooth, mode="nearest")

    phase = np.mod(np.arange(len(env), dtype=np.float64) / sr, ibi)
    bins = (phase / ibi * _FOLD_BINS).astype(np.int32)
    np.clip(bins, 0, _FOLD_BINS - 1, out=bins)
    counts = np.bincount(bins, minlength=_FOLD_BINS).astype(np.float64)
    profile = np.bincount(bins, weights=env, minlength=_FOLD_BINS) / np.maximum(
        counts, 1.0
    )
    peak_value = float(np.max(profile))
    if peak_value <= 1e-12:
        return None, 0.0
    floor_value = float(np.min(profile))
    lock = float(np.clip((peak_value - floor_value) / peak_value, 0.0, 1.0))

    threshold = floor_value + _FOLD_ATTACK_FRACTION * (peak_value - floor_value)
    peak_bin = int(np.argmax(profile))
    attack_bin = peak_bin
    for step in range(_FOLD_BINS):
        candidate = (peak_bin - step) % _FOLD_BINS
        if profile[candidate] <= threshold:
            attack_bin = candidate
            break
    return float(attack_bin) / _FOLD_BINS * ibi, lock


def _znorm(values: np.ndarray) -> np.ndarray:
    """Z-Normalisierung mit Guard gegen Null-Varianz."""
    std = float(np.std(values))
    if std < 1e-9:
        return np.zeros_like(values)
    return (values - float(np.mean(values))) / std


def estimate_first_downbeat(
    y: np.ndarray, sr: int, bpm: float
) -> tuple[float, float]:
    """
    Schaetzt den Zeitpunkt der ersten "1" (Downbeat) und eine Konfidenz.

    Args:
        y: Audio (mono)
        sr: Sample-Rate
        bpm: bekannte BPM (Prior fuers Beat-Tracking)

    Returns:
        (first_downbeat_seconds, confidence 0-1).
        (0.0, 0.0) bei Fehler/zu wenig Material — Verhalten wie ohne Anker.
    """
    if y is None or bpm <= 0 or len(y) < sr * 8:
        return 0.0, 0.0

    try:
        _, beat_frames = librosa.beat.beat_track(
            y=y, sr=sr, hop_length=HOP_LENGTH, start_bpm=bpm, trim=False
        )
        beat_frames = np.atleast_1d(beat_frames)
        if beat_frames.size < _MIN_BEATS:
            return 0.0, 0.0
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sr, hop_length=HOP_LENGTH
        )

        # AUDIT-FIX D-02 (2026-08-14): Tempo-Konsistenz-Gate.
        # Das Phase-Voting laeuft ueber `beat_index % 4` des librosa-Rasters,
        # das Ergebnis wird aber als Phase auf dem Takt-Gitter interpretiert,
        # das ALLE Konsumenten aus `bpm` aufbauen (dj_brain, transition_renderer,
        # models.quantize_to_grid: seconds_per_bar = METER * 60/bpm).
        # Trackt librosa ein anderes Tempo — an echtem Material gemessen bei
        # 11 von 34 Tracks das 3:2-Verhaeltnis —, dann zaehlt `% 4` Takte einer
        # FREMDEN Metrik und die gelieferte Phase ist auf dem Zielgitter
        # bedeutungslos. Ein selbstbewusst falscher Anker ist schlechter als
        # keiner: hier gilt der dokumentierte Vertrag (0.0, 0.0) = "kein Anker".
        grid_ibi = float(
            (beat_times[-1] - beat_times[0]) / (beat_times.size - 1)
        )
        if not _grid_is_commensurate(grid_ibi, 60.0 / bpm):
            logger.debug(
                f"Downbeat verworfen: Beat-Raster {60.0 / grid_ibi:.1f} BPM "
                f"ist inkommensurabel zu bpm={bpm:.1f}"
            )
            return 0.0, 0.0

        beat_samples = (beat_times * sr).astype(int)

        # --- Feature-Kurven (frame-basiert) ---
        # Bass-Onsets: Mel-Spektrum auf <= 160 Hz beschraenkt (Kick/Sub)
        bass_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=HOP_LENGTH, fmax=160, n_mels=16
        )
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP_LENGTH)

        n_beats = len(beat_times)
        bass_score = np.zeros(n_beats)
        nov_score = np.zeros(n_beats)
        loud_score = np.zeros(n_beats)

        for i in range(n_beats):
            f = int(beat_frames[i])
            # Bass-Onset am Beat (kleines Fenster gegen Frame-Jitter)
            lo, hi = max(0, f - 1), min(len(bass_env), f + 2)
            if hi > lo:
                bass_score[i] = float(np.max(bass_env[lo:hi]))

            # Chroma-Novelty: Cosinus-Distanz zwischen dem Beat-Fenster
            # davor und danach (Harmoniewechsel auf der 1)
            f_next = int(beat_frames[i + 1]) if i + 1 < n_beats else chroma.shape[1]
            f_prev = int(beat_frames[i - 1]) if i > 0 else 0
            before = chroma[:, f_prev:f]
            after = chroma[:, f:f_next]
            if before.shape[1] > 0 and after.shape[1] > 0:
                b = before.mean(axis=1)
                a = after.mean(axis=1)
                nb, na = np.linalg.norm(b), np.linalg.norm(a)
                if nb > 1e-9 and na > 1e-9:
                    nov_score[i] = 1.0 - float(np.dot(b, a) / (nb * na))

            # Loudness des Beat-Fensters
            s_end = beat_samples[i + 1] if i + 1 < n_beats else len(y)
            seg = y[beat_samples[i]:s_end]
            if seg.size:
                loud_score[i] = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))

        # --- Trim: leise Beats (Intro/Breakdown) nicht werten ---
        loud_max = float(np.max(loud_score))
        if loud_max < 1e-9:
            return 0.0, 0.0
        valid = loud_score >= loud_max * _TRIM_RATIO
        if int(np.sum(valid)) < _MIN_BEATS:
            return 0.0, 0.0

        # Loudness-AKZENT: relativ zum lokalen Umfeld (nicht absolute Lautheit)
        # AUDIT-FIX N11 (2026-07-24): mode="same" behandelt Werte ausserhalb
        # des Arrays als 0, teilte aber weiter durch 5 — die Raender bekamen
        # dadurch einen kuenstlich ueberhoehten Akzent, der das Phase-Voting
        # systematisch zugunsten der ersten Beats verzerrte. Jetzt: durch die
        # tatsaechliche Fensterbreite pro Position normieren.
        kernel = np.ones(5)
        window_counts = np.convolve(np.ones_like(loud_score), kernel, mode="same")
        local_avg = np.convolve(loud_score, kernel, mode="same") / np.maximum(
            window_counts, 1.0
        )
        accent = loud_score - local_avg

        z_bass = _znorm(bass_score[valid])
        z_nov = _znorm(nov_score[valid])
        z_accent = _znorm(accent[valid])
        phases = (np.arange(n_beats) % 4)[valid]

        # --- Phase-Voting ---
        votes = np.zeros(4)
        combined = (
            _WEIGHTS[0] * z_bass + _WEIGHTS[1] * z_nov + _WEIGHTS[2] * z_accent
        )
        for p in range(4):
            mask = phases == p
            if np.any(mask):
                votes[p] = float(np.sum(combined[mask]))

        best_phase = int(np.argmax(votes))
        # AUDIT-FIX D-03 (2026-08-14): ehrliche 0..1-Skala statt roher Margin
        # (analytisch auf 2/3 gedeckelt, siehe _bar_phase_confidence).
        bar_confidence = _bar_phase_confidence(votes)

        # AUDIT-FIX N10 (2026-07-24): Der Anker wurde vorher direkt aus einem
        # der ersten vier Beats gelesen (beat_times[best_phase]) — genau dem
        # Bereich, den das Trim-Kriterium als zu leise vom Voting ausschliesst
        # (Intro/Stille, maximaler Beat-Tracking-Jitter). Der Fehler propagierte
        # in JEDE Quantisierung des Projekts. Jetzt: aus allen VALIDEN Beats
        # der Gewinner-Phase auf t0 zurueckrechnen.
        #
        # AUDIT-FIX D-01 (2026-08-14, Drift): Die Rueckrechnung lief vorher
        # linear ueber `beat_times - (idx // 4) * 4 * median(diff(beat_times))`.
        # Beide Groessen darin sind fehlerhaft:
        #   1. beat_times liegen auf dem HOP-Raster (1024/22050 = 46,4 ms).
        #      median(diff(...)) rastet damit auf ein GANZZAHLIGES Vielfaches
        #      der Hop-Dauer ein. Bei 140 BPM ist der echte Beat-Abstand
        #      9,22 Hops, der Median aber 9 Hops — 2,5 % zu kurz.
        #   2. Der lineare Term (idx // 4) * bar_len multipliziert diesen Bias
        #      mit der Taktnummer, der Fehler waechst also UNBEGRENZT mit der
        #      Tracklaenge. Gemessen an einem perfekten Klick-Track (140 BPM,
        #      64 Takte) landete der "erste" Downbeat bei 1,30 s statt 0,05 s;
        #      im Produktivcache lagen 13 von 17 selbst geschaetzten Ankern
        #      ausserhalb des ersten Takts, der Extremwert bei 55,6 s
        #      (= 31,5 Takte) — als Untergrenze fuer Mix-In (dj_brain R3)
        #      direkt schaedlich.
        # Fix: (a) Die Taktlaenge kommt aus dem validierten Tempo, nicht aus
        # dem hop-gerasterten Beat-Abstand — nur so liegt der Anker auf
        # DEMSELBEN Gitter, das alle Konsumenten aus bpm aufbauen.
        # (b) Statt linearer Rueckrechnung ein ZIRKULAERER Mittelwert der
        # Beat-Zeiten modulo Taktlaenge: driftfrei und per Konstruktion
        # in [0, bar_len) — ein "erster Downbeat" kann nie mehr hinter dem
        # ersten Takt liegen.
        ibi = 60.0 / bpm
        bar_len = ibi * METER
        idx = np.arange(n_beats)
        phase_mask = valid & ((idx % 4) == best_phase)
        first_downbeat = float(beat_times[best_phase]) % bar_len
        if int(np.sum(phase_mask)) >= 2:
            angles = 2.0 * np.pi * np.mod(beat_times[phase_mask], bar_len) / bar_len
            mean_angle = np.arctan2(
                float(np.mean(np.sin(angles))), float(np.mean(np.cos(angles)))
            )
            first_downbeat = (
                float(np.mod(mean_angle, 2.0 * np.pi)) * bar_len / (2.0 * np.pi)
            )

        # Sub-Beat-Feinausrichtung (AUDIT-FIX D-03): Die Taktphase kommt aus
        # dem Voting, die PRAEZISE Lage im Beat aus der beat-synchronen
        # Faltung. Der frueher hier stehende Snap auf den staerksten
        # Bass-Onset-Frame war auf das 46-ms-Hop-Raster gerastert und
        # systematisch ~116 ms zu spaet (Messung an 35 ANLZ-Referenzen).
        beat_phase, fold_lock = _beat_phase_from_fold(y, sr, ibi)
        if beat_phase is None:
            # Ohne belastbare Sub-Beat-Phase gibt es keinen Anker, den ein
            # Konsument ausrichten koennte — dokumentierter Vertrag.
            logger.debug("Downbeat verworfen: keine beat-synchrone Struktur")
            return 0.0, 0.0
        # Denselben Takt behalten, nur die Beat-Phase korrigieren.
        first_downbeat = beat_phase + round((first_downbeat - beat_phase) / ibi) * ibi
        first_downbeat = float(np.mod(first_downbeat, bar_len))

        # Die Konfidenz ist die SCHWAECHERE der beiden Saeulen: eine klare
        # Taktphase nuetzt nichts ohne beat-synchrone Struktur und umgekehrt.
        # An echtem Material trennt erst diese Konjunktion die Ausreisser —
        # Tracks mit hohem fold_lock, aber unentschiedenem Voting (gemessen:
        # 153 ms und 188 ms Phasenfehler) faellt nur die Margin.
        confidence = min(bar_confidence, fold_lock)
        confidence = float(
            np.clip(confidence, 0.0, SELF_ESTIMATE_CONFIDENCE_MAX)
        )

        logger.debug(
            f"Downbeat: Phase {best_phase}, t={first_downbeat:.3f}s, "
            f"Konfidenz {confidence:.2f} (Takt {bar_confidence:.2f} / "
            f"Faltung {fold_lock:.2f})"
        )
        return round(first_downbeat, 4), round(confidence, 3)

    except Exception as e:
        logger.warning(f"Downbeat-Erkennung fehlgeschlagen: {e}")
        return 0.0, 0.0


# Kalibrierungs-Basis von PHRASE_CONFIDENCE_MIN: die Schwelle wurde fuer
# 8-Bar-Phrasen gewaehlt (haeufigster Fall, Techno/House)
_PHRASE_UNIT_REFERENCE = 8

# AUDIT-FIX P-01 (2026-08-14): Mindest-Korrelation des Phasen-Votings mit sich
# selbst, um eine HALBIERTE Phrasen-Periode als gemessen zu akzeptieren.
# Gemessen an 35 echten AIFFs (D:/beatport_tracks_2025-08) gegen eine
# unabhaengige Referenz (Bass-Energie 20-150 Hz, groesste Bar-zu-Bar-Spruenge;
# Periode 8 <=> zirkulare Konzentration mod 8 hoch, mod 16 niedrig):
#   18 Tracks sind eindeutig entscheidbar, 9 mit Periode 8, 9 mit Periode 16.
#   Hoechste Selbstkorrelation eines echten 16-Bar-Tracks: 0.60
#   Niedrigste der erkannten 8-Bar-Tracks:                 0.78
# Die Luecke 0.60 .. 0.78 ist eindeutig; 0.70 liegt darin (geometrisch mittig
# 0.684). Bei 0.70 werden 6 von 9 Periode-8-Tracks erkannt und KEIN
# Periode-16-Track faelschlich gefaltet.
PHRASE_SUBPERIOD_MIN_CORRELATION = 0.70


def _fold_votes_to_measured_period(votes: np.ndarray) -> np.ndarray:
    """AUDIT-FIX P-01 (2026-08-14): faltet das Voting auf die GEMESSENE Periode.

    ``phrase_unit`` ist eine Genre-ANNAHME (Psytrance/Trance: 16 Bars), keine
    Messung. Wiederholt sich der Track in Wahrheit alle 8 Bars, dann sammeln
    im 16-Bin-Voting ZWEI Bins — p und p+8 — dieselbe echte Phrasengrenze. Die
    Margin zwischen Platz 1 und 2 bricht damit genau dann zusammen, wenn die
    Struktur besonders klar ist. Gemessen an 35 echten Tracks:

      Track                     Konf. P=16   Konf. P=8   Phasenfehler P=8
      Dragonfruit (E-Clip)          0.012       0.416       0 Bars
      Flowstate                     0.042       0.439       0 Bars
      Night Sky                     0.045       0.298       0 Bars
      Solarians                     0.279       0.478       0 Bars
      Shores of the Subconscious    0.314       0.538       0 Bars

    Musikalisch ist die verbleibende Zweideutigkeit dabei folgenlos: liegt die
    echte Periode bei 8 Bars, sind BEIDE Kandidaten (p und p+8) echte
    Phrasengrenzen. Ein 16-Bar-Gitter, das auf einer davon verankert ist,
    trifft ausschliesslich echte 8-Bar-Grenzen. Deshalb darf hier gefaltet
    werden — anders als bei einem Track mit echter 16-Bar-Periode, wo die
    falsche Haelfte mitten in der Phrase landen wuerde.

    Kriterium ist die zirkulare Selbstkorrelation der Stimmen bei Lag P/2 —
    eine Messung AM TRACK, unabhaengig von der Margin. Deshalb inflationiert
    sie die Falsch-Positiv-Rate des Gates praktisch nicht (Monte-Carlo ueber
    4000 Rauschlaeufe je Konfiguration: 3.62 % -> 3.67 % bei iid-Rauschen,
    2.52 % -> 2.58 % bei AR(1)-Rauschen, n_bars = 210).

    Die Faltung ist exakt: ``votes[:h] + votes[h:]`` ist dieselbe Summe, die
    ein Voting mit P/2 Bins direkt berechnet haette (die Bars ``i % P == p``
    und ``i % P == p + h`` sind genau die Bars ``i % h == p``).
    """
    votes = np.asarray(votes, dtype=float)
    while votes.size >= 2 * _PHRASE_UNIT_REFERENCE and votes.size % 2 == 0:
        energy = float(np.dot(votes, votes))
        if energy < 1e-12:
            break
        half = votes.size // 2
        correlation = float(np.dot(votes, np.roll(votes, half))) / energy
        if correlation < PHRASE_SUBPERIOD_MIN_CORRELATION:
            break
        votes = votes[:half] + votes[half:]
    return votes


def _vote_margin_confidence(votes: np.ndarray) -> float:
    """AUDIT-FIX N-03 (2026-07-26): phrase_unit-invariante Voting-Konfidenz.

    Die rohe Margin-Konfidenz (v1 - v2) / sum(|votes|) faellt systematisch
    mit der Bin-Anzahl P: die Gewinner-Stimme buendelt nur noch n_bars/P
    Bars, waehrend die Rauschsumme im Nenner mit P waechst.
    PHRASE_CONFIDENCE_MIN wurde bei phrase_unit=8 kalibriert — bei
    16-Bar-Genres (Psytrance/Trance, Kern-Genres!) erreichte selbst starke
    2-Sigma-Struktur nur ~49 % Pass-Rate; die Phrasen-Erkennung war dort
    faktisch abgeschaltet.

    Fix: Konfidenz auf die 8er-Referenz normieren (Faktor P/8). Bei P=8 ist
    das exakt die alte, kalibrierte Groesse (kein Verhaltens-Drift, Noise-
    Rejection bleibt unveraendert streng); bei P=16/32 wird der strukturelle
    Nachteil der duenner besetzten Bins kompensiert. Feinkalibrierung an
    gelabelten Tracks: Plan 3.4.
    """
    p = int(votes.size)
    if p < 2:
        return 0.0
    order = np.argsort(votes)[::-1]
    margin = float(votes[order[0]] - votes[order[1]])
    spread = float(np.sum(np.abs(votes)))
    if spread < 1e-9:
        return 0.0
    scale = p / float(_PHRASE_UNIT_REFERENCE)
    return float(np.clip((margin / spread) * scale, 0.0, 1.0))


def estimate_first_phrase(
    y: np.ndarray,
    sr: int,
    bpm: float,
    first_downbeat: float,
    phrase_unit: int = 8,
) -> tuple[float, float]:
    """AUDIT-FEATURE A1 (2026-07-26): Schaetzt die PHRASEN-Phase eines Tracks.

    estimate_first_downbeat liefert nur die Takt-Phase (welcher Beat ist die
    "1"). Ein DJ denkt aber in Phrasen (8/16 Bars): Mix-Punkte, die auf einem
    Phrasengitter mit falscher Phrasen-Phase liegen, koennen bis zu
    phrase_unit-1 Bars neben der echten Phrasengrenze sitzen — hoerbar falsch.

    Erweiterung der Voting-Idee von estimate_first_downbeat auf Bar-Ebene:
    In EDM beginnen Phrasen dort, wo Elemente ein-/aussetzen — Kick-Einsatz,
    Filter-Oeffnung, harmonischer Wechsel, Energie-Sprung. Pro Bar-Grenze
    werden drei z-normierte Indizien berechnet und ueber bar_index %
    phrase_unit abgestimmt.

    Args:
        y: Audio (mono), idealerweise der Analyse-Head (>= ~2 Phrasen).
        sr: Samplerate.
        bpm: Tempo (validiert, > 0).
        first_downbeat: Takt-Anker in Sekunden (Basis des Bar-Rasters).
        phrase_unit: Phrasenlaenge in Bars (Genre-ANNAHME: 8, 16 oder 32).
            Obergrenze der Voting-Aufloesung; zeigt der Track eine halbierte
            Periode, wird darauf gefaltet (P-01, _fold_votes_to_measured_period).

    Returns:
        (first_phrase_seconds, confidence 0..1). first_phrase liegt auf dem
        Bar-Raster (first_downbeat + k * bar_len) innerhalb der ersten Phrase.
        (-1.0, 0.0) wenn keine belastbare Schaetzung moeglich ist.
        AUDIT-FIX R4 (2026-07-26): Sentinel ist -1.0 statt 0.0 — eine Phase
        von exakt 0.0 (Track startet auf der Phrasengrenze) ist GUELTIG und
        wurde vorher vom `> 0.0`-Gate der Aufrufer verworfen.
    """
    try:
        if bpm <= 0 or phrase_unit <= 1 or y is None or len(y) == 0:
            return -1.0, 0.0

        bar_len = (60.0 / bpm) * METER
        duration = len(y) / float(sr)
        # Anker in den Bereich [0, bar_len) falten, damit auch Bars vor dem
        # (ggf. spaeten) first_downbeat gezaehlt werden
        anchor = float(first_downbeat) % bar_len if bar_len > 0 else 0.0
        n_bars = int((duration - anchor) / bar_len)
        # Mindestens 2 volle Phrasen, sonst ist das Voting Rauschen
        if n_bars < phrase_unit * 2:
            return -1.0, 0.0

        bar_times = anchor + np.arange(n_bars) * bar_len

        # --- Feature-Grundlagen (einmal berechnen) ---
        bass_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=HOP_LENGTH, fmax=160, n_mels=16
        )
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP_LENGTH)
        rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
        bar_frames = librosa.time_to_frames(
            bar_times, sr=sr, hop_length=HOP_LENGTH
        ).astype(int)
        n_frames = min(len(bass_env), chroma.shape[1], len(rms))

        bass_score = np.zeros(n_bars)
        nov_score = np.zeros(n_bars)
        rms_delta = np.zeros(n_bars)

        for i in range(n_bars):
            f = int(bar_frames[i])
            if f < 0 or f >= n_frames:
                continue
            # Bass-Onset direkt an der Bar-Grenze (Kick-/Bass-Einsatz)
            lo = max(0, f - 1)
            hi = min(n_frames, f + 3)
            bass_score[i] = float(np.max(bass_env[lo:hi]))

            # Chroma-Novelty: Harmoniewechsel ueber die Bar-Grenze
            f_prev = int(bar_frames[i - 1]) if i > 0 else 0
            f_next = int(bar_frames[i + 1]) if i + 1 < n_bars else n_frames
            f_prev = max(0, min(f_prev, n_frames))
            f_next = max(f, min(f_next, n_frames))
            before = chroma[:, f_prev:f]
            after = chroma[:, f:f_next]
            if before.shape[1] > 0 and after.shape[1] > 0:
                b = before.mean(axis=1)
                a = after.mean(axis=1)
                nb, na = np.linalg.norm(b), np.linalg.norm(a)
                if nb > 1e-9 and na > 1e-9:
                    nov_score[i] = 1.0 - float(np.dot(b, a) / (nb * na))

            # RMS-Sprung: Energie der Bar vs. Vorgaenger-Bar
            if i > 0:
                cur = rms[f:min(n_frames, int(bar_frames[i + 1]) if i + 1 < n_bars else n_frames)]
                prev = rms[f_prev:f]
                if cur.size and prev.size:
                    rms_delta[i] = float(np.mean(cur) - np.mean(prev))

        z_bass = _znorm(bass_score)
        z_nov = _znorm(nov_score)
        # Nur POSITIVE Energie-Spruenge zaehlen (Element-Einsatz, nicht -Ausstieg)
        z_rms = _znorm(np.maximum(rms_delta, 0.0))

        combined = 1.0 * z_bass + 1.0 * z_nov + 0.75 * z_rms

        # --- Phase-Voting ueber bar_index % phrase_unit ---
        votes = np.zeros(phrase_unit)
        idx = np.arange(n_bars)
        for p in range(phrase_unit):
            mask = (idx % phrase_unit) == p
            if np.any(mask):
                votes[p] = float(np.sum(combined[mask]))

        # AUDIT-FIX P-01 (2026-08-14): auf die GEMESSENE Periode falten, bevor
        # bewertet wird — der Genre-Prior phrase_unit ist eine Annahme.
        votes = _fold_votes_to_measured_period(votes)

        best_phase = int(np.argmax(votes))
        # AUDIT-FIX N-03 (2026-07-26): phrase_unit-invariante Konfidenz —
        # Margin/Spread auf die 8-Bar-Referenz normiert (Faktor P/8), sonst
        # skaliert die Konfidenz mit der Bin-Anzahl und 16-Bar-Genres
        # fallen systematisch durch das PHRASE_CONFIDENCE_MIN-Gate.
        confidence = _vote_margin_confidence(votes)

        first_phrase = float(anchor + best_phase * bar_len)

        logger.debug(
            f"Phrasen-Phase: Bar {best_phase}/{votes.size} "
            f"(Genre-Annahme {phrase_unit}), t={first_phrase:.3f}s, "
            f"Konfidenz {confidence:.3f}"
        )
        return round(first_phrase, 4), round(confidence, 3)

    except Exception as e:
        logger.warning(f"Phrasen-Phase-Erkennung fehlgeschlagen: {e}")
        return -1.0, 0.0
