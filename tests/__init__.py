"""
Harmonic Playlist Generator - Comprehensive Test Suite

Test coverage for all HPG components:
- Audio analysis (BPM, key, energy)
- Track modeling and compatibility
- Playlist generation algorithms
- Mix point detection
- Export functionality
"""

# Bewusst KEINE Version und KEIN Import hier.
#
# Frueher stand hier ein hartkodiertes __version__ = "3.7.0", das seit dem
# Release 3.7.2 veraltet war und niemand las. Der naheliegende Fix — die
# Version aus hpg_core.app_metadata importieren — ist FALSCH: schon dieser
# eine Import zieht hpg_core/__init__.py und darueber analysis -> caching
# nach. caching.CACHE_FILE wird beim Import festgelegt, und zwar bevor
# conftest.py HPG_CACHE_FILE auf das Test-Verzeichnis setzt. Ergebnis:
# die Cache-Isolation der Tests bricht (test_cache_isolation schlaegt fehl).
#
# Dieses Paket darf auf Modulebene NICHTS aus hpg_core importieren.
