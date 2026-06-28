import re
from datetime import datetime, timezone

_HASHTAG_RE = re.compile(r"#[A-Za-z0-9_]+")


def fix_mojibake(s: str) -> str:
    """Recover UTF-8 text that was re-escaped as Latin-1 in the FB export."""
    if not s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def extract_hashtags(s: str) -> list[str]:
    return _HASHTAG_RE.findall(s or "")


def epoch_to_dt(n: int) -> datetime:
    return datetime.fromtimestamp(n, tz=timezone.utc)
