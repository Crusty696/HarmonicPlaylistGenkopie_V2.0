"""Qt-freie Texte und Metadaten zum tatsächlich gewählten Übergang."""
import math

from .models import get_camelot_components

TRANSITION_TYPE_LABELS: dict[str, str] = {
    "smooth_blend": "Smooth Blend",
    "bass_swap": "Bass Swap",
    "pro_eq_swap": "Pro EQ Swap",
    "breakdown_bridge": "Breakdown Bridge",
    "drop_cut": "Drop Cut",
    "filter_ride": "Filter Ride",
    "halftime_switch": "Halftime Switch",
    "echo_out": "Echo Out",
    "cold_cut": "Cold Cut",
}


def local_key_note(current, upcoming, candidate) -> str:
    """Erklärt ausschließlich die Tonartquelle des bewerteten Kandidaten.

    Trackweite Codes bleiben getrennte Kontextdaten. Ein Snapshot ohne lokale
    Messwerte wird nicht nachträglich aus Metadaten oder anderen Punkten ergänzt.
    """
    def field(value, name, default=None):
        return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)

    def key(value):
        code = field(value, "camelot_lokal", "")
        return code if isinstance(code, str) and get_camelot_components(code)[0] else ""

    def confidence(value):
        number = field(value, "key_confidence_lokal")
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1:
            return "unbekannt"
        return f"{number:.3f}".rstrip("0").rstrip(".").replace(".", ",")

    outgoing, incoming = field(candidate, "out_a"), field(candidate, "in_b")
    code_a, code_b = key(outgoing), key(incoming)
    parts = []
    if code_a and code_b:
        parts.append(f"Lokale Tonarten (Mix-Out/Mix-In): {code_a} -> {code_b}")
        score = dict(field(candidate, "teilwerte", {}) or {}).get("harmonic")
        if type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1:
            level = ("stark" if score >= 0.9 else "kompatibel" if score >= 0.7
                     else "eingeschränkt" if score >= 0.5 else "gering")
            parts.append(f"Lokale Harmonie {level} ({score * 100:.0f}/100)")
        else:
            parts.append("Lokale Harmoniebewertung unbekannt")
        parts.append(f"Messkonfidenz: {confidence(outgoing)} / {confidence(incoming)}")
    else:
        parts.append("Lokale Tonart nicht vollständig bestimmt")
        parts.append(f"Mix-Out/Mix-In: {code_a or 'unbekannt'} -> {code_b or 'unbekannt'}")

    global_a = getattr(current, "camelotCode", "") or "unbekannt"
    global_b = getattr(upcoming, "camelotCode", "") or "unbekannt"
    if not code_a or not code_b or (global_a, global_b) != (code_a, code_b):
        parts.append(f"Trackweite Tonarten: {global_a} -> {global_b} (separate Quelle, keine lokale Bewertung)")
    return "; ".join(parts)


def format_dj_notes(recommendation) -> list[str]:
    """Formatiert aktuelle Metadaten; verändert weder Empfehlung noch Plan."""
    notes = []
    for field, prefix in (("mix_technique", "Mix"), ("eq_advice", "EQ")):
        value = getattr(recommendation, field, "")
        if value:
            notes.append(f"{prefix}: {value}")
    bars = getattr(recommendation, "transition_bars", 0)
    if bars > 0:
        notes.append(f"Übergang: {bars} Takte")
    structure = getattr(recommendation, "structure_note", "")
    if structure:
        notes.append(structure)
    genre_pair = getattr(recommendation, "genre_pair", "")
    if genre_pair:
        notes.append(f"[{genre_pair}]")
    notes.extend(f"! {risk}" for risk in getattr(recommendation, "risk_notes", ()) or ())
    for field, prefix in (
        ("bpm_advice", "BPM"), ("key_advice", "Tonart"),
        ("energy_advice", "Energie"), ("gain_advice", "Gain"),
        ("rhythm_advice", "Rhythmus"),
    ):
        value = getattr(recommendation, field, "")
        if value:
            notes.append(f"{prefix}: {value}")
    return notes


def bind_candidate_recommendation(recommendation, current, upcoming, candidate, transition_type):
    """Bindet erläuternde Metadaten an den Plan, ohne die Mixwahl zu verändern."""
    from .dj_brain import _build_structure_note, section_dict_at_time

    recommendation.adjusted_mix_out_a = float(candidate.t_out)
    recommendation.adjusted_mix_in_b = float(candidate.t_in)
    recommendation.overlap_seconds = float(candidate.overlap_sec)
    recommendation.transition_bars = int(candidate.blend_bars)
    recommendation.transition_type = transition_type
    recommendation.mix_technique = TRANSITION_TYPE_LABELS.get(transition_type, transition_type)
    recommendation.key_advice = local_key_note(current, upcoming, candidate)
    # Diese Warnung stammt ausdrücklich aus dem globalen Camelot-Vergleich.
    # Alle übrigen Risiken bleiben erhalten; die lokale Bewertung steht oben.
    recommendation.risk_notes = [
        risk for risk in (getattr(recommendation, "risk_notes", ()) or ())
        if not str(risk).startswith("Tonart-Clash (Camelot-Distanz:")
    ]
    # Die generische EQ-Anweisung wurde für eine andere Technik erzeugt.
    # Konkrete Ausführung bleibt im aktiven Plan und dessen Renderer verankert.
    recommendation.eq_advice = ""
    outgoing = section_dict_at_time(current, candidate.t_out) or {}
    incoming = section_dict_at_time(upcoming, candidate.t_in) or {}
    recommendation.outgoing_section = outgoing.get("label", "unknown")
    recommendation.incoming_section = incoming.get("label", "unknown")
    recommendation.structure_note = _build_structure_note(
        recommendation.outgoing_section, recommendation.incoming_section
    )
