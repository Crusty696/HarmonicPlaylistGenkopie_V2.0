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

    def test_benannter_cue_im_intro_wird_ebenfalls_verworfen(self):
        assert cue_in_verwerfen(30.0, benannter_cue=True, intro_ende=60.0) is True

    def test_ohne_sektionen_kein_urteil(self):
        """Ohne erkanntes Intro gilt nur das Sicherheitsband ab Trackstart."""
        assert cue_in_verwerfen(30.0, benannter_cue=False, intro_ende=0.0) is False
        assert cue_in_verwerfen(0.0, benannter_cue=True, intro_ende=0.0) is True

    def test_ohne_cue_nichts_zu_verwerfen(self):
        assert cue_in_verwerfen(None, benannter_cue=False, intro_ende=60.0) is False

    def test_sicherheitsband_wird_verworfen(self):
        assert cue_in_verwerfen(59.9968, benannter_cue=False,
                                intro_ende=60.0) is True
        assert cue_in_verwerfen(60.04, benannter_cue=True,
                                intro_ende=60.0) is True

    def test_introgrenze_nutzt_projekttoleranz(self):
        band_ende = 60.0 + QUANTIZE_TOLERANCE_SEC
        sicher_danach = band_ende + 0.001
        assert cue_in_verwerfen(band_ende, benannter_cue=False,
                                intro_ende=60.0) is True
        assert cue_in_verwerfen(sicher_danach, benannter_cue=False,
                                intro_ende=60.0) is False

    def test_deutlicher_abstand_wird_verworfen(self):
        """Eine halbe Sekunde ist keine Rundung mehr."""
        assert cue_in_verwerfen(59.5, benannter_cue=False,
                                intro_ende=60.0) is True

    def test_exakt_auf_der_intro_grenze_wird_verworfen(self):
        assert cue_in_verwerfen(60.0, benannter_cue=False, intro_ende=60.0) is True

    def test_benannter_cue_hat_keine_guard_ausnahme(self):
        assert cue_in_verwerfen(60.0, benannter_cue=True, intro_ende=90.0) is True
        assert cue_in_verwerfen(60.0, benannter_cue=False, intro_ende=90.0) is True

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
