import re

from app.core.config import get_settings


def test_cors_regex_allows_common_lan_origins() -> None:
    regex = get_settings().cors_origin_regex

    assert re.search(regex, "http://192.168.1.23:5173")
    assert re.search(regex, "http://10.42.10.8:5173")
    assert not re.search(regex, "http://26.42.10.8:5173")
