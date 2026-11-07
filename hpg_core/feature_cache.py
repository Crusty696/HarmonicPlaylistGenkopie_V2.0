"""Tracklokale, wiederverwendbare Audiomerkmale ohne Analyse-Orchestrierung."""
from __future__ import annotations
from dataclasses import dataclass, field
import librosa
import numpy as np
from .config import HOP_LENGTH

@dataclass
class FeatureCache:
    """Lazy, track-lokaler Cache für wiederverwendete Librosa-Features.

    Die Cache-Einträge werden erst beim ersten Zugriff berechnet. Dadurch
    bleibt der bestehende Fast-Path leichtgewichtig, während Struktur-,
    Fingerprint- und Track-Feature-Pfade dieselben Matrizen teilen können.
    Module außerhalb des Ownership-Scope bleiben bewusst über ihre alten
    Signaturen angebunden.
    """

    y: np.ndarray
    sr: int
    _mfcc: dict[tuple[int, int | None], np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _rms: dict[int, np.ndarray] = field(default_factory=dict, init=False, repr=False)
    _stft: dict[tuple[int, int], np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _chroma: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _centroid: dict[int, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _flatness: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _contrast: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _onset: dict[int | None, np.ndarray] = field(
        default_factory=dict, init=False, repr=False
    )
    _hpss: tuple[np.ndarray, np.ndarray] | None = field(
        default=None, init=False, repr=False
    )

    def fenster(self, max_samples: int) -> "FeatureCache":
        """Abgeleiteter Cache ueber die ersten `max_samples` Samples.

        Warum ueberhaupt: Fast-Path und Vollpfad laden verschieden lange
        Signale und rechnen dieselben Merkmalsfunktionen darauf. Das Ergebnis
        haengt damit daran, ob Rekordbox-Metadaten vorliegen -- und genau
        diese Werte vergleicht das Scoring miteinander (D8).

        Ist das Signal nicht laenger als das Fenster, kommt das ELTERNOBJEKT
        selbst zurueck. Der Fast-Path bekommt es heute, weil
        `FEATURE_WINDOW_DURATION` GLEICH `LIBROSA_FAST_PATH_DURATION` ist --
        `config.py` koppelt beide ueber `min`, beide stehen auf 360. Nicht
        "nie groesser als": der `return self`-Zweig verlangt ein Fenster, das
        MINDESTENS so lang ist wie das geladene Signal. Stiege die Ladegrenze
        ueber 360, entstuende auch im Fast-Path ein Kindcache -- fachlich
        folgenlos, weil das Kind denselben Ausschnitt frisch rechnet. Was
        wirklich zaehlt, ist `FEATURE_WINDOW_DURATION <= `
        `LIBROSA_FAST_PATH_DURATION`; das sichert
        `TestMerkmalsfensterKopplung` in tests/test_config.py.

        Sonst entsteht ein LEERER Cache auf dem Ausschnitt. Er rechnet jede
        Matrix selbst und ist damit wertgleich zu einer Rechnung auf
        `self.y[:max_samples]` -- nicht gemessen, sondern dadurch, dass
        dieselbe Funktion mit denselben Parametern auf denselben Samples
        laeuft. Ueber das Verhaeltnis der beiden PFADE zueinander sagt das
        nichts: was Fast-Path und Vollpfad laden, entscheidet `librosa.load`.

        Frueher wurden hier die Matrizen des Elternteils zugeschnitten. Das
        war toter Code -- an beiden Aufrufstellen steht `fenster()` direkt
        hinter `FeatureCache(y, sr)`, der Elterncache ist also leer, und der
        Schnitt lief ueber leere Dicts. Er trug dafuer einen echten Fehler:
        `chroma_stft` schaetzt `tuning` global ueber das ganze Signal, ein
        geschnittenes Chroma haette also zu einer anderen Stimmung gehoert
        als das Fenster (Journal 2026-09-05).
        """
        if max_samples >= len(self.y):
            return self
        return FeatureCache(y=self.y[:max_samples], sr=self.sr)

    def get_mfcc(self, n_mfcc: int = 13, hop_length: int | None = None) -> np.ndarray:
        key = (n_mfcc, hop_length)
        if key not in self._mfcc:
            kwargs = {"y": self.y, "sr": self.sr, "n_mfcc": n_mfcc}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._mfcc[key] = librosa.feature.mfcc(**kwargs)
        return self._mfcc[key]

    def get_rms(self, hop_length: int = HOP_LENGTH) -> np.ndarray:
        if hop_length not in self._rms:
            self._rms[hop_length] = librosa.feature.rms(
                y=self.y, hop_length=hop_length
            )
        return self._rms[hop_length]

    def get_stft_magnitude(
        self, n_fft: int = 2048, hop_length: int = HOP_LENGTH
    ) -> np.ndarray:
        key = (n_fft, hop_length)
        if key not in self._stft:
            self._stft[key] = np.abs(
                librosa.stft(self.y, n_fft=n_fft, hop_length=hop_length)
            )
        return self._stft[key]

    def get_chroma(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._chroma:
            kwargs = {"y": self.y, "sr": self.sr}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._chroma[hop_length] = librosa.feature.chroma_stft(**kwargs)
        return self._chroma[hop_length]

    def get_spectral_centroid(self, hop_length: int = HOP_LENGTH) -> np.ndarray:
        if hop_length not in self._centroid:
            self._centroid[hop_length] = librosa.feature.spectral_centroid(
                y=self.y, sr=self.sr, hop_length=hop_length
            )
        return self._centroid[hop_length]

    def get_spectral_flatness(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._flatness:
            kwargs = {"y": self.y}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._flatness[hop_length] = librosa.feature.spectral_flatness(**kwargs)
        return self._flatness[hop_length]

    def get_spectral_contrast(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._contrast:
            kwargs = {"y": self.y, "sr": self.sr}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._contrast[hop_length] = librosa.feature.spectral_contrast(**kwargs)
        return self._contrast[hop_length]

    def get_onset_strength(self, hop_length: int | None = None) -> np.ndarray:
        if hop_length not in self._onset:
            kwargs = {"y": self.y, "sr": self.sr}
            if hop_length is not None:
                kwargs["hop_length"] = hop_length
            self._onset[hop_length] = librosa.onset.onset_strength(**kwargs)
        return self._onset[hop_length]

    def get_hpss(self) -> tuple[np.ndarray, np.ndarray]:
        if self._hpss is None:
            self._hpss = librosa.effects.hpss(self.y)
        return self._hpss
