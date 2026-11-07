"""Lesende Detaildarstellung aus dem aktiven Track und seinen Empfehlungen."""


def playlist_track_details(track, index, recommendations):
    """Keine Neuanalyse und keine Änderung der gespeicherten Messwerte."""
    from ..measurement_panel import track_measurement_summary
    origin = {"fresh": "Frische Analyse", "cache": "Cache-Wiederverwendung"}.get(
        getattr(track, "analysis_origin", None), "Nicht dokumentiert"
    )
    parts = [
        f"Position {index + 1}: {track.title or track.fileName}",
        f"Interpret: {track.artist or 'Unbekannt'}",
        f"Analyseherkunft: {origin}",
        track_measurement_summary(track),
        "",
    ]
    if index == 0:
        parts.append("Erster Track: kein eingehender Übergang.")
    else:
        rec = next((rec for pos, rec in enumerate(recommendations or ())
                    if getattr(rec, "index", pos) == index - 1), None)
        plan = getattr(rec, "plan", None)
        if plan is None:
            parts.extend([
                "UNGEPLANT – keine ausführbare Übergangsplanung.",
                getattr(rec, "notes", "") or "Für diese Grenze liegt kein freigegebener Plan vor.",
                "Nächster Schritt: Messdiagnose und Kandidaten unter Übergänge prüfen; "
                "gegebenenfalls einen anderen Nachbartrack wählen.",
            ])
        else:
            parts.extend([
                f"Aktiver Kandidat: {getattr(rec, 'kandidat_aktiv', 0)}",
                f"Mix-Out vorheriger Track: {plan.mix_out_a:.2f} s",
                f"Mix-In dieses Tracks: {plan.mix_in_b:.2f} s",
                f"Blende: {plan.overlap:.2f} s · {plan.transition_type}",
                getattr(rec, "notes", ""),
                "Nächster Schritt: Übergang anhören und bewerten.",
            ])
    return "\n".join(parts)
