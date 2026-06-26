from app.services.confidence_monitor import camera_capture_profile, preview_write_interval
from app.services.confidence_monitor_manager import DEFAULT_LOW_PERFORMANCE


def test_classroom_mode_is_the_default_confidence_profile() -> None:
    assert DEFAULT_LOW_PERFORMANCE is True

    profile = camera_capture_profile(low_performance=True)

    assert profile.width <= 424
    assert profile.height <= 240
    assert profile.fps <= 12
    assert profile.detect_every_frames >= 2


def test_preview_writes_are_throttled_for_classroom_mode() -> None:
    assert preview_write_interval(low_performance=True) >= 0.75
    assert preview_write_interval(low_performance=False) >= 0.25
