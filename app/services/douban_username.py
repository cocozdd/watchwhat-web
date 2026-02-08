import re
from urllib.parse import urlparse
from urllib.parse import unquote

PEOPLE_PATH_RE = re.compile(r"(?:^|/)people/([^/?#]+)/?", re.IGNORECASE)


def normalize_douban_username(raw: str) -> str:
    value = unquote((raw or "").strip())
    if not value:
        return ""

    lower = value.lower()
    if "douban.com/mine" in lower:
        return "__mine__"

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = (parsed.path or "").strip()
        if path.lower().startswith("/mine"):
            return "__mine__"
        match = PEOPLE_PATH_RE.search(path)
        if match:
            return match.group(1).strip()
        return ""

    match = PEOPLE_PATH_RE.search(value)
    if match:
        return match.group(1).strip()

    compact = value.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    if compact.lower().startswith("mine"):
        return "__mine__"
    if compact.lower().startswith("people/"):
        parts = compact.split("/")
        if len(parts) >= 2:
            return parts[1].strip()

    if "/" in compact:
        return ""
    return compact.strip()


def infer_sync_media_types(raw: str, normalized_username: str) -> list:
    # Mine-mode links are domain-specific: book mine should not force movie sync.
    if normalized_username == "__mine__":
        value = unquote((raw or "").strip()).lower()
        parsed = urlparse(value)
        host = parsed.netloc or ""
        if "book.douban.com" in host:
            return ["book"]
        if "movie.douban.com" in host:
            return ["movie_tv"]
        return ["movie_tv", "book"]

    return ["movie_tv", "book"]
