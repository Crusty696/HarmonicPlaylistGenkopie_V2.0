"""Rekonstruierte Modellwahl aus Rekordbox 7.2.19, RVA128ecd0.

Konfiguration 2 übernimmt das gespeicherte native Modusbit; sie bedeutet
nicht automatisch eine Tempoheuristik. 3 und 4 wählen ausdrücklich Modell8/7.
Die Zuordnung zu Rekordbox-Oberflächenbezeichnungen ist nicht belegt.
"""
import os


VERSION = 'rb-7.2.19-mode-selection-v1'


def configured_mode():
    """HPG-Vorgabe 2 übernimmt das native Modusbit; kein behaupteter RB-Default."""
    value = os.environ.get('HPG_NATIVE_BEAT_MODE', '2')
    if value not in ('2', '3', '4'):
        raise ValueError('Unsupported native beat configuration; expected 2, 3 or 4')
    return int(value)


def select_model(mode, stored_mode=None):
    if type(mode) is not int or mode not in (2, 3, 4):
        raise ValueError('Native configuration uses a different analysis pipeline')
    if mode == 2:
        if type(stored_mode) is not bool:
            raise ValueError('Native stored mode is required for configuration 2')
        selected = stored_mode
    else:
        selected = mode == 4
    return dict(version=VERSION, configuration=mode,
                stored_mode=stored_mode if mode == 2 else None,
                model_id='model7' if selected else 'model8', chunked=selected)


def validate_selection(value):
    if type(value) is not dict or set(value) != {
            'version', 'configuration', 'stored_mode', 'model_id', 'chunked'}:
        raise ValueError('Invalid native model selection')
    expected = select_model(value['configuration'], value['stored_mode'])
    if value != expected or type(value['chunked']) is not bool:
        raise ValueError('Inconsistent native model selection')
