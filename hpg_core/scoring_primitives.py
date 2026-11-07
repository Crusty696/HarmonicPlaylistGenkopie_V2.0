"""Qt-freie gemeinsame Grundlagen der lokalen Bewertung."""

VOCAL_CLASH_PENALTY = 0.06  # Abzug nur bei beidseitig bekannten Vocals.

def combine_weighted(
    components: dict[str, float | None], weights: dict[str, float]
) -> float:
    """Gewichtete Summe; fehlende Komponenten werden umverteilt.

    Ein Faktor mit Wert None ist "nicht bestimmbar" und wird NICHT mit 0
    bewertet — das waere eine stille Bestrafung fuer Tracks ohne Groove-Daten.
    Stattdessen faellt er samt Gewicht aus der Summe, und die verbleibenden
    Gewichte werden auf 1.0 renormiert.
    """
    verfuegbar = {k: v for k, v in components.items() if v is not None}
    if not verfuegbar:
        return 0.0
    gewicht_summe = sum(weights.get(k, 0.0) for k in verfuegbar)
    if gewicht_summe <= 0.0:
        return 0.0
    roh = sum(weights.get(k, 0.0) * float(v) for k, v in verfuegbar.items())
    return roh / gewicht_summe
