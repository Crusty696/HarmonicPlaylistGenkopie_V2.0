"""Strategien mit explizitem Bewertungskontext, unabhängig von der Fassade."""
from __future__ import annotations

import math
import heapq
from dataclasses import dataclass
from typing import Callable, List, Optional, Dict, Tuple
from .models import Track, effective_bpm_diff


@dataclass(frozen=True)
class StrategyServices:
    ENERGY_WAVE_FENSTER: float
    LOOKAHEAD_FUTURE_WEIGHT: float
    LOOKAHEAD_TOP_K: float
    _apply_harmonic_smoothing: Callable
    _check_cancel: Callable
    _context_target_energy: Callable
    _find_best_starting_track: Callable
    _peak_time_curve: Callable
    _prepare_track_metrics: Callable
    _remove_track: Callable
    _resolve_track_genre: Callable
    _small_pool_order: Callable
    _track_cache_key: Callable
    _transition_path_score: Callable
    calculate_transition_objective: Callable
    get_genre_compatibility: Callable
    _sort_harmonic_flow: Callable


class PlaylistStrategies:
    def __init__(self, services: StrategyServices):
        self.services = services

    def _sort_harmonic_flow(self,
        tracks: list[Track], bpm_tolerance: float, **kwargs
    ) -> list[Track]:
        """Enhanced harmonic flow using look-ahead and backtracking to avoid local optima."""
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        if len(tracks) <= 6:
            # Kleine Pools vollständig lösen: ein lokal guter Start kann eine
            # Sackgasse erzeugen, obwohl eine lückenlose gerichtete Kette existiert.
            # Jedes Paar nur einmal bewerten, auch bei bis zu 720 Reihenfolgen.
            edge_scores = {}
            def complete_path_score(order):
                scores = []
                for a, b in zip(order, order[1:]):
                    key = (id(a), id(b))
                    if key not in edge_scores:
                        edge_scores[key] = self.services.calculate_transition_objective(a, b, bpm_tolerance, **kwargs)
                    scores.append(edge_scores[key])
                return sum(score > 0 for score in scores), sum(scores)
            return self.services._small_pool_order(
                tracks,
                complete_path_score,
                cancel_check,
            )

        # Create a local cache specifically to avoid repeated function calls during lookahead
        # and pass it to _find_best_starting_track as well.
        compat_cache = {}

        # Capture kwargs in closure for nested function
        compat_kwargs = kwargs.copy()
        compat_kwargs["compat_cache"] = compat_cache

        def _lookahead_score(
            current: Track, remaining: List[Track], depth: int = 2
        ) -> Tuple[Track, float]:
            """Look ahead to find the best path with given depth."""
            if not remaining or depth <= 0:
                return None, 0.0

            # H6-Fix: Immediate-Scores zuerst berechnen, Rekursion nur fuer die
            # Top-K Kandidaten — reduziert O(n^3) auf O(n^2 * K) bei grossen Listen
            scored = []
            for candidate in remaining:
                self.services._check_cancel(cancel_check)
                cache_key = (self.services._track_cache_key(current), self.services._track_cache_key(candidate))
                if cache_key in compat_cache:
                    immediate_score = compat_cache[cache_key]
                else:
                    immediate_score = self.services.calculate_transition_objective(
                        current, candidate, bpm_tolerance, **kwargs
                    )
                    compat_cache[cache_key] = immediate_score

                if immediate_score == 0:  # Skip incompatible tracks
                    continue
                scored.append((immediate_score, candidate))

            if not scored:
                return None, -1

            scored = heapq.nlargest(
                self.services.LOOKAHEAD_TOP_K,
                scored,
                key=lambda item: item[0],
            )

            best_candidate = None
            best_total_score = -1
            for immediate_score, candidate in scored[:self.services.LOOKAHEAD_TOP_K]:
                self.services._check_cancel(cancel_check)
                future_score = 0.0
                if depth > 1 and len(remaining) > 1:
                    next_remaining = [t for t in remaining if t is not candidate]
                    _, future_score = _lookahead_score(candidate, next_remaining, depth - 1)

                # Konstante statt Literal: derselbe Wert stand hier doppelt, ein
                # Aendern von LOOKAHEAD_FUTURE_WEIGHT haette nur die andere
                # Fundstelle erwischt und die Gewichtung still auseinanderlaufen
                # lassen. Sofort-Score wiegt schwerer als die Vorausschau.
                total_score = immediate_score + self.services.LOOKAHEAD_FUTURE_WEIGHT * future_score
                if total_score > best_total_score:
                    best_total_score = total_score
                    best_candidate = candidate

            return best_candidate, best_total_score

        unprocessed = list(tracks)
        # Start with a track that has good overall connectivity
        start_track = self.services._find_best_starting_track(tracks, bpm_tolerance, **compat_kwargs)
        final_playlist = [start_track]
        self.services._remove_track(unprocessed, start_track)

        current_track = start_track
        while unprocessed:
            self.services._check_cancel(cancel_check)
            best_next, score = _lookahead_score(
                current_track, unprocessed, depth=2
            )  # Optimized: depth=2 (was 3)

            if best_next and score > 0:
                final_playlist.append(best_next)
                self.services._remove_track(unprocessed, best_next)
                current_track = best_next
            else:
                # Fallback (Strategien-Merge 2026-07-17, portiert aus der frueheren
                # Plain-Variante): kein harmonisch kompatibler Kandidat mehr —
                # waehle den Track mit der kleinsten EFFEKTIVEN BPM-Differenz
                # (Half/Double-Time-bewusst) statt roher Kompatibilitaets-Maxima
                fallback = min(
                    unprocessed,
                    key=lambda t: effective_bpm_diff(t.bpm, current_track.bpm)[0],
                )
                final_playlist.append(fallback)
                self.services._remove_track(unprocessed, fallback)
                current_track = fallback

        return final_playlist


    def _sort_directional_bpm(self,
        tracks: list[Track],
        bpm_tolerance: float,
        reverse: bool,
        **kwargs,
    ) -> list[Track]:
        """Sortiert nach BPM und nutzt bei Gleichstand das volle Uebergangsziel."""
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        if len(tracks) <= 1:
            return list(tracks)

        bpm_ordered = sorted(tracks, key=lambda track: track.bpm, reverse=reverse)
        result: list[Track] = []
        position = 0

        while position < len(bpm_ordered):
            self.services._check_cancel(cancel_check)
            reference_bpm = bpm_ordered[position].bpm
            group = []
            while position < len(bpm_ordered) and math.isclose(
                bpm_ordered[position].bpm, reference_bpm, abs_tol=1e-9
            ):
                group.append(bpm_ordered[position])
                position += 1

            if len(group) == 1:
                result.extend(group)
                continue

            remaining = list(group)
            if result:
                current = result[-1]
            else:
                current = max(
                    remaining,
                    key=lambda candidate: sum(
                        self.services.calculate_transition_objective(
                            candidate, other, bpm_tolerance, **kwargs
                        )
                        for other in remaining
                        if other is not candidate
                    ),
                )
                result.append(current)
                self.services._remove_track(remaining, current)

            while remaining:
                self.services._check_cancel(cancel_check)
                def _tie_break_score(candidate: Track) -> float:
                    immediate = self.services.calculate_transition_objective(
                        current, candidate, bpm_tolerance, **kwargs
                    )
                    # AUDIT-FIX 2026-08-14: Guard (len(remaining) > 1) passte nicht
                    # zum Filter (other is not candidate). Steht DASSELBE Track-
                    # Objekt mehrfach in der BPM-Gruppe (Nutzer laedt eine Datei
                    # doppelt), filtert der Generator alle Kopien heraus und max()
                    # lief auf einer leeren Sequenz -> ValueError mitten in
                    # Warm-Up/Cool-Down. default=0.0 ist bei nicht-leerer Sequenz
                    # verhaltensgleich.
                    future = max(
                        (
                            self.services.calculate_transition_objective(
                                candidate, other, bpm_tolerance, **kwargs
                            )
                            for other in remaining
                            if other is not candidate
                        ),
                        default=0.0,
                    )
                    return immediate + self.services.LOOKAHEAD_FUTURE_WEIGHT * future

                next_track = max(remaining, key=_tie_break_score)
                result.append(next_track)
                self.services._remove_track(remaining, next_track)
                current = next_track

        return result


    def _sort_warm_up(self, tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
        """BPM aufsteigend, Harmonik als Tiebreaker innerhalb gleicher BPM."""
        return self._sort_directional_bpm(tracks, bpm_tolerance, reverse=False, **kwargs)


    def _sort_cool_down(self, tracks: list[Track], bpm_tolerance: float, **kwargs) -> list[Track]:
        """BPM absteigend, Harmonik als Tiebreaker innerhalb gleicher BPM."""
        return self._sort_directional_bpm(tracks, bpm_tolerance, reverse=True, **kwargs)


    def _sort_energy_wave(self,
        tracks: list[Track], bpm_tolerance: float, **kwargs
    ) -> list[Track]:
        """Wellenfoermige Reise: abwechselnd hoehere und niedrigere Energie,
        vom Zentrum aus mit wachsendem Ausschlag.

        Die Reihenfolge der Seiten und der wachsende Ausschlag sind unveraendert.
        Neu ist nur die AUSWAHL innerhalb einer Seite: statt immer den
        zentrumsnaechsten Track zu nehmen, wird unter den naechsten
        ENERGY_WAVE_FENSTER Kandidaten der mit der kleinsten effektiven
        BPM-Differenz zum zuletzt gesetzten Track gewaehlt.

        Anlass: die Strategie nahm `bpm_tolerance` entgegen und benutzte sie nie.
        Gemessen an 80 Tracks mit 93-146 BPM waren dadurch 63 % der Nachbarpaare
        unmixbar (Median-BPM-Differenz 10,0) — zum Vergleich liegen Harmonic
        Flow, Warm-Up, Cool-Down und Consistent bei 2-5 %. Bei einem engen Pool
        (137-141 BPM) trat das Problem nicht auf; es trifft, wer die Strategie
        auf einen gemischten Bestand anwendet.

        Innerhalb des Seitenfensters entscheidet zuerst die lokale Uebergangsguete,
        danach BPM-Naehe und Energiesprung. Auch ohne planbare Kante bleiben alle
        Tracks erhalten; die spaetere Kettenplanung kennzeichnet diese UNGEPLANT.
        """
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        if not tracks:
            return []

        ordered_by_energy = sorted(tracks, key=lambda track: track.energy)
        count = len(ordered_by_energy)
        if count <= 2:
            return ordered_by_energy

        center_index = (count - 1) // 2
        result: list[Track] = [ordered_by_energy[center_index]]

        # Zentrumsnaechster Kandidat steht in beiden Listen vorne
        nach_unten = list(reversed(ordered_by_energy[:center_index]))
        nach_oben = ordered_by_energy[center_index + 1:]
        take_high = True

        while nach_unten or nach_oben:
            self.services._check_cancel(cancel_check)
            seite = nach_oben if (take_high and nach_oben) else (
                nach_unten if nach_unten else nach_oben
            )
            if not seite:
                break
            aktuell = result[-1]
            grenze = min(len(seite), max(1, self.services.ENERGY_WAVE_FENSTER))
            # Ueber den INDEX waehlen, nicht ueber den Wert: Track vergleicht
            # sich ueber `track_id`, also den normalisierten Dateipfad
            # (models.py, `__eq__`). Zwei Objekte mit demselben Pfad sind gleich,
            # unabhaengig von BPM und Energie. `list.remove(track)` entfernte
            # deshalb den erstbesten Treffer statt des gewaehlten — im Test mit
            # der Fixture `make_track`, die allen Tracks denselben Default-Pfad
            # gibt, verschwanden dadurch Tracks aus der Playlist.
            #
            # Tie-Break bewusst gegen den ZULETZT GESETZTEN Track, nicht gegen das
            # Zentrum: bei gleicher BPM-Naehe gewinnt der sanftere Energiesprung.
            index = min(
                range(grenze),
                key=lambda i: (
                    -self.services.calculate_transition_objective(aktuell, seite[i], bpm_tolerance, **kwargs),
                    effective_bpm_diff(aktuell.bpm, seite[i].bpm)[0],
                    abs(seite[i].energy - aktuell.energy),
                ),
            )
            result.append(seite.pop(index))
            take_high = not take_high

        return result


    def _sort_peak_time(self,
        tracks: list[Track], bpm_tolerance: float, **kwargs
    ) -> list[Track]:
        """Enhanced peak-time arrangement with harmonic considerations and multiple peaks."""
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        if not tracks:
            return []

        peak_position = kwargs.get("peak_position", 70) / 100.0
        if len(tracks) <= 3:
            combined_by_track = {
                id(track): combined
                for track, combined, _norm_bpm, _norm_energy
                in self.services._prepare_track_metrics(tracks)
            }
            peak_curve = self.services._peak_time_curve(len(tracks), peak_position)

            def small_score(order) -> tuple:
                valid, transition_score = self.services._transition_path_score(
                    order, bpm_tolerance, kwargs
                )
                curve_fit = -sum(
                    abs(combined_by_track[id(track)] - peak_curve[index])
                    for index, track in enumerate(order)
                )
                return valid, curve_fit, transition_score

            return self.services._small_pool_order(tracks, small_score, cancel_check)

        scored_tracks = self.services._prepare_track_metrics(tracks)
        count = len(scored_tracks)

        # Create a double-peak curve for longer sets
        peak_curve = self.services._peak_time_curve(count, peak_position)

        # Sort tracks by curve position preference
        waveform_positions = sorted(range(count), key=lambda idx: peak_curve[idx])

        # Assign tracks to positions with harmonic consideration
        ordered_tracks: list[Optional[Track]] = [None] * count

        # Audit-Fix 2026-07-21: Tracks nach combined_score (Energie+BPM) sortieren,
        # BEVOR sie auf die Peak-Kurve gelegt werden. Vorher lief die Zuweisung ueber
        # den Eingabe-Index -> die Peak-Dramaturgie (ruhige Tracks an Start/Ende,
        # energiereiche am Peak) entstand nie und das Ergebnis haing an der Ladereihenfolge.
        scored_by_energy = sorted(scored_tracks, key=lambda item: item[1])

        for track_idx in zip(scored_by_energy, waveform_positions):
            self.services._check_cancel(cancel_check)
            track, score, norm_bpm, norm_energy = track_idx[0]
            position = track_idx[1]

            if position < len(ordered_tracks):
                ordered_tracks[position] = track

        # Apply harmonic smoothing pass
        result = [track for track in ordered_tracks if track is not None]
        return self.services._apply_harmonic_smoothing(result, bpm_tolerance, **kwargs)


    def _sort_genre_flow(self,
        tracks: list[Track], bpm_tolerance: float, **kwargs
    ) -> list[Track]:
        """Arrange tracks to create smooth genre transitions while maintaining energy."""
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        # Get genre parameters
        genre_mixing_enabled = kwargs.get("genre_mixing", True)
        genre_weight = kwargs.get("genre_weight", 0.3)  # 0.0-1.0

        if len(tracks) <= 2:
            # For 2 oder weniger Tracks wird die Richtung per Vergleich der
            # paarweisen Verträglichkeit eindeutig aufgelöst. ``_sort_harmonic_flow``
            # ist für kleine Pools zu passiv und würde bei [B, A] die Reihenfolge
            # nicht stabil in Richtung des erwarteten Contracts ändern.
            def small_score(order) -> tuple:
                harmonic_scores = [
                    self.services.calculate_transition_objective(a, b, bpm_tolerance, **kwargs)
                    for a, b in zip(order, order[1:])
                ]
                if not genre_mixing_enabled:
                    blended_scores = [
                        harmonic / 100.0 for harmonic in harmonic_scores
                    ]
                else:
                    blended_scores = [
                        (1.0 - genre_weight) * harmonic / 100.0
                        + genre_weight * self.services.get_genre_compatibility(
                            self.services._resolve_track_genre(a), self.services._resolve_track_genre(b)
                        )
                        for (a, b), harmonic in zip(
                            zip(order, order[1:]), harmonic_scores
                        )
                    ]
                return (
                    sum(score > 0 for score in harmonic_scores),
                    sum(blended_scores),
                    sum(harmonic_scores),
                )

            return self.services._small_pool_order(tracks, small_score, cancel_check)

        if not genre_mixing_enabled or genre_weight <= 0.0:
            return self.services._sort_harmonic_flow(tracks, bpm_tolerance, **kwargs)

        # Group tracks by genre (bevorzuge eine echte Klassifikation, sonst ID3)
        genre_groups = {}
        for track in tracks:
            self.services._check_cancel(cancel_check)
            genre = self.services._resolve_track_genre(track)
            if genre == "Unknown":
                genre = "Mixed"
            if genre not in genre_groups:
                genre_groups[genre] = []
            genre_groups[genre].append(track)

        # Audit-Fix 2026-07-17 (Runde 2): die frühere lokale Fallback-Tabelle
        # (base_genre_compatibility) war ein zweites, teils widersprüchliches
        # Duplikat der DJ-Brain-Matrix — entfernt. Einzige Quelle ist jetzt
        # get_genre_compatibility (dj_brain), skaliert mit genre_weight.

        # Create transitions between genres
        result = []
        processed_genres = set()

        # Start with the genre that has the most tracks
        current_genre = max(genre_groups.keys(), key=lambda g: len(genre_groups[g]))

        while len(processed_genres) < len(genre_groups):
            self.services._check_cancel(cancel_check)
            if current_genre in genre_groups and current_genre not in processed_genres:
                # Arrange tracks within current genre (pass kwargs for harmonic params)
                genre_tracks = self._sort_consistent(
                    genre_groups[current_genre], bpm_tolerance, **kwargs
                )
                result.extend(genre_tracks)
                processed_genres.add(current_genre)

            # Find best next genre
            best_next_genre = None
            best_compatibility = 0

            for genre in genre_groups:
                self.services._check_cancel(cancel_check)
                if genre not in processed_genres:
                    # genre_weight blendet zwischen dem besten realen Uebergang
                    # in die Gruppe (0 = Genre ignorieren) und der DJ-Brain-Matrix
                    # (1 = Genre ist ausschlaggebend). Die fruehere affine Formel
                    # war fuer alle Gewichte < 1 streng monoton und konnte deshalb
                    # die Rangfolge niemals veraendern.
                    dj_compat = self.services.get_genre_compatibility(current_genre, genre)
                    current_track = result[-1]
                    transition_compat = 0
                    for candidate in genre_groups[genre]:
                        self.services._check_cancel(cancel_check)
                        transition_compat = max(
                            transition_compat,
                            self.services.calculate_transition_objective(
                                current_track, candidate, bpm_tolerance, **kwargs
                            ),
                        )
                    transition_compat /= 100.0
                    compatibility = (
                        (1.0 - genre_weight) * transition_compat
                        + genre_weight * dj_compat
                    )
                    if compatibility > best_compatibility:
                        best_compatibility = compatibility
                        best_next_genre = genre

            if best_next_genre:
                current_genre = best_next_genre
            else:
                # If no compatible genre found, pick any remaining genre.
                # sorted() statt list(set(...)): Set-Iteration haengt vom
                # PYTHONHASHSEED ab -> sonst nichtdeterministische Playlist-Reihenfolge
                # ueber Programmlaeufe hinweg bei identischem Track-Pool.
                remaining_genres = set(genre_groups.keys()) - processed_genres
                if remaining_genres:
                    current_genre = sorted(remaining_genres)[0]
                else:
                    break  # All genres processed

        return result


    def _sort_consistent(self,
        tracks: list[Track], bpm_tolerance: float, **kwargs
    ) -> list[Track]:
        """Keep transitions smooth by minimising BPM/Energy jumps while preferring harmonic compatibility."""
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        if not tracks:
            return []

        # Capture kwargs for nested function
        compat_kwargs = kwargs

        remaining = list(tracks)
        average_bpm = sum(getattr(track, "bpm", 0.0) for track in remaining) / len(
            remaining
        )
        average_energy = sum(getattr(track, "energy", 0) for track in remaining) / len(
            remaining
        )

        def _center_distance(track: Track) -> float:
            bpm_deviation = effective_bpm_diff(
                getattr(track, "bpm", average_bpm), average_bpm
            )[0]
            energy_deviation = (
                abs(getattr(track, "energy", average_energy) - average_energy) / 5.0
            )
            return bpm_deviation + energy_deviation

        current = min(remaining, key=_center_distance)
        playlist = [current]
        self.services._remove_track(remaining, current)

        while remaining:
            self.services._check_cancel(cancel_check)

            def _transition_cost(candidate: Track) -> float:
                bpm_delta, _ = effective_bpm_diff(
                    getattr(candidate, "bpm", current.bpm), getattr(current, "bpm", 0.0)
                )
                energy_delta = (
                    abs(
                        getattr(candidate, "energy", current.energy)
                        - getattr(current, "energy", 0)
                    )
                    / 5.0
                )
                compatibility = self.services.calculate_transition_objective(
                    current, candidate, bpm_tolerance, **compat_kwargs
                )
                compatibility_penalty = (100 - compatibility) / 8.0
                if compatibility == 0:
                    compatibility_penalty += 10.0
                return bpm_delta + energy_delta + compatibility_penalty

            next_track = min(remaining, key=_transition_cost)
            playlist.append(next_track)
            self.services._remove_track(remaining, next_track)
            current = next_track

        return playlist


    def _sort_context_flow(self,
        tracks: list[Track], bpm_tolerance: float, **kwargs
    ) -> list[Track]:
        """
        Kontext-bewusster Greedy-Sort. Basis ist calculate_transition_objective
        (lokale Kandidatenwerte mit unveraenderten Gates); darauf DJ-Kontext-Modifikatoren,
        portiert aus der frueheren Intelligent-Scoring-Schicht:
          - Set-Phase mit Ziel-Energie (Warm-up 30 / Build 60 / Peak 85 / Cool-down 40)
          - Energie-Trend-Fortfuehrung (steigende Kurve nicht abwuergen)
          - Genre-Fatigue (nach 4 gleichen Genres Wechsel belohnen)
          - Repetition-Penalty (Beinahe-Klone nicht back-to-back)
          - Energie-Cliff-Penalty (Spruenge > 35 Punkte vermeiden)

        Strategien-Merge 2026-07-17: uebernimmt die energy_direction-Presets der
        frueheren "Emotional Journey"-Strategie — "Build Up"/"Cool Down"/"Maintain"
        formen die Zielenergie-Kurve, "Auto" = klassische Set-Dramaturgie.
        """
        cancel_check = kwargs.get("cancel_check")
        self.services._check_cancel(cancel_check)
        if not tracks:
            return []

        raw_energy_dir = str(kwargs.get("energy_direction", "Auto"))
        energy_dir = {
            "auto": "Auto",
            "up": "Build Up",
            "down": "Cool Down",
            "maintain": "Maintain",
        }.get(raw_energy_dir, raw_energy_dir)
        peak_position = max(0.4, min(0.8, float(kwargs.get("peak_position", 70)) / 100.0))
        genre_mixing = bool(kwargs.get("genre_mixing", True))
        genre_weight = max(0.0, min(1.0, float(kwargs.get("genre_weight", 0.3))))
        pool_avg_energy = sum(t.energy for t in tracks) / len(tracks)
        configured_target = kwargs.get("target_energy")
        if configured_target is not None:
            configured_target = max(0.0, min(100.0, float(configured_target)))

        def _target_energy(position: int, total: int) -> float:
            return self.services._context_target_energy(
                position,
                total,
                energy_direction=energy_dir,
                peak_position=peak_position,
                pool_average=pool_avg_energy,
                configured_target=configured_target,
            )

        if len(tracks) <= 2:
            def small_score(order) -> tuple:
                total_score = 0.0
                valid_edges = 0
                for position, track in enumerate(order):
                    self.services._check_cancel(cancel_check)
                    target = _target_energy(position, len(order))
                    total_score += 10.0 - min(30.0, abs(track.energy - target)) / 3.0
                    if position == 0:
                        continue
                    previous = order[position - 1]
                    base = self.services.calculate_transition_objective(
                        previous, track, bpm_tolerance, **kwargs
                    )
                    if base == 0:
                        continue
                    valid_edges += 1
                    total_score += float(base)
                    if genre_mixing and genre_weight > 0.0:
                        genre_compat = self.services.get_genre_compatibility(
                            self.services._resolve_track_genre(previous), self.services._resolve_track_genre(track)
                        )
                        total_score += genre_weight * (genre_compat - 0.5) * 20.0
                    if (
                        abs(track.bpm - previous.bpm) < 0.5
                        and track.camelotCode == previous.camelotCode
                        and abs(track.energy - previous.energy) < 5
                    ):
                        total_score -= 12.0
                    if abs(track.energy - previous.energy) > 35:
                        total_score -= 15.0
                return valid_edges, total_score

            return self.services._small_pool_order(tracks, small_score, cancel_check)

        unprocessed = list(tracks)
        total = len(tracks)
        # Start-Track passend zur Richtung: Build Up/Auto = ruhigster Track,
        # Cool Down = energiereichster, Maintain = naechster am Durchschnitt
        if energy_dir == "Cool Down":
            start = max(unprocessed, key=lambda t: t.energy)
        elif energy_dir == "Maintain":
            start = min(unprocessed, key=lambda t: abs(t.energy - pool_avg_energy))
        else:
            start = min(unprocessed, key=lambda t: t.energy)
        final_playlist = [start]
        self.services._remove_track(unprocessed, start)

        while unprocessed:
            self.services._check_cancel(cancel_check)
            current = final_playlist[-1]
            target_energy = _target_energy(len(final_playlist), total)

            # Energie-Trend aus den letzten 3 Tracks
            recent = [t.energy for t in final_playlist[-3:]]
            trend = recent[-1] - recent[0] if len(recent) >= 2 else 0.0

            # Genre-Streak am Playlist-Ende
            streak_genre = self.services._resolve_track_genre(current)
            streak = 0
            for t in reversed(final_playlist):
                self.services._check_cancel(cancel_check)
                if self.services._resolve_track_genre(t) == streak_genre:
                    streak += 1
                else:
                    break

            best_next = None
            highest_score = -999999.0
            for candidate in unprocessed:
                self.services._check_cancel(cancel_check)
                # Lokale Uebergangsguete als Basis. genre_weight=0 deaktiviert nur
                # die zusaetzlichen Context-Boni, nicht den lokalen Genre-Teilwert.
                base = self.services.calculate_transition_objective(
                    current, candidate, bpm_tolerance, **kwargs
                )
                if base == 0:
                    continue  # BPM-Hard-Gate beibehalten

                score = float(base)
                # Kontextboni ergaenzen die lokale Basis. Harte Kandidatengates
                # werden dadurch nicht umgangen; keine reine Camelot-Stufenlogik.
                # Phase: Naehe zur Ziel-Energie (+10 bei Treffer, faellt linear ab)
                score += 10.0 - min(30.0, abs(candidate.energy - target_energy)) / 3.0
                # Trend-Fortfuehrung: Kandidat setzt erkennbare Richtung fort
                if abs(trend) >= 5.0:
                    cand_delta = candidate.energy - current.energy
                    if (trend > 0) == (cand_delta > 0) and abs(cand_delta) <= 25:
                        score += 5.0
                if genre_mixing and genre_weight > 0.0:
                    # Genre-Matrix wirkt kontinuierlich: bei Gewicht 0 ist Genre
                    # vollstaendig neutral, bei 1 maximal +/-10 Punkte.
                    genre_compat = self.services.get_genre_compatibility(
                        streak_genre, self.services._resolve_track_genre(candidate)
                    )
                    score += genre_weight * (genre_compat - 0.5) * 20.0
                    # Fatigue bleibt ein kleiner Zusatz innerhalb desselben Reglers.
                    if streak >= 4:
                        fatigue = 4.0 if self.services._resolve_track_genre(candidate) != streak_genre else -6.0
                        score += genre_weight * fatigue
                # Repetition-Penalty: Beinahe-Klon direkt hintereinander
                if (
                    abs(candidate.bpm - current.bpm) < 0.5
                    and candidate.camelotCode == current.camelotCode
                    and abs(candidate.energy - current.energy) < 5
                ):
                    score -= 12.0
                # Energie-Cliff
                if abs(candidate.energy - current.energy) > 35:
                    score -= 15.0

                if score > highest_score:
                    highest_score = score
                    best_next = candidate

            if best_next is None:
                best_next = min(
                    unprocessed,
                    key=lambda t: effective_bpm_diff(t.bpm, current.bpm)[0],
                )
            final_playlist.append(best_next)
            self.services._remove_track(unprocessed, best_next)

        return final_playlist
