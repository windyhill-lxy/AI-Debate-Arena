import re

from app.core.config import get_settings


def test_cors_regex_allows_radmin_lan_origin() -> None:
    regex = get_settings().cors_origin_regex

    assert re.search(regex, "http://26.42.10.8:5173")
