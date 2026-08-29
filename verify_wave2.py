# Verifikation Welle 2 (Scoring) — stellt die Audit-Belege mit gefixtem Code nach.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

from hpg_core.models import effective_bpm_diff, Track
from hpg_core.playlist import (
    _calculate_compatibility_inner, calculate_enhanced_compatibility, EnergyDirection,
    _apply_harmonic_smoothing, calculate_transition_objective,
)
from hpg_core.analysis import get_key_with_confidence, key_confidence_score

PASS, FAIL = [], []
def check(n, c, d=""): (PASS if c else FAIL).append(f"{n}: {d}")

# --- F01: BPM-Gate misst im richtigen Tempo-Raum ---
diff, rel = effective_bpm_diff(140, 73)
check("F01 140vs73", abs(diff - 6.0) < 0.01,
      f"diff={diff:.1f} rel={rel} (vorher 3.0 = 2x zu lax; real 6.0 BPM Anpassung)")
diff2, _ = effective_bpm_diff(128, 128)
check("F01 direct intakt", diff2 == 0.0, f"diff={diff2}")
diff3, rel3 = effective_bpm_diff(174, 87)
check("F01 174vs87 double", abs(diff3) < 0.01, f"diff={diff3} rel={rel3} (echtes Half-Time = 0)")

# --- F03/F04: +1 schlaegt +4; +2 existiert und ist Energy-Boost, kein Clash ---
def mk(cam, bpm=128, energy=50, genre="Techno"):
    return Track(filePath=f"/{cam}.mp3", fileName=f"{cam}.mp3", bpm=bpm, energy=energy,
                 camelotCode=cam, detected_genre=genre)
for strict in (1, 4, 5, 7, 10):
    s_adj = _calculate_compatibility_inner(mk("8A"), mk("9A"), 6.0, harmonic_strictness=strict)  # +-1
    s_p4 = _calculate_compatibility_inner(mk("8A"), mk("12A"), 6.0, harmonic_strictness=strict)   # +4
    check(f"F03 +-1>=+4 (strict {strict})", s_adj >= s_p4, f"adjacent={s_adj} +4={s_p4}")
s_p2 = _calculate_compatibility_inner(mk("8A"), mk("10A"), 6.0, harmonic_strictness=7)  # +2
s_clash = _calculate_compatibility_inner(mk("8A"), mk("6A"), 6.0, harmonic_strictness=7)  # clash
check("F04 +2 Energy-Boost", s_p2 > s_clash and s_p2 >= 70,
      f"+2={s_p2} clash={s_clash} (vorher beide 8)")

# --- F05: AI-Bonus nicht mehr in der Harmonik-Skala (predict-Pfad) ---
from hpg_core.playlist import calculate_compatibility
raw = _calculate_compatibility_inner(mk("8A"), mk("9A"), 6.0)
wrapped = calculate_compatibility(mk("8A"), mk("9A"), 6.0)
check("F05 kein Doppel-Bonus", raw == wrapped, f"inner={raw} wrapper={wrapped} (muessen gleich sein)")

# --- F06: energy_direction als String wirkt jetzt (Enum-Mapping) ---
ta, tb = mk("8A", energy=30), mk("8A", energy=80)
m_up = calculate_enhanced_compatibility(ta, tb, 6.0, energy_direction="Build Up")
m_none = calculate_enhanced_compatibility(ta, tb, 6.0)
check("F06 Build Up wirkt", m_up.energy_flow > m_none.energy_flow,
      f"energy_flow Build Up={m_up.energy_flow:.2f} vs None={m_none.energy_flow:.2f}")
m_enum = calculate_enhanced_compatibility(ta, tb, 6.0, energy_direction=EnergyDirection.UP)
check("F06 String==Enum", abs(m_up.energy_flow - m_enum.energy_flow) < 1e-9,
      f"str={m_up.energy_flow:.3f} enum={m_enum.energy_flow:.3f}")

# --- F12: ID3-Genre-Fallback wirkt (detected_genre 'Unknown' truthy) ---
t_id3_a = Track(filePath="/x.mp3", fileName="x.mp3", bpm=128, camelotCode="8A",
                detected_genre="Unknown", genre="Techno")
t_id3_b = Track(filePath="/y.mp3", fileName="y.mp3", bpm=128, camelotCode="8A",
                detected_genre="Unknown", genre="Techno")
m_id3 = calculate_enhanced_compatibility(t_id3_a, t_id3_b, 6.0)
# Techno<->Techno = 1.0, waehrend Unknown<->Unknown = 0.5
check("F12 ID3-Fallback", m_id3.genre_compatibility > 0.9,
      f"genre_compat={m_id3.genre_compatibility:.2f} (vorher 0.5 konstant)")

# --- F08: harmonic smoothing verschlechtert nicht mehr ---
seq = [mk("1A"), mk("2A"), mk("1B"), mk("12A")]
def chainsum(ts):
    return sum(calculate_transition_objective(ts[i], ts[i+1], 6.0) for i in range(len(ts)-1))
before = chainsum(seq)
out = _apply_harmonic_smoothing(list(seq), 6.0)
after = chainsum(out)
check("F08 kein Kettenverlust", after >= before,
      f"vorher={before} nachher={after} (Audit-Gegenbeispiel fiel 265->250)")

# --- F02: Key-Confidence diskriminiert (peaked vs flach) ---
# Klare A-Minor-artige Chroma vs. flache Chroma
peaked = np.zeros(12); peaked[[9,0,4]] = [1.0, 0.6, 0.7]  # A, C, E ~ A-minor triad
flat = np.ones(12)
kn, km, s_p, mg_p, sn, sm = get_key_with_confidence(peaked)
conf_p = key_confidence_score(s_p, mg_p, kn, km, sn, sm)
kn2, km2, s_f, mg_f, sn2, sm2 = get_key_with_confidence(flat)
conf_f = key_confidence_score(s_f, mg_f, kn2, km2, sn2, sm2)
check("F02 peaked>flach", conf_p > conf_f,
      f"peaked conf={conf_p} (strength/contrast={s_p}) vs flach conf={conf_f} (contrast={s_f})")
check("F02 flach unsicher", conf_f <= 0.4, f"flache Chroma conf={conf_f}")
check("F02 peaked erreichbar", conf_p >= 0.5, f"klarer Key conf={conf_p} (vorher max 0.4)")

print("\n=== PASS ===")
for p in PASS: print(" OK ", p)
if FAIL:
    print("\n=== FAIL ===")
    for f in FAIL: print(" XX ", f)
    sys.exit(1)
print(f"\n{len(PASS)} Checks bestanden, 0 Fehler.")
