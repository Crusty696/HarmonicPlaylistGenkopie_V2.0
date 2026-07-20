import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
import hpg_core.caching as c  # noqa: E402

print("CACHE_FILE:", c.CACHE_FILE)
print("LOCK_FILE:", c.LOCK_FILE)
