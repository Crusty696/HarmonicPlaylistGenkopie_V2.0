"""
hpg_core/transition_renderer.py

Rendert einen Transition-Preview-Clip als WAV-Datei.
Verwendet: scipy.signal (EQ-Filter) + soundfile (I/O) + numpy (Mix)
Keine neuen pip-Abhaengigkeiten noetig — scipy und soundfile sind bereits
implizite Abhaengigkeiten von librosa.

Aufbau eines gerenderten Clips:
    [pre_roll]  |  [crossfade]  |  [post_roll]
    Nur Track A    Beide gemischt  Nur Track B
"""

import os
import logging
import tempfile
from dataclasses import dataclass

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt
import librosa

from .config import MAX_TRANSITION_OVERLAP_SECONDS, METER
from .downbeat import DOWNBEAT_RELIABLE_MIN, REFERENCE_BEATGRID_CONFIDENCE

logger = logging.getLogger(__name__)

# EQ-Cutoffs der Transition-Typen (L2-Fix: zentral statt hartkodiert im Code)
FILTER_RIDE_HP_HZ = 800.0    # Hochpass-Sweep beim Ausblenden (filter_ride)
SMOOTH_BLEND_LP_HZ = 300.0   # Tiefpass auf Track A (smooth_blend)
BREAKDOWN_HP_HZ = 250.0      # Bass-Kill auf Track A (breakdown_bridge)
FILTER_RAMP_SECONDS = 0.05   # Kurze Rampe gegen harte Filter-Schalter


# ---------------------------------------------------------------------------
# Daten-Klassen
# ---------------------------------------------------------------------------

@dataclass
class EqCrossfadeConfig:
    """Parameter fuer den EQ-Crossfade."""
    cf_frames: int
    sr: int
    bass_cutoff_hz: float
    transition_type: str
    bpm_a: float = 120.0  # AUDIT-FIX R-04: fuer beat-synchrone echo_out-Delays


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
    # Lautheits-Normalisierung (Research 2026-02-28: verhindert Lautheitssprunge)
    normalize_rms: bool = True          # RMS-Normalisierung vor Crossfade
    normalize_target_db: float = -14.0  # Ziel-Pegel in dBRMS (EBU R128: -14 LUFS)
    use_compressor: bool = False        # Optionaler pedalboard Compressor (experimentell)
    # AUDIT-FIX R-07 (2026-07-26): echte gemessene Track-LUFS (pyloudnorm,
    # BS.1770) aus der Analyse — praeziser als der ungewichtete RMS-Messwert
    # des Renderers. 0.0 = nicht gemessen (Sentinel) -> RMS-Fallback.
    lufs_a: float = 0.0
    lufs_b: float = 0.0

    @classmethod
    def from_plan(cls, plan, from_track, to_track):
        """Erzeugt eine Render-Spezifikation ohne zweite Timing-Berechnung."""
        return cls(
            track_a_path=from_track.filePath,
            track_b_path=to_track.filePath,
            mix_out_sec=plan.mix_out_a,
            mix_in_sec=plan.mix_in_b,
            crossfade_sec=plan.overlap,
            transition_type=plan.transition_type,
            target_sr=plan.target_sr,
            bpm_a=float(from_track.bpm or 120.0),
            bpm_b=float(to_track.bpm or 120.0),
            first_downbeat_a=float(getattr(from_track, "first_downbeat", 0.0) or 0.0),
            first_downbeat_b=float(getattr(to_track, "first_downbeat", 0.0) or 0.0),
            downbeat_reliable_a=(
                getattr(from_track, "downbeat_confidence", 0.0)
                >= DOWNBEAT_RELIABLE_MIN
            ),
            downbeat_reliable_b=(
                getattr(to_track, "downbeat_confidence", 0.0)
                >= DOWNBEAT_RELIABLE_MIN
            ),
            bar_phase_reliable_a=(
                getattr(from_track, "downbeat_confidence", 0.0)
                == REFERENCE_BEATGRID_CONFIDENCE
            ),
            bar_phase_reliable_b=(
                getattr(to_track, "downbeat_confidence", 0.0)
                == REFERENCE_BEATGRID_CONFIDENCE
            ),
            lufs_a=float(getattr(from_track, "lufs", 0.0) or 0.0),
            lufs_b=float(getattr(to_track, "lufs", 0.0) or 0.0),
        )


# ---------------------------------------------------------------------------
# Oeffentliche Hauptfunktion
# ---------------------------------------------------------------------------

def render_transition_clip(spec: TransitionClipSpec, output_path: str) -> str:
    """
    Rendert den Transition-Clip und speichert ihn als 16-bit PCM WAV.

    Lade-Strategie:
      Track A: start = mix_out_sec - pre_roll_sec,  dauer = pre_roll_sec + crossfade_sec
      Track B: start = mix_in_sec,                   dauer = crossfade_sec + post_roll_sec

    Gibt den output_path zurueck.
    """
    sr = spec.target_sr
    # Sicherheitslimit: max 64s Crossfade -- Trance/Progressive blenden 32-64 Bars
    # (~55-110s bei 138 BPM), 32s kappte die Preview systematisch vor dem Mix-Out.
    # Audit-Fix 2026-07-21: untere Grenze 0 erzwingen. Ein degenerierter Mixplan
    # (overlap <= 0, aus plan.overlap ungeprueft uebernommen) ergab sonst negative
    # cf_frames -> np.linspace(..., negativ) / sosfiltfilt-Crash statt sauberem Clip.
    cf_sec = min(max(0.0, spec.crossfade_sec), MAX_TRANSITION_OVERLAP_SECONDS)
    pre_roll = max(0.0, spec.pre_roll_sec)
    post_roll = max(0.0, spec.post_roll_sec)

    # Segmente berechnen
    a_start = max(0.0, spec.mix_out_sec - pre_roll)
    a_dur   = pre_roll + cf_sec
    # AUDIT-FIX N-02 (2026-07-26): Track B mit 1 Takt VORLAUF laden. Das
    # C1-Bar-Alignment verschiebt B um bis zu einen Takt — ohne Vorlauf wurden
    # dabei bis zu 2 Beats vom ANFANG von seg_b verworfen: genau der Phrasen-/
    # Drop-Einsatz, auf den die Analyse den Mix-In gelegt hat. Mit Vorlauf
    # schneidet der Alignment-Cut nur in den Vorlauf, nie in den Einsatz.
    bar_lead_sec = (60.0 / spec.bpm_b) * METER if spec.bpm_b > 0 else 0.0
    b_start = max(0.0, spec.mix_in_sec - bar_lead_sec)
    b_lead_sec = spec.mix_in_sec - b_start  # tatsaechlich geladener Vorlauf
    b_dur   = b_lead_sec + cf_sec + post_roll

    # Audio laden (beide Segmente)
    seg_a = _load_segment(spec.track_a_path, a_start, a_dur, sr)
    seg_b = _load_segment(spec.track_b_path, b_start, b_dur, sr)

    # Dynamic BPM Time-Stretching (echter DJ Pitchfader!)
    # Wenn Track B ein anderes Tempo als Track A besitzt, passen wir sein Tempo an Track A an.
    applied_stretch_rate = 1.0  # fuer die Downbeat-Phasen-Umrechnung unten
    if spec.bpm_a > 0 and spec.bpm_b > 0 and abs(spec.bpm_a - spec.bpm_b) > 0.05:
        target_bpm_b = spec.bpm_b
        
        # Half/Double-Erkennung relativ zum Zieltempo: DJ-Pitchfader-Praxis
        # erlaubt ~3-4% Anpassung, absolute 10-BPM-Fenster triggerten falsch
        half_double_tolerance = spec.bpm_a * 0.04

        # Check fuer Halftime-Switch (BPM_B ist ca. die Haelfte von BPM_A)
        if abs(spec.bpm_b * 2.0 - spec.bpm_a) < half_double_tolerance:
            target_bpm_b = spec.bpm_b * 2.0
            logger.info(f"Halftime-Switch erkannt fuer Track B: Virtuelle BPM verdoppelt von {spec.bpm_b:.1f} auf {target_bpm_b:.1f}")
        # Check fuer Doubletime-Switch (BPM_B ist ca. das Doppelte von BPM_A)
        elif abs(spec.bpm_b / 2.0 - spec.bpm_a) < half_double_tolerance:
            target_bpm_b = spec.bpm_b / 2.0
            logger.info(f"Doubletime-Switch erkannt fuer Track B: Virtuelle BPM halbiert von {spec.bpm_b:.1f} auf {target_bpm_b:.1f}")

        # AUDIT-FIX R-01 (2026-07-24): Rate war invertiert.
        # librosa.effects.time_stretch: rate > 1.0 = SCHNELLER, rate < 1.0 = LANGSAMER.
        # Track B (target_bpm_b) soll auf das Tempo von Track A (bpm_a) gebracht werden:
        # rate = bpm_a / target_bpm_b  (B langsamer als A -> rate > 1 -> B wird beschleunigt).
        # Die Phasen-Umrechnung in known_b (phase_b / applied_stretch_rate) folgt bereits
        # dieser librosa-Semantik (t_out = t_in / rate) und bleibt unveraendert.
        raw_rate = float(spec.bpm_a / target_bpm_b)

        # AUDIT-FIX C4 (2026-07-26): Clamp von +-15% auf +-8% gesenkt.
        # DJ-realistisch sind +-6-8% Pitchfader; +-15% ohne Key-Lock waren
        # ~2,4 Halbtoene Verstimmung — das Camelot-Scoring stimmt dann nicht
        # mehr mit dem Gehoerten ueberein. (Phase-Vocoder ohne Key-Lock:
        # 8% ~ 1,3 Halbtoene, an der Grenze des Tolerablen fuer Previews.)
        rate = max(0.92, min(1.08, raw_rate))
        # H3-Fix: geclampter Stretch bedeutet, dass der Preview NICHT
        # tempo-synchron laeuft — das muss sichtbar geloggt werden
        if abs(rate - raw_rate) > 1e-6:
            logger.warning(
                f"Time-Stretch geclamped (benoetigt Rate {raw_rate:.3f}, erlaubt 0.92-1.08): "
                f"Preview laeuft NICHT tempo-synchron ({spec.bpm_b:.1f} vs {spec.bpm_a:.1f} BPM)"
            )

        try:
            # librosa.effects.time_stretch arbeitet auf der LETZTEN Achse.
            # seg_b ist (frames, 2) → transponieren auf (2, frames), stretchen,
            # zurueck transponieren. (Das frueher genutzte axis=-Kwarg existiert
            # in dieser librosa-Version nicht und wuerde an stft() durchgereicht.)
            seg_b = librosa.effects.time_stretch(seg_b.T, rate=rate).T
            applied_stretch_rate = rate
            logger.info(f"BPM Time-Stretching angewendet: Track B ({spec.bpm_b:.1f} BPM -> {target_bpm_b:.1f} BPM) auf Track A ({spec.bpm_a:.1f} BPM) angepasst (Rate={rate:.4f})")
        except Exception as ts_err:
            logger.warning(f"BPM Time-Stretching fehlgeschlagen: {ts_err}")

    # Lautheits-Normalisierung: absolute Pegel ausschliesslich aus dem
    # tatsaechlichen Preview-Segment bestimmen.
    # AUDIT-FIX R-07 (2026-07-26): Wenn echte Track-LUFS aus der Analyse
    # vorliegen (pyloudnorm, K-gewichtet nach BS.1770), wird der Gain direkt
    # daraus berechnet — der ungewichtete RMS des Renderers unterschied sich
    # je nach Spektrum um 2-4 LUFS (basslastiger Techno vs. heller Trance),
    # genau der Lautheitssprung, den das Feature verhindern soll.
    if spec.normalize_rms:
        # -14 dB ist ein RMS-Ziel, kein LUFS-Ziel. Die gemessenen LUFS duerfen
        # danach nur noch den relativen A/B-Unterschied korrigieren; so bleibt
        # die Preview-Semantik unabhaengig davon, ob Track-LUFS vorhanden ist.
        seg_a = _rms_normalize(seg_a, spec.normalize_target_db)
        seg_b = _rms_normalize(seg_b, spec.normalize_target_db)
        # AUDIT-FIX 2026-08-14: Hier stand vorher spec.lufs_a/spec.lufs_b — die
        # Lautheit der GANZEN Tracks, gemessen VOR dieser Normalisierung. Da
        # _rms_normalize die beiden Segmente aber bereits angeglichen hat
        # (gemessen: Restdifferenz 0.62 dB), zog das Delta sie anschliessend
        # wieder auseinander statt sie zusammenzufuehren: 6.62 dB Ueber-
        # korrektur, im fertigen Clip 9.83 dB Pegelsprung zwischen den Tracks.
        # Korrigiert wird jetzt die RESTdifferenz der normalisierten Segmente.
        # spec.lufs_a/lufs_b bleiben als Analyse-Metadaten erhalten (dj_brain
        # nutzt sie fuer gain_advice), steuern hier aber nichts mehr.
        seg_a, seg_b = _apply_lufs_delta(
            seg_a,
            seg_b,
            _measure_segment_loudness(seg_a, sr),
            _measure_segment_loudness(seg_b, sr)
        )

    # Soll-Laengen in Frames
    cf_frames   = int(cf_sec * sr)
    # C1-Fix: pre_frames muss die TATSAECHLICH geladene Vorlaufzeit abbilden.
    # Bei mix_out_sec < pre_roll wird a_start (Zeile 126) auf 0.0 geklemmt — das
    # Segment beginnt dann bei t=0 statt pre_roll Sekunden vor dem Mix-Out. Nutzt
    # man hier weiter das ungeklemmte spec.pre_roll_sec, greift der Crossfade
    # (seg_a[pre_frames:]) pre_roll Sekunden hinter dem echten Mix-Out — bei kurzen
    # Tracks komplett im Null-Padding (stilles/falsches Audio, kein Crash).
    pre_frames  = int(round(max(0.0, spec.mix_out_sec - a_start) * sr))
    post_frames = int(post_roll * sr)

    # H2-Fix: Beat-Phase-Alignment — Track B wird um den Phasenversatz
    # (< 1 Beat) verschoben, damit die Kicks im Crossfade uebereinander liegen.
    # Downbeat-Feature 2026-07-17: sind die ersten Downbeats beider Tracks
    # bekannt, wird der Versatz EXAKT aus den Beatgrids berechnet statt zur
    # Renderzeit geschaetzt (schneller und praeziser).
    # AUDIT-FIX N-02 (2026-07-26): der geladene Vorlauf (b_lead_sec) skaliert
    # beim Time-Stretch mit 1/rate; das Alignment konsumiert ihn per Cut.
    b_lead_frames = int(round(b_lead_sec / applied_stretch_rate * sr))
    if spec.bpm_a > 0 and len(seg_a) > pre_frames:
        try:
            known_a = known_b = None
            bar_aligned = False
            if spec.downbeat_reliable_a and spec.downbeat_reliable_b:
                # AUDIT-FIX C1 (2026-07-26): Phase innerhalb des TAKTS (Bar)
                # statt innerhalb des Beats — das Alignment setzt Beat 1 von B
                # auf Beat 1 von A, nicht nur Kick auf Kick.
                # AUDIT-FIX D-03 (2026-08-14): Die Takt-Ebene setzt voraus,
                # dass BEIDE Anker aus einem Referenz-Beatgrid stammen. Die
                # Eigenschaetzung liefert die Beat-Phase praezise, die
                # Takt-Phase aber nur in 10 von 19 gemessenen Faellen richtig
                # — auf ihr zu takten waere eine unbelegte Behauptung.
                bar_aligned = (
                    spec.bar_phase_reliable_a and spec.bar_phase_reliable_b
                )
                bar_sec_a = (60.0 / spec.bpm_a) * METER
                known_a = (spec.first_downbeat_a - spec.mix_out_sec) % bar_sec_a
                bar_sec_b = (
                    (60.0 / spec.bpm_b) * METER if spec.bpm_b > 0 else bar_sec_a
                )
                # N-02: Phase relativ zum SEGMENT-Anfang (b_start, inkl.
                # Vorlauf) — konsistent mit dem Schaetz-Pfad, der die Phase
                # ebenfalls ab Segment-Anfang misst. Ohne Clamp ist das
                # modulo-identisch zur alten Rechnung ab mix_in_sec.
                phase_b = (spec.first_downbeat_b - b_start) % bar_sec_b
                # Track B wurde ggf. gestretcht: Zeitpunkte skalieren mit 1/rate
                known_b = phase_b / applied_stretch_rate
            seg_b = _align_beat_phase(
                seg_a[pre_frames:], seg_b, spec.bpm_a, sr,
                known_first_beat_a=known_a, known_first_beat_b=known_b,
                lead_frames=b_lead_frames, bar_aligned=bar_aligned,
            )
        except Exception as align_err:
            logger.warning(f"Beat-Phase-Alignment fehlgeschlagen: {align_err}")
            # N-02: Vorlauf trotzdem entfernen, sonst laege der Crossfade
            # einen Takt zu frueh im Material von Track B
            seg_b = seg_b[min(b_lead_frames, len(seg_b)):]
    elif b_lead_frames > 0:
        # Kein Alignment moeglich -> Vorlauf verwerfen (altes Verhalten)
        seg_b = seg_b[min(b_lead_frames, len(seg_b)):]

    # Sicherstellen dass Segmente lang genug sind (Null-Padding falls noetig)
    seg_a = _ensure_len(seg_a, pre_frames + cf_frames)
    seg_b = _ensure_len(seg_b, cf_frames + post_frames)

    # Clip zusammenbauen
    part_pre  = seg_a[:pre_frames]             # Nur Track A vor dem Mix
    a_cf      = seg_a[pre_frames:]             # Track A im Crossfade-Bereich
    b_cf      = seg_b[:cf_frames]              # Track B im Crossfade-Bereich

    config = EqCrossfadeConfig(
        cf_frames=cf_frames,
        sr=sr,
        bass_cutoff_hz=spec.bass_cutoff_hz,
        transition_type=spec.transition_type,
        bpm_a=float(spec.bpm_a or 120.0),
    )
    part_cf   = _apply_eq_crossfade(a_cf, b_cf, config)
    part_post = seg_b[cf_frames:]              # Nur Track B nach dem Mix

    # Zusammenfuegen
    mixed = np.concatenate([part_pre, part_cf, part_post], axis=0)

    # Optionaler Compressor (pedalboard) fuer gleichmaessigere Lautheit im Mix
    # Glaettet residuale Schwankungen die RMS-Norm nicht vollstaendig behebt
    if spec.use_compressor:
        mixed = _apply_compressor(mixed, sr)

    # AUDIT-FIX R-03 (2026-07-24): Echter Soft-Limiter mit tanh-Kennlinie statt
    # globaler Peak-Normalisierung. Vorher senkte ein EINZELNER Transient den
    # KOMPLETTEN Clip (Pre-Roll + Crossfade + Post-Roll) linear ab -> die
    # -14-dBRMS-Normalisierung wurde durch einen Sample-Peak zunichte gemacht
    # und A/B-Previews waren nicht mehr lautheitskonsistent. Jetzt: nur die
    # ueberschreitenden Samples weich begrenzen, der Rest bleibt unveraendert.
    if mixed.size:
        mixed = _apply_soft_limiter(mixed)

    # Als 16-bit PCM WAV exportieren
    sf.write(output_path, mixed.astype(np.float32), samplerate=sr, subtype='PCM_16')
    return output_path


def _render_clip_subprocess_wrapper(args):
    """
    Hilfsfunktion zum Rendern eines Transition-Clips in einem separaten Prozess.
    Muss auf Modulebene in DIESEM Modul liegen (nicht in main.py/__main__):
    im PyInstaller-Frozen-Build dispatcht multiprocessing.freeze_support() den
    spawn-Child bereits am Anfang von main.py — die dortigen Modulfunktionen sind
    dann noch nicht definiert, und der Pickle-Lookup ueber __main__ schlaegt fehl
    (AttributeError). Aus hpg_core.transition_renderer laedt der Child sauber
    ohne Qt/Audio-Stack.
    """
    spec, out_path = args
    render_transition_clip(spec, out_path)
    return out_path


def _estimate_first_beat(seg: np.ndarray, sr: int, bpm: float) -> float:
    """Schaetzt den Zeitpunkt (Sekunden) des ersten Beats im Segment (max. 8s Fenster)."""
    mono = seg.mean(axis=1)
    window = mono[: int(min(len(mono), sr * 8))]
    if len(window) < sr:
        return 0.0
    _, beats = librosa.beat.beat_track(y=window, sr=sr, start_bpm=bpm, trim=False)
    beats = np.atleast_1d(beats)
    if beats.size == 0:
        return 0.0
    return float(librosa.frames_to_time(beats[0], sr=sr))


def _align_beat_phase(ref_seg: np.ndarray, seg_b: np.ndarray,
                      bpm: float, sr: int,
                      known_first_beat_a: float | None = None,
                      known_first_beat_b: float | None = None,
                      lead_frames: int = 0,
                      bar_aligned: bool = False) -> np.ndarray:
    """
    Verschiebt seg_b, sodass sein Beat-Raster auf das von ref_seg (Track A im
    Crossfade-Bereich) faellt.

    Downbeat-Feature 2026-07-17: sind die ersten Beat-Zeitpunkte beider
    Segmente aus den Beatgrids bekannt, entfaellt die (teurere und
    unsicherere) Laufzeit-Schaetzung via librosa.beat.beat_track.

    AUDIT-FIX N-02 (2026-07-26): seg_b wird jetzt mit `lead_frames` Vorlauf
    (1 Takt vor dem Mix-In) uebergeben. Der Alignment-Cut waehlt den
    GROESSTEN Schnitt <= lead_frames mit korrekter Phase — er schneidet also
    nur in den Vorlauf, nie in den eigentlichen Einsatz (Phrasen-/Drop-Start
    bei lead_frames). Vorher wurden bis zu grid_len/2 Samples (2 Beats auf
    dem Takt-Pfad) vom Einsatz selbst verworfen. Das zurueckgegebene Segment
    beginnt am (alignierten) Crossfade-Start; der Vorlauf ist konsumiert.

    Ohne Vorlauf (lead_frames == 0, Mix-In am Track-Anfang) bleibt das alte
    Verhalten: naechstgelegene Verschiebung, nach vorne = Cut, nach hinten =
    Null-Padding (< 1/2 Grid, unhoerbar da im Fade-In).

    AUDIT-FIX D-03 (2026-08-14): `bar_aligned` entscheidet ueber die
    Gitterweite des Exakt-Pfads — Takt (METER Beats) nur mit beidseitigem
    Referenz-Beatgrid, sonst Beat. Die uebergebenen Phasen sind in beiden
    Faellen dieselben Takt-Phasen; modulo beat_len ergibt daraus die
    Beat-Phase.
    """
    lead_frames = max(0, min(int(lead_frames), len(seg_b)))
    if bpm <= 0 or len(ref_seg) < sr or len(seg_b) < sr:
        return seg_b[lead_frames:]
    beat_len = int(round(60.0 / bpm * sr))
    if beat_len <= 0:
        return seg_b[lead_frames:]

    # AUDIT-FIX C1 (2026-07-26): Auf dem EXAKT-Pfad mit Referenz-Beatgrid wird
    # auf TAKT-Phase aligned (Modulo Bar-Laenge) statt nur auf Beat-Phase.
    # Vorher konnte die Kick zwar auf der Kick sitzen, aber Beat 1 von B auf
    # Beat 3 von A — der Snare-Backbeat und die Taktstruktur lagen versetzt.
    # Der Laufzeit-Schaetz-Pfad (8-s-Fenster) bleibt auf Beat-Ebene: eine
    # Verschiebung um ganze Takte auf Basis einer unsicheren Schaetzung waere
    # riskanter als der Beat-Fehler, den sie korrigieren soll. Dasselbe gilt
    # seit D-03 fuer bekannte Anker aus der EIGENSCHAETZUNG (bar_aligned=False).
    if known_first_beat_a is not None and known_first_beat_b is not None:
        t_a = float(known_first_beat_a)
        t_b = float(known_first_beat_b)
        # D-03: Takt-Phase nur mit beidseitigem Referenz-Beatgrid, sonst
        # Beat-Phase. Die uebergebenen Phasen sind Takt-Phasen; modulo
        # beat_len ergibt daraus korrekt die Beat-Phase.
        grid_len = beat_len * METER if bar_aligned else beat_len
    else:
        t_a = _estimate_first_beat(ref_seg, sr, bpm)
        t_b = _estimate_first_beat(seg_b, sr, bpm)
        grid_len = beat_len
    # t_a/t_b sind Grid-Phasen relativ zum jeweiligen SEGMENT-Anfang.
    # Gesuchter Schnitt: cut == (t_b - t_a) (mod grid_len), damit die Phase
    # des Ergebnis-Anfangs auf dem Raster von A liegt.
    raw = int(round((t_b - t_a) * sr))
    if lead_frames > 0:
        # N-02: groesster phasengleicher Schnitt <= lead_frames — der Einsatz
        # (bei lead_frames) bleibt vollstaendig erhalten und landet maximal
        # grid_len-1 Samples hinter dem Crossfade-Start.
        cut = raw + grid_len * ((lead_frames - raw) // grid_len)
    else:
        # Alt-Verhalten ohne Vorlauf: naechstgelegene Verschiebung (+-1/2 Grid)
        offset = raw % grid_len
        cut = offset if offset <= grid_len // 2 else offset - grid_len

    if cut >= 0:
        shifted = seg_b[cut:]
    else:
        shifted = np.concatenate(
            [np.zeros((-cut, seg_b.shape[1]), dtype=seg_b.dtype), seg_b], axis=0
        )
    shift_info = lead_frames - cut  # Verschiebung relativ zum nominalen Start
    if shift_info != 0:
        logger.info(
            f"Beat-Phase-Alignment: Track B um {shift_info / sr * 1000:.0f}ms verschoben"
        )
    return shifted


def make_temp_output_path(index: int) -> str:
    """Erstellt einen temporaeren Pfad fuer eine Preview-WAV-Datei."""
    tmp_dir = tempfile.gettempdir()
    return os.path.join(tmp_dir, f"hpg_preview_{index:03d}.wav")


# ---------------------------------------------------------------------------
# Hilfsfunktionen (intern)
# ---------------------------------------------------------------------------

def _load_segment(path: str, start_sec: float, duration_sec: float,
                  target_sr: int = 44100) -> np.ndarray:
    """
    Laedt nur den benoetigten Abschnitt einer Audio-Datei.

    soundfile unterstuetzt: WAV, FLAC, AIFF, OGG (nativ, schnell, offset-seeking).
    MP3 wird von soundfile NICHT unterstuetzt → Fallback via librosa.load().

    Gibt immer ein (frames, 2) float32 Array zurueck.
    Mono wird auf Stereo verdoppelt.
    """
    path = str(path)
    audio = None

    # Erster Versuch: soundfile (schnell, unterstuetzt offset-seeking)
    try:
        with sf.SoundFile(path) as f:
            sr_file    = f.samplerate
            start_frame = int(start_sec * sr_file)
            num_frames  = int(duration_sec * sr_file)
            # Seek jenseits Dateiende → leeres Array zurueckgeben (kein Fehler)
            if start_frame >= f.frames:
                # L5-Fix: hoerbar stiller Preview braucht eine sichtbare Ursache im Log
                logger.warning(
                    f"Segment-Start {start_sec:.1f}s liegt hinter dem Dateiende — "
                    f"stilles Segment fuer {os.path.basename(path)} (Mix-Punkt pruefen)"
                )
                return np.zeros((0, 2), dtype=np.float32)
            f.seek(max(0, start_frame))
            audio = f.read(num_frames, dtype='float32', always_2d=True)
            sr_loaded = sr_file
    except (sf.LibsndfileError, RuntimeError):
        # Fallback fuer MP3 und andere nicht-unterstuetzte Formate
        try:
            import librosa
            y, sr_loaded = librosa.load(
                path, sr=None, mono=False,
                offset=start_sec, duration=duration_sec
            )
            if y.ndim == 1:
                y = np.stack([y, y], axis=0)   # Mono → (2, frames)
            audio = y.T.astype(np.float32)      # → (frames, 2)
        except Exception as e:
            raise RuntimeError(f"Konnte Datei nicht laden: {path!r} — {e}") from e

    # Kanal-Normalisierung: immer (frames, 2)
    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)     # Mono → Stereo duplizieren
    elif audio.shape[1] > 2:
        audio = audio[:, :2]                    # Surround → Stereo beschraenken

    # Sample-Rate-Konvertierung wenn noetig (Ausnahme, meist 44100)
    if sr_loaded != target_sr:
        import librosa
        # librosa.resample erwartet (channels, frames)
        audio = librosa.resample(audio.T, orig_sr=sr_loaded, target_sr=target_sr).T

    return audio.astype(np.float32)


def _ensure_len(arr: np.ndarray, n: int) -> np.ndarray:
    """
    Stellt sicher dass arr mindestens n Frames hat.
    Zu kurze Arrays werden mit Null-Frames aufgefuellt (Stille am Ende).
    """
    if len(arr) >= n:
        return arr[:n]
    pad = np.zeros((n - len(arr), 2), dtype=np.float32)
    return np.concatenate([arr, pad])


def _make_sos(cutoff_hz: float, sr: int, btype: str, order: int = 4) -> np.ndarray:
    """
    Erstellt einen Butterworth-Filter als Second-Order-Sections (SOS).
    Butterworth = maximale Flachheit im Durchlassbereich, kein Ripple.
    """
    return butter(order, cutoff_hz, btype=btype, fs=sr, output='sos')


def _apply_filter_ramp(
    unfiltered: np.ndarray,
    filtered: np.ndarray,
    sr: int,
) -> np.ndarray:
    """Blendt den Filtereinsatz am Crossfade-Anfang kurz und sicher ein."""
    ramp_frames = min(
        len(unfiltered),
        len(filtered),
        max(1, int(round(FILTER_RAMP_SECONDS * sr))),
    )
    if ramp_frames < 2:
        return unfiltered.astype(np.float32, copy=True)

    filter_env = np.ones((len(unfiltered), 1), dtype=np.float32)
    filter_env[:ramp_frames] = np.linspace(
        0.0, 1.0, ramp_frames, dtype=np.float32
    )[:, np.newaxis]
    return (
        unfiltered * (1.0 - filter_env) + filtered * filter_env
    ).astype(np.float32)


def _rms_normalize(seg: np.ndarray, target_rms_db: float = -14.0) -> np.ndarray:
    """
    Normalisiert ein Audio-Segment auf einen Ziel-RMS-Pegel.

    Berechnet RMS nur anhand aktiver Frames (obere 80% Energie) um stille
    Intro/Outro-Bereiche zu ignorieren. Gain wird auf +12dB/-20dB begrenzt.

    Hintergrund: EBU R128 definiert -14 LUFS als Streaming-Norm (Spotify, YouTube).
    Durch Normalisierung auf -14 dBRMS klingen unterschiedlich gemasterte Tracks
    im Crossfade gleichmaessig — kein ploetzlicher Lautheitssprung.
    """
    # C2-Fix: leeres Segment (z.B. _load_segment gibt (0,2) wenn der Mix-Punkt
    # hinter dem Dateiende liegt) wuerde np.percentile crashen — unveraendert
    # zurueckgeben, das Null-Padding erfolgt spaeter in _ensure_len.
    if len(seg) == 0:
        return seg

    # Aktive Frames finden (obere 80% Energie — ignoriert stille Passagen)
    energy = np.mean(seg**2, axis=1)
    threshold = np.percentile(energy, 20)
    active = seg[energy > threshold]

    # Fallback: gesamtes Segment wenn zu wenige aktive Frames
    if len(active) < 100:
        active = seg

    current_rms = np.sqrt(np.mean(active**2))
    if current_rms < 1e-6:
        return seg  # Stilles Segment unveraendert lassen

    target_rms_linear = 10 ** (target_rms_db / 20.0)
    gain = target_rms_linear / current_rms

    # Gain clampen: max. +12 dB (4.0x) / -20 dB (0.1x) — verhindert aggressive Eingriffe
    gain = float(np.clip(gain, 0.1, 4.0))
    return (seg * gain).astype(np.float32)


def _measure_segment_loudness(seg: np.ndarray, sr: int) -> float:
    """Integrated Loudness eines bereits normalisierten Segments (BS.1770).

    Returns:
        LUFS (negativ) oder 0.0 als "unbekannt"-Sentinel — mit 0.0 wird
        _apply_lufs_delta zum No-Op, was hier die sichere Variante ist:
        die RMS-Normalisierung allein trifft die Lautheit bereits auf ~0.6 dB.
    """
    if seg is None or len(seg) == 0 or sr <= 0:
        return 0.0
    try:
        import pyloudnorm as pyln

        data = np.asarray(seg, dtype=np.float64)
        if data.ndim == 1:
            data = data[:, None]
        meter = pyln.Meter(sr, filter_class="DeMan")
        if len(data) < int(meter.block_size * sr):
            return 0.0
        value = float(meter.integrated_loudness(data))
        if not np.isfinite(value) or value >= 0.0 or value < -70.0:
            return 0.0
        return value
    except Exception as error:  # pyloudnorm fehlt oder Messung scheitert
        logger.debug("Segment-Loudness nicht messbar: %s", error)
        return 0.0


def _apply_lufs_delta(
    seg_a: np.ndarray,
    seg_b: np.ndarray,
    lufs_a: float,
    lufs_b: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Korrigiert nur den relativen LUFS-Abstand nach der Segment-RMS-Norm."""
    if not (np.isfinite(lufs_a) and np.isfinite(lufs_b)):
        return seg_a, seg_b
    if lufs_a >= 0.0 or lufs_b >= 0.0:
        return seg_a, seg_b

    delta_db = float(np.clip(lufs_a - lufs_b, -6.0, 6.0))
    half_gain = float(10.0 ** (delta_db / 40.0))
    return (
        (seg_a / half_gain).astype(np.float32),
        (seg_b * half_gain).astype(np.float32),
    )


def _apply_soft_limiter(
    mixed: np.ndarray, threshold: float = 0.95
) -> np.ndarray:
    """Begrenzt Peaks kanalgekoppelt und bereinigt ungueltige Samples."""
    limited = np.nan_to_num(mixed, nan=0.0, posinf=1.0, neginf=-1.0).astype(
        np.float32, copy=True
    )
    if limited.size == 0:
        return limited
    frame_peak = np.max(np.abs(limited), axis=1, keepdims=True)
    over = frame_peak > threshold
    excess = (frame_peak - threshold) / (1.0 - threshold + 1e-9)
    limited_peak = threshold + (1.0 - threshold) * np.tanh(excess)
    scale = np.ones_like(frame_peak, dtype=np.float32)
    scale[over] = limited_peak[over] / np.maximum(frame_peak[over], 1e-12)
    return limited * scale


_pedalboard_warned = False


def _apply_compressor(mixed: np.ndarray, sr: int) -> np.ndarray:
    """
    Wendet einen sanften pedalboard-Compressor an.

    2:1 Ratio + -12 dBFS Threshold = nicht destruktiv, Transienten bleiben erhalten.
    Fallback auf Eingangssignal wenn pedalboard nicht installiert ist.

    Testwert (2026-02-28 PoC): reduziert Lautheitssprung von ~2 dB auf ~0.1 dB
    nach vorheriger RMS-Normalisierung.
    """
    global _pedalboard_warned
    try:
        from pedalboard import Pedalboard, Compressor  # type: ignore[import]
    except ImportError:
        if not _pedalboard_warned:
            logger.warning(
                "Optional library 'pedalboard' is not installed. High-end transition compression is disabled. "
                "You can install it using 'pip install pedalboard' to enable smooth multi-band compression."
            )
            _pedalboard_warned = True
        return mixed

    # pedalboard erwartet ein zusammenhaengendes float32-Array im Layout
    # (channels, frames). mixed.T ist nur ein nicht zusammenhaengender View;
    # dessen native Verarbeitung kann auf Windows mit einer Access Violation
    # enden, statt einen Python-Fehler zu liefern.
    stereo = np.ascontiguousarray(mixed.T, dtype=np.float32)
    board = Pedalboard([
        Compressor(
            threshold_db=-12.0,  # Erst ab -12 dBFS komprimieren
            ratio=2.0,           # 2:1 = sanfte Kompression
            attack_ms=20.0,      # Langer Attack = Transienten bleiben erhalten
            release_ms=200.0,    # Normaler Release
        ),
    ])
    compressed = board(stereo, sr).T  # Zurueck zu (frames, channels)
    return compressed.astype(np.float32)


def _apply_eq_crossfade(
    seg_a: np.ndarray,       # (cf_frames, 2) float32 — Track A im Crossfade
    seg_b: np.ndarray,       # (cf_frames, 2) float32 — Track B im Crossfade
    config: EqCrossfadeConfig,
) -> np.ndarray:
    """
    Wendet hochpraezise, echt verdrahtete EQ- und DSP-Effekte fuer DJ-Übergänge an.

    Fade-Envelopes:
      fo (fade_out): Track A verschwindet
      fi (fade_in):  Track B erscheint

    AUDIT-FIX C3 (2026-07-24): EQUAL-POWER (cos/sin) statt linear. Ein linearer
    Crossfade erzeugt bei nicht perfekt korrelierten Signalen in der Mitte ein
    hoerbares ~-3-dB-Lautheitsloch. Die Equal-Power-Kurven halten die
    Summenleistung fo^2 + fi^2 == 1 konstant. Betrifft die Hoehen im bass_swap,
    filter_ride/smooth_blend/breakdown_bridge und den Fallback-Crossfade.
    """
    _t = np.linspace(0.0, 1.0, config.cf_frames, dtype=np.float32)
    fo = np.cos(_t * (np.pi / 2.0)).astype(np.float32)[:, np.newaxis]
    fi = np.sin(_t * (np.pi / 2.0)).astype(np.float32)[:, np.newaxis]

    # Audit-Fix 2026-07-21: sosfiltfilt verlangt Segmentlaenge > padlen (~30-60
    # Samples). Bei extrem kurzem Crossfade (< ~1.5ms) crasht der Filter mit
    # "input vector x must be greater than padlen". Solche Winz-Crossfades sind
    # ohnehin degeneriert -> sauberer linearer Crossfade ohne EQ-Filter.
    min_frames = min(len(seg_a), len(seg_b))
    if min_frames < 64:
        return (seg_a * fo + seg_b * fi).astype(np.float32)

    t_type = str(config.transition_type).lower()

    if t_type == "bass_swap":
        # Bass (Tief) und Hoehen separat faden (klassischer EQ-Bass-Swap)
        sos_lp = _make_sos(config.bass_cutoff_hz, config.sr, 'low')
        sos_hp = _make_sos(config.bass_cutoff_hz, config.sr, 'high')

        highs_a = sosfiltfilt(sos_hp, seg_a, axis=0)
        highs_b = sosfiltfilt(sos_hp, seg_b, axis=0)
        bass_a  = sosfiltfilt(sos_lp, seg_a, axis=0)
        bass_b  = sosfiltfilt(sos_lp, seg_b, axis=0)

        # AUDIT-FIX R-09 (2026-07-24): Die hier vorher stehende Zeile
        # `mixed = highs_a * fo + highs_b * fi` erzeugte ein komplettes
        # Crossfade-langes Array, das 16 Zeilen weiter sofort ueberschrieben
        # wurde — reine Verschwendung, entfernt.

        # M6-Fix: echter Bass-Handover — harter Swap am Crossfade-Mittelpunkt
        # mit kurzer 50ms-Rampe gegen Klicks. Vorher ueberlappten beide Baesse
        # (A~0.75 / B~0.25 am Mittelpunkt) — doppelter Sub-Bass.
        half = config.cf_frames // 2
        ramp = max(1, int(0.05 * config.sr))
        ramp_end = min(half + ramp, config.cf_frames)
        n_ramp = ramp_end - half
        bass_a_env = np.ones((config.cf_frames, 1), dtype=np.float32)
        bass_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)
        if n_ramp > 0:
            bass_a_env[half:ramp_end] = np.linspace(1.0, 0.0, n_ramp, dtype=np.float32)[:, np.newaxis]
            bass_b_env[half:ramp_end] = np.linspace(0.0, 1.0, n_ramp, dtype=np.float32)[:, np.newaxis]
        bass_a_env[ramp_end:] = 0.0
        bass_b_env[ramp_end:] = 1.0
        mixed = bass_a * bass_a_env + bass_b * bass_b_env + highs_a * fo + highs_b * fi

    elif t_type == "pro_eq_swap":
        # 3-Band Linkwitz-Riley EQ Simulation mit Zero-Phase Filtering (sosfiltfilt)
        fc1 = 120.0   # Low-to-Mid Crossover
        fc2 = 2500.0  # Mid-to-High Crossover

        # Filter design
        sos_lp_low  = _make_sos(fc1, config.sr, 'low', order=2)
        sos_hp_high = _make_sos(fc2, config.sr, 'high', order=2)

        # AUDIT-FIX R-05 (2026-07-24): Mitten aus Rest bilden (seg - bass - highs)
        # statt zwei zusaetzlicher Filterpassagen (sos_hp_mid + sos_lp_mid) —
        # spart pro Track 2 von 4 Filterlaeufen und 2 float64-Vollkopien.
        bass_a = sosfiltfilt(sos_lp_low, seg_a, axis=0)
        highs_a = sosfiltfilt(sos_hp_high, seg_a, axis=0)
        mids_a = seg_a - bass_a - highs_a

        bass_b = sosfiltfilt(sos_lp_low, seg_b, axis=0)
        highs_b = sosfiltfilt(sos_hp_high, seg_b, axis=0)
        mids_b = seg_b - bass_b - highs_b

        # Envelopes
        # Lows (Bass-Swap auf der Haelfte mit 50ms Rampe)
        half = config.cf_frames // 2
        ramp = max(1, int(0.05 * config.sr))
        ramp_end = min(half + ramp, config.cf_frames)
        n_ramp = ramp_end - half

        bass_a_env = np.ones((config.cf_frames, 1), dtype=np.float32)
        bass_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)
        if n_ramp > 0:
            bass_a_env[half:ramp_end] = np.linspace(1.0, 0.0, n_ramp, dtype=np.float32)[:, np.newaxis]
            bass_b_env[half:ramp_end] = np.linspace(0.0, 1.0, n_ramp, dtype=np.float32)[:, np.newaxis]
        bass_a_env[ramp_end:] = 0.0
        bass_b_env[ramp_end:] = 1.0

        # Mids: Equal-Power (cos/sin) ueber den gesamten Crossfade.
        # AUDIT-FIX N-01 (2026-07-26): vorher amplituden-komplementaere
        # LINEARE Envelopes ("-6 dB Rule": 1.0 -> 0.5 -> 0.0). Bei nicht
        # korrelierten Signalen ergibt das am Mittelpunkt eine Summenleistung
        # von 0.5^2 + 0.5^2 = 0.5 = -3.01 dB — genau das Energie-Loch, das
        # C3 im Fallback-Crossfade beseitigt hatte, hier im Default-Modus
        # fuer Techno/Psy/Tech-House (Hauptpfad). cos/sin haelt
        # fo^2 + fi^2 == 1 konstant (0 dB am Mittelpunkt). Der harte
        # Bass-Swap oben bleibt unveraendert hart.
        mids_a_env = fo
        mids_b_env = fi

        # Highs (Asymmetrischer Tausch: A voll bis 1/4, B voll ab 3/4).
        # AUDIT-FIX R-02 (2026-07-24): kein a+b > 1 mehr (vorher Summe 2.0
        # am 3/4-Punkt -> +6 dB, Limiter, harsches Uebergangsdrittel).
        # AUDIT-FIX N-01 (2026-07-26): Equal-Power (cos/sin) statt linear-
        # komplementaer — a + b == 1 fixierte zwar die +6-dB-Spitze, erzeugte
        # aber dasselbe -3.01-dB-Leistungsloch am Fenster-Mittelpunkt wie bei
        # den Mids. Jetzt gilt a^2 + b^2 == 1 im gesamten Fade-Fenster.
        quarter = config.cf_frames // 4
        three_quarters = 3 * quarter
        len_in = max(1, three_quarters - quarter)
        # Fade-Fortschritt 0..1 innerhalb des Fensters [1/4 .. 3/4]
        prog = np.linspace(0.0, 1.0, len_in, dtype=np.float32)[:, np.newaxis]

        highs_a_env = np.ones((config.cf_frames, 1), dtype=np.float32)
        highs_b_env = np.zeros((config.cf_frames, 1), dtype=np.float32)
        highs_a_env[quarter:three_quarters] = np.cos(prog * (np.pi / 2.0))
        highs_a_env[three_quarters:] = 0.0
        highs_b_env[quarter:three_quarters] = np.sin(prog * (np.pi / 2.0))
        highs_b_env[three_quarters:] = 1.0

        # Rekonstruktion
        mixed = (bass_a * bass_a_env + bass_b * bass_b_env +
                 mids_a * mids_a_env + mids_b * mids_b_env +
                 highs_a * highs_a_env + highs_b * highs_b_env)

    elif t_type == "filter_ride" or t_type == "smooth_blend":
        # Hochpass- bzw. Tiefpass-Filterung zur Vermeidung von Frequenzüberlagerungen
        if t_type == "filter_ride":
            # Hochpass auf Track A simuliert einen Filter-Sweep beim Ausblenden
            sos_hp_a = _make_sos(FILTER_RIDE_HP_HZ, config.sr, 'high')
            filtered_a = sosfiltfilt(sos_hp_a, seg_a, axis=0)
            filtered_a = _apply_filter_ramp(seg_a, filtered_a, config.sr)
            mixed = filtered_a * fo + seg_b * fi
        else:
            # smooth_blend: Tiefpass auf Track A waehrend Track B einfadet
            sos_lp_a = _make_sos(SMOOTH_BLEND_LP_HZ, config.sr, 'low')
            filtered_a = sosfiltfilt(sos_lp_a, seg_a, axis=0)
            filtered_a = _apply_filter_ramp(seg_a, filtered_a, config.sr)
            mixed = filtered_a * fo + seg_b * fi

    elif t_type == "cold_cut":
        # Harter Cut in der Mitte — AUDIT-FIX R-06 (2026-07-24): mit 3ms
        # Mikro-Fade um die Schnittstelle gegen den sonst garantierten Klick
        # (Amplitudensprung A->B = breitbandiger Impuls). Bleibt hoerbar ein
        # harter Cut.
        half = config.cf_frames // 2
        mixed = np.zeros_like(seg_a)
        mixed[:half] = seg_a[:half]
        mixed[half:] = seg_b[half:]
        mf = min(int(0.003 * config.sr), half, config.cf_frames - half)
        if mf > 0:
            ramp = np.linspace(1.0, 0.0, mf, dtype=np.float32)[:, np.newaxis]
            mixed[half - mf:half] = (
                seg_a[half - mf:half] * ramp + seg_b[half - mf:half] * (1.0 - ramp)
            )

    elif t_type == "drop_cut":
        # Track A blendet bis zur Mitte aus, dann bricht Track B ein.
        # AUDIT-FIX R-06: kurzer Mikro-Fade am Einsatzpunkt von B gegen Klick.
        half = config.cf_frames // 2
        fo_half = np.linspace(1.0, 0.0, half, dtype=np.float32)[:, np.newaxis]
        mixed = np.zeros_like(seg_a)
        mixed[:half] = seg_a[:half] * fo_half
        mixed[half:] = seg_b[half:]
        mf = min(int(0.003 * config.sr), config.cf_frames - half)
        if mf > 0:
            ramp_in = np.linspace(0.0, 1.0, mf, dtype=np.float32)[:, np.newaxis]
            mixed[half:half + mf] = seg_b[half:half + mf] * ramp_in

    elif t_type == "echo_out":
        # Track A bekommt ein Echo-Delay-Feedback, waehrend Track B einfadet.
        mixed = seg_b * fi

        # AUDIT-FIX R-04 (2026-07-24): Delay ist jetzt BEAT-synchron zu Track A
        # (vorher fix 0.5 s = bei 120 BPM ein ganzer Beat, bei 138 BPM 65 ms
        # Drift pro Reflexion -> hoerbares Flamming). Ein Beat = 60/bpm.
        beat_sec = 60.0 / config.bpm_a if config.bpm_a > 0 else 0.5
        delay_samples = max(1, int(beat_sec * config.sr))
        echo_signal = seg_a.copy()

        # 3 Echo-Reflektionen mit Daempfung (Feedback)
        for i in range(1, 4):
            shift = i * delay_samples
            if shift < len(echo_signal):
                echo_signal[shift:] += seg_a[:-shift] * (0.45 ** i)

        # AUDIT-FIX R-04: Pegel normieren — die kohaerente Summe erreichte bis
        # 1.74x (1 + 0.45 + 0.2 + 0.09) und loeste bei -14 dBRMS Clipping aus.
        echo_signal *= (1.0 / 1.74)
        mixed += echo_signal * fo

    elif t_type == "breakdown_bridge":
        # Bass aus Track A sofort komplett rausfiltern, um Platz fuer Track B zu machen
        sos_hp = _make_sos(BREAKDOWN_HP_HZ, config.sr, 'high')
        highs_a = sosfiltfilt(sos_hp, seg_a, axis=0)
        highs_a = _apply_filter_ramp(seg_a, highs_a, config.sr)
        mixed = highs_a * fo + seg_b * fi

    else:
        # Standard-Fallback bei unkonfigurierten Typen: linearer Crossfade
        mixed = seg_a * fo + seg_b * fi

    return mixed.astype(np.float32)


# ---------------------------------------------------------------------------
# Direkt ausfuehrbar fuer schnellen Smoke-Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("transition_renderer — Smoke-Test mit synthetischen Daten")

    # Synthetischen Stereo-Sinus erzeugen und als WAV schreiben
    test_sr = 44100
    duration = 60.0  # 1 Minute pro Test-Track
    t = np.linspace(0, duration, int(test_sr * duration), endpoint=False)
    track_a_data = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    track_b_data = (np.sin(2 * np.pi * 528 * t) * 0.5).astype(np.float32)
    track_a_stereo = np.stack([track_a_data, track_a_data], axis=1)
    track_b_stereo = np.stack([track_b_data, track_b_data], axis=1)

    tmp = tempfile.gettempdir()
    path_a = os.path.join(tmp, "hpg_test_track_a.wav")
    path_b = os.path.join(tmp, "hpg_test_track_b.wav")
    out_path = os.path.join(tmp, "hpg_smoke_test_preview.wav")

    sf.write(path_a, track_a_stereo, test_sr, subtype='PCM_16')
    sf.write(path_b, track_b_stereo, test_sr, subtype='PCM_16')

    spec = TransitionClipSpec(
        track_a_path    = path_a,
        track_b_path    = path_b,
        mix_out_sec     = 40.0,
        mix_in_sec      = 5.0,
        crossfade_sec   = 16.0,
        transition_type = "bass_swap",
        pre_roll_sec    = 10.0,
        post_roll_sec   = 10.0,
    )

    result = render_transition_clip(spec, out_path)
    file_info = sf.info(result)
    print(f"  Output: {result}")
    print(f"  Dauer:  {file_info.duration:.1f}s")
    print(f"  Kanaele: {file_info.channels}")
    print(f"  Sample-Rate: {file_info.samplerate} Hz")

    expected_dur = spec.pre_roll_sec + spec.crossfade_sec + spec.post_roll_sec
    assert abs(file_info.duration - expected_dur) < 0.5, \
        f"Erwartete Dauer {expected_dur}s, bekommen {file_info.duration:.1f}s"
    print(f"  Smoke-Test BESTANDEN (Erwartete Dauer: ~{expected_dur:.0f}s)")

    # Aufraeumen
    for p in [path_a, path_b, out_path]:
        if os.path.exists(p):
            os.remove(p)
