import sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
import hpg_core.caching as c

print("CACHE_FILE:", c.CACHE_FILE)
print("LOCK_FILE:", c.LOCK_FILE)
