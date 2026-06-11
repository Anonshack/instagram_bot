"""
bot/utils/validators.py — URL validation helpers

Broad coverage: accepts any Instagram URL.
Even if a URL doesn't match known patterns, yt-dlp will attempt it — only instagram.com domain is required.
"""

import re
from enum import Enum, auto
from urllib.parse import urlparse


class InstagramURLType(Enum):
    POST = auto()
    REEL = auto()
    STORY = auto()
    IGTV = auto()
    UNKNOWN = auto()


_INSTAGRAM_DOMAIN_RE = re.compile(
    r"^(www\.)?instagram\.com$", re.IGNORECASE
)

# Specific patterns (for type detection)
_PATH_PATTERNS: list[tuple[re.Pattern, InstagramURLType]] = [
    (re.compile(r"^/p/[\w-]+/?"),                       InstagramURLType.POST),
    (re.compile(r"^/reel/[\w-]+/?"),                    InstagramURLType.REEL),
    (re.compile(r"^/reels/[\w-]+/?"),                   InstagramURLType.REEL),
    # Story: with or without ID (e.g. username/123)
    (re.compile(r"^/stories/[\w.]+(/\d+/?)?$"),         InstagramURLType.STORY),
    (re.compile(r"^/tv/[\w-]+/?"),                      InstagramURLType.IGTV),
]

# Paths that must be rejected (not content)
_BLACKLIST_PATHS = re.compile(
    r"^/(explore|accounts|about|legal|privacy|help|press|api|oauth|direct|"
    r"web|graphql|static|embed|favicon|manifest|robots)(/|$)",
    re.IGNORECASE,
)


def parse_instagram_url(url: str) -> tuple[bool, InstagramURLType]:
    """
    Returns (is_valid, url_type).

    Strategy: accept any URL from instagram.com that is not on the blacklist —
    yt-dlp will try to download it.
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, InstagramURLType.UNKNOWN

    if parsed.scheme not in ("http", "https", ""):
        return False, InstagramURLType.UNKNOWN

    if not _INSTAGRAM_DOMAIN_RE.match(parsed.netloc):
        return False, InstagramURLType.UNKNOWN

    path = parsed.path

    # Root URL — content yo'q
    if path in ("", "/"):
        return False, InstagramURLType.UNKNOWN

    # Aniq blacklist
    if _BLACKLIST_PATHS.match(path):
        return False, InstagramURLType.UNKNOWN

    # Type detection
    for pattern, url_type in _PATH_PATTERNS:
        if pattern.match(path):
            return True, url_type

    # Accept as unknown type if it's from instagram.com — yt-dlp will try it
    return True, InstagramURLType.UNKNOWN


def is_valid_instagram_url(url: str) -> bool:
    valid, _ = parse_instagram_url(url)
    return valid


def normalize_url(url: str) -> str:
    """Strip query params & fragments, convert to https."""
    parsed = urlparse(url.strip())
    clean = parsed._replace(query="", fragment="", scheme="https")
    return clean.geturl()
