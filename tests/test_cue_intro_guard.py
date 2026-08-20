"""Tests fuer den Intro-Guard der Rekordbox-Cue-Uebernahme.

Hintergrund: Invariante 5 (Mix-In nie im Intro) war nur in
`calculate_genre_aware_mix_points` gesichert. Die Cue-Uebernahme in
`analyze_track` umging sie vollstaendig — gemessen an 232 Tracks lagen
dadurch 24 Mix-Punkte im fuehrenden Intro, bis zu 56,5 s tief. Alle 24
stammten aus dem Heuristik-Zweig (`dedup_positions[1]`), kein einziger aus
einem benannten Cue.

Vor dieser Datei gab es KEINEN Test, der die Cue-Uebernahme beruehrt — ein
Rueckbau des Guards waere lautlos geblieben.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from hpg_core.analysis import cue_in_verwerfen
from hpg_core.models import QUANTIZE_TOLERANCE_SEC


class TestCueInVerwerfen:
    """Die Entscheidung, ob ein geratener Mix-In-Cue verworfen wird."""

    def test_heuristik_cue_im_intro_wird_verworfen(self):
        """Der Regelfall: DJs setzen den zweiten Hot Cue typisch bei rund
        30 s, das Intro endet bei 60 s."""
        assert cue_in_verwerfen(30.0, benannter_cue=False, intro_ende=60.0) is True

    def test_heuristik_cue_nach_dem_intro_bleibt(self):
        assert cue_in_verwerfen(70.0, benannter_cue=False, intro_ende=60.0) is False

    def test_benannter_cue_im_intro_bleibt(self):
        """Die bewusste Ausnahme: wer seinen Cue selbst benennt, hat sich
        etwas dabei gedacht. Ohne diesen Test kippt die Ausnahme beim
        naechsten Refactor stillschweigend."""
        assert cue_in_verwerfen(30.0, benannter_cue=True, intro_ende=60.0) is False

    def test_ohne_sektionen_kein_urteil(self):
        """intro_ende == 0 heisst 'kein Intro erkannt', nicht 'Intro bei 0'.
        Dann darf der Guard nicht auf gut Glueck verwerfen."""
        assert cue_in_verwerfen(30.0, benannter_cue=False, intro_ende=0.0) is False

    def test_ohne_cue_nichts_zu_verwerfen(self):
        assert cue_in_verwerfen(None, benannter_cue=False, intro_ende=60.0) is False

    def test_rundungsrauschen_wird_nicht_verworfen(self):
        """36 der 232 gemessenen Tracks liegen unter dem Intro-Ende, alle
        unter 5 ms (Median 3,2 ms, Maximum 4,9 ms) — reine Quantisierung."""
        assert cue_in_verwerfen(59.9968, benannter_cue=False,
                                intro_ende=60.0) is False   # 3,2 ms, der Median
        assert cue_in_verwerfen(59.9951, benannter_cue=False,
                                intro_ende=60.0) is False   # 4,9 ms, der groesste

    def test_epsilon_ist_die_projektkonstante(self):
        """Kein eigener Wert: dieselbe Konstante entscheidet in
        quantize_to_grid, wann ein Punkt als 'auf dem Raster' gilt."""
        knapp_drueber = 60.0 - QUANTIZE_TOLERANCE_SEC * 0.5
        knapp_drunter = 60.0 - QUANTIZE_TOLERANCE_SEC * 2.0
        assert cue_in_verwerfen(knapp_drueber, benannter_cue=False,
                                intro_ende=60.0) is False
        assert cue_in_verwerfen(knapp_drunter, benannter_cue=False,
                                intro_ende=60.0) is True

    def test_deutlicher_abstand_wird_verworfen(self):
        """Eine halbe Sekunde ist keine Rundung mehr."""
        assert cue_in_verwerfen(59.5, benannter_cue=False,
                                intro_ende=60.0) is True

    def test_exakt_auf_der_intro_grenze_bleibt(self):
        assert cue_in_verwerfen(60.0, benannter_cue=False, intro_ende=60.0) is False

    def test_mindestfenster_gilt_nur_wenn_der_guard_zuschlug(self):
        """Die Bedingung darf benannte Cue-Paare nicht anfassen.

        Sonst haette ein benanntes Paar mit kurzem Fenster (z. B. MIX IN 60 s,
        MIX OUT 80 s bei 140 BPM und phrase_unit 16: noetig waeren 54,9 s)
        seine Cues verloren — genau die Ausnahme, die der Spec-Nachtrag
        zusichert. Gemessen am Bestand betrifft die Bedingung 0 von 210
        Tracks mit verwertbarem Cue-Paar; sie ist Absicherung, kein Eingriff.

        ACHTUNG zur Reichweite dieses Tests: er prueft die SPEZIFIKATION,
        nicht die Produktionslogik. Das Mindestfenster steckt inline in
        analyze_track und ist ohne echtes Audio nicht ausfuehrbar; hier wird
        die Entscheidung nachgebildet. Wer in analysis.py das
        `if guard_hat_zugeschlagen else 0.0` streicht, macht diesen Test
        NICHT rot. Die Absicherung dagegen ist der Kommentar an der Stelle
        selbst plus dieser Test als Beschreibung des Sollverhaltens.
        """
        def min_fenster(guard_zuschlug, bpm=140.0, phrase_unit=16):
            return ((60.0 / bpm) * 4 * phrase_unit * 2) if guard_zuschlug else 0.0

        # benannter Cue: Guard schlaegt nie zu -> kein Mindestfenster
        assert cue_in_verwerfen(60.0, benannter_cue=True, intro_ende=90.0) is False
        assert min_fenster(False) == 0.0
        assert 80.0 - 60.0 >= min_fenster(False)      # Paar bleibt erhalten

        # Heuristik im Intro: Guard schlaegt zu -> Mindestfenster greift
        assert cue_in_verwerfen(60.0, benannter_cue=False, intro_ende=90.0) is True
        assert min_fenster(True) == pytest.approx(54.857, abs=0.01)

    @pytest.mark.parametrize("cue_in,intro_ende", [
        (30.0, 60.0),    # King of the Night
        (27.6, 55.2),    # Indian Jackpot
        (5.3, 61.8),     # Apocalipto — 56,5 s tief, der schlimmste Fall
        (15.0, 45.0),    # Luzius in the Shopping-Center
        (31.0, 77.4),    # All Around Us
    ])
    def test_gemessene_faelle_werden_alle_gefangen(self, cue_in, intro_ende):
        """Echte Werte aus dem Cache, alle aus dem Heuristik-Zweig."""
        assert cue_in_verwerfen(cue_in, benannter_cue=False,
                                intro_ende=intro_ende) is True
