"""E2E：首页创建房间 → 辩论室首条流式或已发布发言（Python Playwright，无需 Node）。"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_create_room_and_first_stream(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")

    page.get_by_test_id("home-enter-room").click()
    page.wait_for_url(re.compile(r"/room/(?!demo)"), timeout=30_000)

    board = page.get_by_test_id("debate-message-board")
    expect(board).to_be_visible()

    streaming = page.get_by_test_id("debate-streaming")
    published = page.locator(".message-board .message .md-body")

    expect(streaming.or_(published.first)).to_be_visible(timeout=90_000)

    if streaming.is_visible():
        expect(streaming.locator(".md-body")).not_to_be_empty()
    else:
        expect(published.first).not_to_be_empty()
