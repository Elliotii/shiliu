from shiliu.bilibili import _duration_seconds


def test_normalized_duration_seconds_and_display_duration_are_supported() -> None:
    assert _duration_seconds(867) == 867
    assert _duration_seconds("14:27") == 867
    assert _duration_seconds("01:14:27") == 4467
    assert _duration_seconds("unknown") == 0

