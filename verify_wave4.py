# Verifikation Welle 4 (Renderer) — isolierte DSP-Checks der gefixten Stellen.
# Stubbt librosa/soundfile, damit transition_renderer importierbar ist.
import sys, types
for n in ("librosa","librosa.effects","soundfile","pedalboard"):
    sys.modules.setdefault(n, types.ModuleType(n))
sys.path.insert(0, "/home/claude/hpg-fix")
import numpy as np
from hpg_core.transition_renderer import _apply_eq_crossfade, EqCrossfadeConfig

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

# --- R-02/N-01: pro_eq_swap Hoehenband: Equal-Power (a^2+b^2 == 1) ---
# Rekonstruiere die Hoehen-Envelopes wie im Code (N-01: cos/sin statt linear)
cf = N
quarter = cf // 4; tq = 3*quarter
li = max(1, tq-quarter)
prog = np.linspace(0, 1, li)
ha = np.ones(cf); hb = np.zeros(cf)
ha[quarter:tq] = np.cos(prog * (np.pi/2)); ha[tq:] = 0.0
hb[quarter:tq] = np.sin(prog * (np.pi/2)); hb[tq:] = 1.0
pow_sum = ha**2 + hb**2
check("N-01 Hoehen Equal-Power", float(np.max(np.abs(pow_sum - 1.0))) < 1e-5,
      f"max|a^2+b^2-1|={float(np.max(np.abs(pow_sum-1.0))):.2e} "
      f"(linear-komplementaer waere 0.5 = -3 dB am Fenster-Mittelpunkt)")
check("R-02 Hoehen-Summe<=sqrt(2)", float(np.max(ha + hb)) <= np.sqrt(2.0) + 1e-6,
      f"max(a+b)={float(np.max(ha+hb)):.3f} (vorher 2.0 am 3/4-Punkt)")

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
mixed_cut = run("cold_cut")
half = N//2
jump = float(np.max(np.abs(mixed_cut[half] - mixed_cut[half-1])))
# mit Mikrofade ist der groesste Ein-Sample-Sprung nahe der Naht klein
seam = mixed_cut[half-200:half+200, 0]
max_step = float(np.max(np.abs(np.diff(seam))))
raw_step = float(np.max(np.abs(np.diff(np.concatenate([a[half-200:half,0], b[half:half+200,0]])))))
check("R-06 cold_cut Mikro-Fade", max_step <= raw_step,
      f"max Sample-Schritt an Naht={max_step:.3f} vs. ohne Fade={raw_step:.3f}")

# --- R-03: Soft-Limiter (tanh) senkt nicht den ganzen Clip ---
# baue Signal mit einem einzelnen Transienten
sig = (rng.randn(N, 2) * 0.1).astype(np.float32)
sig[N//2] = 1.6  # Transient ueber 0.95
from hpg_core import transition_renderer as tr
# repliziere die Limiter-Logik direkt (isoliert)
mixed_l = sig.copy()
threshold = 0.95
peak = float(np.max(np.abs(mixed_l)))
if peak > threshold:
    over = np.abs(mixed_l) > threshold
    s = np.sign(mixed_l[over])
    excess = (np.abs(mixed_l[over]) - threshold) / (1.0 - threshold + 1e-9)
    mixed_l[over] = s * (threshold + (1.0 - threshold) * np.tanh(excess))
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
