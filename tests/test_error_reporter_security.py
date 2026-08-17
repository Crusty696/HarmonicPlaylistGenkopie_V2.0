"""
Tests fuer ErrorReporter (JSON-Fehler-Sink) und playlist_security
(Sanitize/Validate-Gate vor der Playlist-Generierung).
"""
import json


from hpg_core.error_reporter import ErrorReporter, MAX_ENTRIES, get_error_reporter
from hpg_core.playlist_security import (
  sanitize_playlist,
  validate_playlist_security,
  validate_track_security,
)
from hpg_core.resource_limits import sanitize_playlist as sanitize_resource_limits
from hpg_core.config import SECURITY_MAX_PLAYLIST_SIZE, SECURITY_MAX_TRACK_DURATION
from tests.fixtures.track_factories import make_track


def make_existing_track(tmp_path, **overrides):
  path = tmp_path / "track.mp3"
  path.write_bytes(b"audio-fixture")
  return make_track(filePath=str(path), **overrides)


class TestErrorReporter:
  def test_log_and_read_roundtrip(self, tmp_path):
    reporter = ErrorReporter(log_dir=str(tmp_path))
    reporter.log_error("analysis", "Testfehler mit Umlauten: äöü", {"folder": "X:\\Musik"})
    errors = reporter.get_recent_errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "analysis"
    assert errors[0]["message"] == "Testfehler mit Umlauten: äöü"

  def test_corrupt_file_returns_empty(self, tmp_path):
    reporter = ErrorReporter(log_dir=str(tmp_path))
    reporter.error_log_file.write_text("{kaputt", encoding="utf-8")
    assert reporter.get_recent_errors() == []
    # und log_error darf trotz korrupter Datei nicht crashen
    reporter.log_error("x", "y")
    assert len(reporter.get_recent_errors()) == 1

  def test_rotation_caps_entries(self, tmp_path):
    reporter = ErrorReporter(log_dir=str(tmp_path))
    for i in range(MAX_ENTRIES + 20):
      reporter.log_error("t", f"msg {i}")
    data = json.loads(reporter.error_log_file.read_text(encoding="utf-8"))
    assert len(data) == MAX_ENTRIES
    assert data[-1]["message"] == f"msg {MAX_ENTRIES + 19}"

  def test_stack_trace_only_inside_except(self, tmp_path):
    reporter = ErrorReporter(log_dir=str(tmp_path))
    reporter.log_error("no_exc", "ohne Exception")
    assert reporter.get_recent_errors()[-1]["stack_trace"] is None
    try:
      raise ValueError("boom")
    except ValueError:
      reporter.log_error("exc", "mit Exception")
    assert "ValueError: boom" in reporter.get_recent_errors()[-1]["stack_trace"]

  def test_singleton(self):
    assert get_error_reporter() is get_error_reporter()

  def test_zero_count_returns_empty_list(self, tmp_path):
    reporter = ErrorReporter(log_dir=str(tmp_path))
    reporter.log_error("analysis", "one")

    assert reporter.get_recent_errors(0) == []

  def test_atomic_write_leaves_no_temporary_file(self, tmp_path):
    reporter = ErrorReporter(log_dir=str(tmp_path))
    reporter.log_error("analysis", "one")

    assert list(tmp_path.glob("*.tmp")) == []


class TestPlaylistSecurity:
  def test_canonical_resource_limits_module_exports_sanitizer(self):
    assert sanitize_resource_limits([]) == []

  def test_sanitize_removes_none_and_invalid(self, tmp_path):
    good = make_existing_track(tmp_path)
    bad = make_track()
    bad.filePath = ""
    result = sanitize_playlist([None, good, bad, None])
    assert result == [good]

  def test_sanitize_removes_overlong_track(self, tmp_path):
    good = make_existing_track(tmp_path)
    too_long = make_existing_track(tmp_path)
    too_long.duration = SECURITY_MAX_TRACK_DURATION + 1
    result = sanitize_playlist([good, too_long])
    assert result == [good]

  def test_sanitize_truncates_oversized_playlist(self, tmp_path):
    tracks = [
      make_existing_track(tmp_path)
      for _ in range(SECURITY_MAX_PLAYLIST_SIZE + 5)
    ]
    result = sanitize_playlist(tracks)
    assert len(result) == SECURITY_MAX_PLAYLIST_SIZE

  def test_validate_rejects_oversized_playlist(self):
    tracks = [make_track() for _ in range(SECURITY_MAX_PLAYLIST_SIZE + 1)]
    assert validate_playlist_security(tracks) is False

  def test_validate_accepts_normal_playlist(self, tmp_path):
    tracks = [make_existing_track(tmp_path) for _ in range(3)]
    assert validate_playlist_security(tracks) is True

  def test_validate_track_rejects_overlong(self, tmp_path):
    t = make_existing_track(tmp_path)
    t.duration = SECURITY_MAX_TRACK_DURATION + 1
    assert validate_track_security(t) is False

  def test_missing_path_is_rejected_consistently(self):
    track = make_track(filePath="")

    assert validate_track_security(track) is False
    assert validate_playlist_security([track]) is False

  def test_nonexistent_path_is_rejected_consistently(self, tmp_path):
    track = make_track(filePath=str(tmp_path / "missing.wav"))

    assert validate_track_security(track) is False
    assert validate_playlist_security([track]) is False

  def test_empty_playlist(self):
    assert sanitize_playlist([]) == []
    assert validate_playlist_security([]) is True
