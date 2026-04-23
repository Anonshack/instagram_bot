"""
tests/test_validators.py — URL validator unit tests

Run with:
    pytest tests/ -v
"""

import pytest
from bot.utils.validators import (
    is_valid_instagram_url,
    parse_instagram_url,
    normalize_url,
    InstagramURLType,
)


# ── Valid URLs ────────────────────────────────────────────────────────────────

VALID_CASES = [
    # (url, expected_type)
    ("https://www.instagram.com/p/ABC123/",        InstagramURLType.POST),
    ("https://instagram.com/p/ABC123/",            InstagramURLType.POST),
    ("https://instagram.com/p/ABC-xyz_12/",        InstagramURLType.POST),
    ("https://www.instagram.com/reel/XYZ789/",     InstagramURLType.REEL),
    ("https://instagram.com/reels/XYZ789/",        InstagramURLType.REEL),
    ("https://instagram.com/stories/john/123456/", InstagramURLType.STORY),
    ("https://instagram.com/tv/abc123/",           InstagramURLType.IGTV),
]

@pytest.mark.parametrize("url,expected_type", VALID_CASES)
def test_valid_urls(url, expected_type):
    valid, url_type = parse_instagram_url(url)
    assert valid is True, f"Expected valid URL: {url}"
    assert url_type == expected_type


# ── Invalid URLs ──────────────────────────────────────────────────────────────

INVALID_CASES = [
    "",
    "not a url",
    "https://twitter.com/p/ABC123/",
    "https://facebook.com/reel/XYZ/",
    "http://instagram.com/",               # root URL, no content path
    "https://instagram.com/explore/",      # not a downloadable path
    "ftp://instagram.com/p/ABC/",          # wrong scheme
    "instagram.com/p/ABC/",               # missing scheme
    "https://phishing-instagram.com/p/A/", # wrong domain
]

@pytest.mark.parametrize("url", INVALID_CASES)
def test_invalid_urls(url):
    valid, _ = parse_instagram_url(url)
    assert valid is False, f"Expected invalid URL: {url!r}"


# ── Normalizer ────────────────────────────────────────────────────────────────

def test_normalize_strips_query():
    url = "https://www.instagram.com/p/ABC123/?utm_source=ig_web_copy_link&igshid=abc"
    result = normalize_url(url)
    assert "?" not in result
    assert "utm_source" not in result


def test_normalize_strips_fragment():
    url = "https://instagram.com/p/ABC123/#comments"
    result = normalize_url(url)
    assert "#" not in result


def test_normalize_upgrades_to_https():
    url = "http://instagram.com/p/ABC123/"
    result = normalize_url(url)
    assert result.startswith("https://")


def test_normalize_preserves_path():
    url = "https://instagram.com/p/ABC123/"
    result = normalize_url(url)
    assert "/p/ABC123/" in result
