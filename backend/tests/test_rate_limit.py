import pytest
from fastapi import HTTPException

from app.core.rate_limit import SlidingWindowLimiter


def test_sliding_window_blocks_after_max() -> None:
    lim = SlidingWindowLimiter(max_events=2, window_sec=60.0)
    lim.hit("a", scope="t")
    lim.hit("a", scope="t")
    with pytest.raises(HTTPException) as ei:
        lim.hit("a", scope="t")
    assert ei.value.status_code == 429
