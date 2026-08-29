# Verifikation der Audit-Fixes (Welle 1) — stellt die reproduzierten
# Fehlszenarien aus dem Audit mit dem gefixten Code nach.
import sys
sys.path.insert(0, "/home/claude/hpg-fix")

from hpg_core.dj_brain import (
    calculate_genre_aware_mix_points,
    calculate_paired_mix_points,
    _get_intro_end_from_sections,
    _get_outro_start_from_sections,
)
from hpg_core.models import Track

PASS = []
FAIL = []

def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name}: {detail}")

def sec(label, start, end, energy=50.0):
    return {"label": label, "start_time": float(start), "end_time": float(end),
            "avg_energy": float(energy)}

# --- N1: Head-Fenster-Outro darf outro_start nicht in die Mitte ziehen ---
# Track 480s; Head-Fenster endete bei 360s und hatte dort "outro" gelabelt;
# Tail (360-480) endet auf "drop" (kein echtes Outro).
sections_n1 = [
    sec("intro", 0, 30), sec("main", 30, 150), sec("drop", 150, 300),
    sec("outro", 300, 360),  # Fenster-Artefakt (vor dem analysis-Fix moeglich)
    sec("drop", 360, 480),
]
outro = _get_outro_start_from_sections(sections_n1, 480.0)
check("N1 Outro-Scanner", outro == 480.0,
      f"outro_start={outro} (vorher: 300.0 = Track-Mitte; soll: 480.0 = kein Outro)")

# Und mit ECHTEM Outro am Ende funktioniert es weiter:
sections_ok = sections_n1[:-1] + [sec("main", 360, 440), sec("outro", 440, 480)]
outro_ok = _get_outro_start_from_sections(sections_ok, 480.0)
check("N1 echtes Outro intakt", outro_ok == 440.0, f"outro_start={outro_ok} (soll 440.0)")

# --- B7: Tail-Fenster-Intro darf intro_end nicht ans Ende ziehen ---
sections_b7 = [
    sec("main", 0, 100), sec("drop", 100, 300), sec("unanalysed", 300, 420),
    sec("intro", 420, 460),  # Tail-Artefakt
    sec("main", 460, 600),
]
intro = _get_intro_end_from_sections(sections_b7)
check("B7 Intro-Scanner", intro == 0.0,
      f"intro_end={intro} (vorher: 460.0; soll: 0.0 — erste Section ist kein Intro)")
# Echtes Multi-Section-Intro funktioniert weiter:
intro2 = _get_intro_end_from_sections([sec("intro", 0, 20), sec("intro", 20, 60), sec("main", 60, 300)])
check("B7 echtes Intro intakt", intro2 == 60.0, f"intro_end={intro2} (soll 60.0)")

# --- B4: Mix-In nicht mehr in der 2. Trackhaelfte ---
# 420s-Track: fruehes main (32-160), spaetes build (260-300).
sections_b4 = [
    sec("intro", 0, 32), sec("main", 32, 160, 55), sec("drop", 160, 260, 90),
    sec("build", 260, 300, 60), sec("drop", 300, 388, 92), sec("outro", 388, 420, 30),
]
bpm = 128.0
mi, mo, _, _ = calculate_genre_aware_mix_points(sections_b4, bpm, 420.0, "Tech House", anchor=0.0)
check("B4 Mix-In frueh", mi <= 420.0 * 0.5,
      f"mix_in={mi:.2f} ({mi/420.0*100:.0f}% der Laenge; vorher 270.0 = 64%)")

# --- B5: Mix-Out spaet statt Label-dominiert ---
check("B5 Mix-Out spaet", mo >= 420.0 * 0.6,
      f"mix_out={mo:.2f} ({mo/420.0*100:.0f}%; vorher konnte main@50% gewinnen)")

# --- Phasen-Check: beide Punkte auf dem Phrasengitter (Tech House: 8 Bars) ---
spb = (60.0 / bpm) * 4
grid = spb * 8
for name, t in (("mix_in", mi), ("mix_out", mo)):
    phase = t % grid
    on_grid = min(phase, grid - phase) < 0.006  # 6ms-Toleranz (round auf 2 Dezimalen)
    check(f"Gitter {name}", on_grid, f"t={t:.2f}, Phase={min(phase, grid-phase)*1000:.1f}ms")

# --- B1: Paar-Punkte quantisiert (Track A OHNE Outro-Section) ---
ta = Track(filePath="/a.mp3", fileName="a.mp3", duration=400.0, bpm=128.0,
           detected_genre="Tech House", mix_out_point=360.0, first_downbeat=0.1,
           sections=[sec("main", 0, 400)])
tb = Track(filePath="/b.mp3", fileName="b.mp3", duration=400.0, bpm=128.0,
           detected_genre="Tech House", mix_in_point=30.0, first_downbeat=0.25,
           sections=[sec("intro", 0, 60), sec("main", 60, 400)])
out_a, in_b = calculate_paired_mix_points(ta, tb)
grid_a = (60.0/128.0)*4*8
phase_a = (out_a - 0.1) % grid_a
phase_b = (in_b - 0.25) % grid_a
check("B1 mix_out_a auf Gitter", min(phase_a, grid_a-phase_a) < 0.006,
      f"out_a={out_a} (vorher roh 360.0 off-grid), Phase={min(phase_a, grid_a-phase_a)*1000:.1f}ms")
check("B1 mix_in_b auf Gitter", min(phase_b, grid_a-phase_b) < 0.006,
      f"in_b={in_b}, Phase={min(phase_b, grid_a-phase_b)*1000:.1f}ms")

# --- N4: duration=0 kollabiert nicht mehr ---
t0 = Track(filePath="/z.mp3", fileName="z.mp3", duration=0.0, bpm=128.0,
           mix_out_point=0.0, mix_in_point=0.0)
out0, in0 = calculate_paired_mix_points(t0, tb)
check("N4 duration=0 Guard", out0 == 0.0 and in0 == 30.0,
      f"({out0}, {in0}) — Track-Werte unveraendert (vorher (1.71, 60.0) erfunden)")

# --- N5: Notfall-Fallback respektiert Intro + Gitter ---
# Track nur intro(0-100) + outro(100-200): vorher (30.0, 170.0) — Mix-In im Intro.
sections_n5 = [sec("intro", 0, 100), sec("outro", 100, 200)]
mi5, mo5, _, _ = calculate_genre_aware_mix_points(sections_n5, 120.0, 200.0, "Techno", anchor=0.0)
check("N5 Mix-In nicht im Intro", mi5 >= 100.0 or mo5 > mi5,
      f"mix_in={mi5}, mix_out={mo5} (vorher mix_in=30.0 mitten im Intro)")
check("N5 Fenster gueltig", mo5 > mi5, f"({mi5}, {mo5})")

# --- Regression: Normalfall unveraendert sinnvoll ---
sections_norm = [
    sec("intro", 0, 30), sec("build", 30, 90, 60), sec("drop", 90, 210, 90),
    sec("breakdown", 210, 240, 40), sec("drop", 240, 330, 92), sec("outro", 330, 360, 25),
]
mi_n, mo_n, bi, bo = calculate_genre_aware_mix_points(sections_norm, 128.0, 360.0, "Tech House", anchor=0.0)
check("Normalfall", 30.0 <= mi_n < mo_n <= 330.0 + 0.01,
      f"mix_in={mi_n}, mix_out={mo_n}, bars=({bi},{bo})")

print("\n=== PASS ===")
for p in PASS: print(" ✔", p)
if FAIL:
    print("\n=== FAIL ===")
    for f in FAIL: print(" ✘", f)
    sys.exit(1)
print(f"\n{len(PASS)} Checks bestanden, 0 Fehler.")
