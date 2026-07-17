"""Validierungslauf mit echter Musik (2026-07-17).

Zieht eine gleichmaessig verteilte Stichprobe aus zwei Beatport-Ordnern,
analysiert sie ueber die volle HPG-Pipeline (Multi-Core) und vergleicht
die Ergebnisse mit der Ground-Truth aus den Beatport-Dateinamen
(BPM, Genre, Key). Erzeugt Playlists, Qualitaets-Benchmark aller
Strategien und 3 anhoerbare Transition-Previews.

Aufruf: venv312\\Scripts\\python.exe tools\\validation_run.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FOLDERS = {
    "Techno": r"D:\neue techno sammlung nur beatport musik",
    "Psytrance": r"D:\neue Psy-Trance, Progressive nur Beatport musik",
}
SAMPLE_PER_FOLDER = 20
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "validation_output")
AUDIO_EXT = (".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a")

# Beatport-Dateiname: ..._122__(Tech_House)_E_Minor_17_10.aiff
GT_RE = re.compile(r"_(\d{2,3})__\(([^)]+)\)_([A-G][#b]?)_(Minor|Major)_")
FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def sample_folder(path: str, n: int) -> list[str]:
    files = sorted(
        f for f in os.listdir(path) if f.lower().endswith(AUDIO_EXT)
    )
    if len(files) <= n:
        return [os.path.join(path, f) for f in files]
    stride = len(files) / n
    return [os.path.join(path, files[int(i * stride)]) for i in range(n)]


def parse_ground_truth(file_path: str) -> dict:
    m = GT_RE.search(os.path.basename(file_path))
    if not m:
        return {}
    bpm = float(m.group(1))
    genre = m.group(2).replace("_", " ")
    note = FLAT_TO_SHARP.get(m.group(3), m.group(3))
    mode = m.group(4)
    return {"bpm": bpm, "genre": genre, "note": note, "mode": mode}


def camelot_distance(code_a: str, code_b: str):
    from hpg_core.models import get_camelot_components
    n1, l1 = get_camelot_components(code_a)
    n2, l2 = get_camelot_components(code_b)
    if not n1 or not n2:
        return None
    dist = min(abs(n1 - n2), 12 - abs(n1 - n2))
    return dist, l1 == l2


def classify_key_result(detected_code: str, truth_code: str) -> str:
    if detected_code == truth_code:
        return "exakt"
    d = camelot_distance(detected_code, truth_code)
    if d is None:
        return "unbewertbar"
    dist, same_mode = d
    if dist == 0 and not same_mode:
        return "relative (harmlos)"
    if dist == 1 and same_mode:
        return "quinte (harmlos)"
    return "falsch"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = time.time()

    from hpg_core.models import CAMELOT_MAP
    from hpg_core.parallel_analyzer import ParallelAnalyzer
    from hpg_core.playlist import (
        generate_playlist,
        calculate_playlist_quality,
        compute_transition_recommendations,
        benchmark_algorithms,
    )
    from hpg_core.transition_renderer import TransitionClipSpec, render_transition_clip

    report: dict = {"folders": {}, "started": time.strftime("%Y-%m-%d %H:%M")}

    for label, folder in FOLDERS.items():
        files = sample_folder(folder, SAMPLE_PER_FOLDER)
        print(f"[{label}] {len(files)} Tracks (Stichprobe aus {folder})", flush=True)

        analyzer = ParallelAnalyzer()
        tracks = [
            t for t in analyzer.analyze_files(
                files,
                progress_callback=lambda c, t_, msg: print(f"  {c}/{t_} {msg}", flush=True),
            )
            if t is not None
        ]
        print(f"[{label}] analysiert: {len(tracks)}/{len(files)}", flush=True)

        # --- Ground-Truth-Vergleich ---
        gt_rows = []
        for tr in tracks:
            gt = parse_ground_truth(tr.filePath)
            row = {
                "file": os.path.basename(tr.filePath)[:70],
                "bpm_detected": tr.bpm,
                "key_detected": tr.camelotCode,
                "key_confidence": tr.key_confidence,
                "lufs": tr.lufs,
                "first_downbeat": tr.first_downbeat,
                "downbeat_confidence": tr.downbeat_confidence,
                "genre_detected": tr.detected_genre,
                "mix_in": tr.mix_in_point,
                "mix_out": tr.mix_out_point,
            }
            if gt:
                truth_code = CAMELOT_MAP.get((gt["note"], gt["mode"]), "")
                bpm_diff = min(
                    abs(tr.bpm - gt["bpm"]),
                    abs(tr.bpm - gt["bpm"] * 2),
                    abs(tr.bpm - gt["bpm"] / 2),
                )
                row.update({
                    "bpm_truth": gt["bpm"],
                    "bpm_ok": bpm_diff <= 0.5,
                    "key_truth": truth_code,
                    "key_result": classify_key_result(tr.camelotCode, truth_code),
                    "genre_truth": gt["genre"],
                })
            gt_rows.append(row)

        with_gt = [r for r in gt_rows if "bpm_truth" in r]
        bpm_ok = sum(1 for r in with_gt if r["bpm_ok"])
        key_counts: dict = {}
        for r in with_gt:
            key_counts[r["key_result"]] = key_counts.get(r["key_result"], 0) + 1

        # --- Playlist + Qualitaet ---
        playlist = generate_playlist(list(tracks), "Context Flow", bpm_tolerance=6.0)
        quality = calculate_playlist_quality(playlist, 6.0)
        bench = benchmark_algorithms(list(tracks), 6.0)
        bench_scores = {
            k: round(v.get("overall_score", 0), 3) for k, v in bench.items()
        }

        recs = compute_transition_recommendations(playlist, bpm_tolerance=6.0)

        # --- 3 Previews rendern (Anfang / Mitte / Ende der Playlist) ---
        preview_files = []
        idxs = [1, len(recs) // 2, len(recs) - 2] if len(recs) >= 4 else list(range(len(recs)))
        for i in sorted(set(max(0, i) for i in idxs)):
            rec = recs[i]
            dj = rec.dj_rec
            mix_out = (
                dj.adjusted_mix_out_a if dj and dj.adjusted_mix_out_a >= 0.0
                else float(rec.from_track.mix_out_point or 0)
            )
            mix_in = (
                dj.adjusted_mix_in_b if dj and dj.adjusted_mix_in_b >= 0.0
                else float(rec.to_track.mix_in_point or 0)
            )
            crossfade = (
                dj.overlap_seconds if dj and dj.overlap_seconds > 0
                else float(rec.overlap or 16.0)
            )
            out_path = os.path.join(OUT_DIR, f"preview_{label}_{i:02d}.wav")
            try:
                spec = TransitionClipSpec(
                    track_a_path=rec.from_track.filePath,
                    track_b_path=rec.to_track.filePath,
                    mix_out_sec=mix_out,
                    mix_in_sec=mix_in,
                    crossfade_sec=crossfade,
                    transition_type=(dj.transition_type if dj else "smooth_blend"),
                    bpm_a=float(rec.from_track.bpm or 120.0),
                    bpm_b=float(rec.to_track.bpm or 120.0),
                    first_downbeat_a=float(rec.from_track.first_downbeat or 0.0),
                    first_downbeat_b=float(rec.to_track.first_downbeat or 0.0),
                )
                render_transition_clip(spec, out_path)
                preview_files.append({
                    "file": os.path.basename(out_path),
                    "from": rec.from_track.title,
                    "to": rec.to_track.title,
                    "crossfade_sec": round(crossfade, 1),
                    "notes": (rec.notes or "")[:400],
                })
                print(f"[{label}] Preview gerendert: {out_path}", flush=True)
            except Exception as e:
                print(f"[{label}] Preview {i} fehlgeschlagen: {e}", flush=True)

        report["folders"][label] = {
            "sample_size": len(files),
            "analyzed": len(tracks),
            "ground_truth_tracks": len(with_gt),
            "bpm_correct": f"{bpm_ok}/{len(with_gt)}",
            "key_results": key_counts,
            "avg_key_confidence": round(
                sum(r["key_confidence"] for r in gt_rows) / max(1, len(gt_rows)), 3
            ),
            "downbeat_detected": sum(1 for r in gt_rows if r["first_downbeat"] > 0),
            "avg_lufs": round(
                sum(r["lufs"] for r in gt_rows if r["lufs"] < 0)
                / max(1, sum(1 for r in gt_rows if r["lufs"] < 0)), 2
            ),
            "playlist_quality_context_flow": {
                k: round(v, 3) for k, v in quality.items()
            },
            "strategy_benchmark_overall": bench_scores,
            "playlist_order": [os.path.basename(t.filePath)[:70] for t in playlist],
            "previews": preview_files,
            "tracks": gt_rows,
        }

    report["runtime_seconds"] = round(time.time() - t0, 1)
    out_json = os.path.join(OUT_DIR, "validation_report.json")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"\nFERTIG in {report['runtime_seconds']}s -> {out_json}", flush=True)


if __name__ == "__main__":
    main()
