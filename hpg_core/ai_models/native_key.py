"""Tonartvertrag des hashgepinnten Rekordbox-Phrasengenerators.

Rekordbox 7.2.19: Caller RVA 0x1213840 liest die Indextabelle 0x37d02e0
und die UTF-16-Namen über 0x5de00b0. Die Reihenfolge ist A bis Ab,
danach Am bis Abm. Dieser Vertrag gilt ausschließlich für die gepinnte EXE.
"""
from __future__ import annotations


KEY_MAPPING_VERSION = 1
_NOTES = ('A', 'Bb', 'B', 'C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab')
_ALIASES = {'A#': 'Bb', 'C#': 'Db', 'D#': 'Eb', 'G#': 'Ab', 'Gb': 'F#'}


def native_key_index(note, mode):
    """Liefert den belegten Index oder None für eine unbekannte Tonart.

    None bleibt von A-Dur (Index 0) unterscheidbar. Erst der Aufrufer darf
    den nativen Unknown-Fallback 0 wählen und muss dessen Herkunft bewahren.
    """
    if type(note) is not str or type(mode) is not str or mode not in ('Major', 'Minor'):
        return None
    note = _ALIASES.get(note, note)
    if note not in _NOTES:
        return None
    return _NOTES.index(note) + (12 if mode == 'Minor' else 0)
