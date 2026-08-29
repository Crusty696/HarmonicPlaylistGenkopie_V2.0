# Verifikation Welle 4 (Renderer) — isolierte DSP-Checks der gefixten Stellen.
# Verwendet bewusst die reale Produktionsimplementierung und deren Abhaengigkeiten.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from hpg_core.transition_renderer import (
    _apply_eq_crossfade,
    _apply_soft_limiter,
    EqCrossfadeConfig,
)

PASS, FAIL = [], []
def check(n, c, d=""): (PASS if c else FAIL).append(f"{n}: {d}")

sr = 44100
N = sr  # 1 s Crossfade
rng = np.random.RandomState(0)
# Zwei unkorrelierte Rausch-Segmente (worst case fuer lineare Fades)
a = (rng.randn(N, 2) * 0.2).astype(np.float32)
b = (rng.randn(N, 2) * 0.2).astype(np.float32)

def run(ttype, bpm=128):
    cfg = EqCrossfadeConfig(cf_frames=N, sr=sr, bass_cutoff_hz=200.0,
                            transition_type=ttype, bpm_a=bpm)
    return _apply_eq_crossfade(a.copy(), b.copy(), cfg)

# --- C3: Equal-Power haelt die Mitte lautheitsstabil (kein -3dB-Loch) ---
# Fallback-Crossfade ueber unbekannten Typ
mixed = run("unknown_type")
mid = mixed[N//2 - 1000:N//2 + 1000]
edge = mixed[:2000]
rms_mid = float(np.sqrt(np.mean(mid**2)))
rms_edge = float(np.sqrt(np.mean(edge**2)))
ratio_db = 20*np.log10(rms_mid / (rms_edge + 1e-9))
check("C3 kein Lautheitsloch", abs(ratio_db) < 1.5,
      f"Mitte vs Rand = {ratio_db:+.2f} dB (linear waere ~-3 dB)")

# pro_eq_swap laeuft ohne Clipping-Explosion durch
mixed_pro = run("pro_eq_swap")
check("R-02 pro_eq Peak vernuenftig", float(np.max(np.abs(mixed_pro))) < 1.5,
      f"peak={float(np.max(np.abs(mixed_pro))):.2f}")

# --- N-01: pro_eq_swap Mittelpunkt-RMS — kein -3-dB-Energie-Loch mehr ---
# (Gate-Check aus ARBEITSPLAN Phase 0: pro_eq-Mittelpunkt-RMS). Vorher
# fadeten Mids+Highs mit amplituden-komplementaeren LINEAREN Envelopes ->
# Summenleistung 0.5 = -3.01 dB am Uebergangs-Mittelpunkt.
mid_pro = mixed_pro[N//2 - 1000:N//2 + 1000]
edge_pro = mixed_pro[:2000]
rms_mid_pro = float(np.sqrt(np.mean(mid_pro**2)))
rms_edge_pro = float(np.sqrt(np.mean(edge_pro**2)))
ratio_pro_db = 20*np.log10(rms_mid_pro / (rms_edge_pro + 1e-9))
check("N-01 pro_eq kein Lautheitsloch", abs(ratio_pro_db) < 1.0,
      f"Mitte vs Rand = {ratio_pro_db:+.2f} dB (linear waere ~-3 dB)")

# --- R-04: echo_out beat-synchron + Pegel normiert ---
mixed_echo = run("echo_out", bpm=138)
check("R-04 echo_out kein Clipping", float(np.max(np.abs(mixed_echo))) < 1.2,
      f"peak={float(np.max(np.abs(mixed_echo))):.2f} (vorher bis 1.74x)")

# --- R-06: cold_cut hat Mikro-Fade (kein Sample-Sprung an der Schnittstelle) ---
cut_a = np.ones((N, 2), dtype=np.float32) * 0.8
cut_b = np.ones((N, 2), dtype=np.float32) * -0.8
cut_cfg = EqCrossfadeConfig(
    cf_frames=N, sr=sr, bass_cutoff_hz=200.0,
    transition_type="cold_cut", bpm_a=128,
)
mixed_cut = _apply_eq_crossfade(cut_a, cut_b, cut_cfg)
half = N//2
jump = float(np.max(np.abs(mixed_cut[half] - mixed_cut[half-1])))
raw_jump = float(abs(cut_b[half, 0] - cut_a[half - 1, 0]))
check("R-06 cold_cut Mikro-Fade", jump < raw_jump * 0.1,
      f"Sample-Sprung an Naht={jump:.3f} vs. ohne Fade={raw_jump:.3f}")

# --- R-03: Soft-Limiter (tanh) senkt nicht den ganzen Clip ---
# baue Signal mit einem einzelnen Transienten
sig = (rng.randn(N, 2) * 0.1).astype(np.float32)
sig[N//2] = 1.6  # Transient ueber 0.95
mixed_l = _apply_soft_limiter(sig)
# Rand (nicht ueberschritten) unveraendert?
untouched = np.allclose(mixed_l[:1000], sig[:1000])
check("R-03 Limiter lokal", untouched and float(np.max(np.abs(mixed_l))) <= 1.0 + 1e-6,
      f"Rand unveraendert={untouched}, peak={float(np.max(np.abs(mixed_l))):.3f}")

print("\n=== PASS ===")
for p in PASS: print(" OK ", p)
if FAIL:
    print("\n=== FAIL ===")
    for f in FAIL: print(" XX ", f)
    sys.exit(1)
print(f"\n{len(PASS)} Checks bestanden, 0 Fehler.")
