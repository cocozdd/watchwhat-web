import logging
import re
import subprocess
import time
from html import unescape
from typing import List, Optional, Sequence
from urllib.parse import urlencode
from urllib.parse import urljoin

import httpx

from app.config import get_settings
from app.services.adapters.base import CandidateItem, HistoryPage, SourceAdapter
from app.services.cookie_capture import normalize_cookie_text
from app.services.douban_parser import parse_history_page, parse_subject_candidates, parse_top250_page

logger = logging.getLogger(__name__)

_REALISTIC_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_ANTI_BOT_MARKERS = [
    "sec.douban.com",
    "/misc/sorry",
    "禁止访问",
    "异常请求从你的ip发出",
    "检测到有异常请求",
    "验证码",
    "异常请求",
    "captcha",
    "robot",
    "访问过于频繁",
]

_LOGIN_MARKERS = [
    "登录豆瓣",
    "/accounts/login",
    "accounts.douban.com/passport/login",
]


def _is_anti_bot_page(text: str, url: str = "") -> bool:
    lower = text.lower()
    if "sec.douban.com" in url:
        return True
    for marker in _ANTI_BOT_MARKERS:
        if marker in lower:
            return True
    return False


def _is_login_redirect(text: str, url: str = "") -> bool:
    for marker in _LOGIN_MARKERS:
        if marker in text or marker in url:
            return True
    return False


def _is_valid_collection_page(text: str) -> bool:
    lower = text.lower()
    if "li class=\"item\"" in lower or 'class="item"' in lower:
        return True
    if '/subject/' in lower and ('collect' in lower or '看过' in lower or '读过' in lower or '听过' in lower):
        return True
    return False


class DoubanAdapter(SourceAdapter):
    _PEOPLE_RE = re.compile(r"https?://(?:www\.)?douban\.com/people/([^/\"'?]+)/?", re.IGNORECASE)
    _CONTACT_FRIEND_RE = re.compile(
        r'href="(?:https?://(?:www\.)?douban\.com)?/people/([^/\"?]+)/"',
        re.IGNORECASE,
    )
    _CONTACT_NEXT_START_RE = re.compile(r"/people/[^/]+/contacts\?start=(\d+)", re.IGNORECASE)
    _CONTACT_NEXT_HREF_RE = re.compile(
        r'<span[^>]*class="next"[^>]*>.*?<a[^>]+href="([^"]+)"',
        re.IGNORECASE | re.DOTALL,
    )
    _CONTACT_FRIEND_LINK_RE = re.compile(
        r'<a\b([^>]*?)href="((?:https?://(?:www\.)?douban\.com)?/people/([^/"?]+)/?)"([^>]*)>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    _TITLE_ATTR_RE = re.compile(r'title="([^"]+)"', re.IGNORECASE)

    def __init__(self, client: Optional[httpx.Client] = None):
        self.settings = get_settings()
        self._page_delay = 1.5
        self._last_request_time = 0.0
        self._cookie_username_cache: dict[str, Optional[str]] = {}
        self.client = client or httpx.Client(
            timeout=self.settings.request_timeout,
            headers={
                "User-Agent": _REALISTIC_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
            },
            follow_redirects=True,
        )

    @staticmethod
    def _cookie_headers(cookie: Optional[str]) -> dict:
        normalized = normalize_cookie_text(cookie or "")
        if not normalized:
            return {}
        return {"Cookie": normalized}

    def _throttled_get(self, url: str, **kwargs) -> httpx.Response:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._page_delay:
            time.sleep(self._page_delay - elapsed)
        response = self.client.get(url, **kwargs)
        self._last_request_time = time.monotonic()
        return response

    def _detect_is_own_account(self, username: str, cookie: Optional[str]) -> bool:
        if not cookie or username == "__mine__":
            return username == "__mine__"
        cookie_username = self._detect_cookie_username(cookie)
        if cookie_username and cookie_username == username:
            return True
        return False

    def fetch_history(
        self,
        username: str,
        cookie: Optional[str],
        page_cursor: int,
        media_type: str,
    ) -> HistoryPage:
        if media_type not in {"movie_tv", "book"}:
            raise ValueError(f"Unsupported media_type: {media_type}")

        domain = "movie" if media_type == "movie_tv" else "book"
        mine_mode = username == "__mine__"

        if mine_mode:
            if not cookie:
                raise RuntimeError("Mine-page sync requires login cookie")
            return self._fetch_via_mine(domain=domain, cookie=cookie, page_cursor=page_cursor, media_type=media_type)

        return self._fetch_via_people(
            domain=domain, username=username, cookie=cookie, page_cursor=page_cursor, media_type=media_type,
        )

    def _fetch_via_mine(
        self, domain: str, cookie: str, page_cursor: int, media_type: str,
    ) -> HistoryPage:
        url = f"https://{domain}.douban.com/mine"
        params = {"status": "collect", "start": page_cursor}
        headers = self._cookie_headers(cookie)
        headers["Referer"] = f"https://{domain}.douban.com/"
        response = self._throttled_get(url, params=params, headers=headers)

        if _is_login_redirect(response.text, str(response.url)):
            raise RuntimeError(
                "Mine-page sync requires a valid login cookie. "
                "Cookie may have expired. Please re-capture cookie and retry."
            )
        if _is_anti_bot_page(response.text, str(response.url)):
            raise RuntimeError(
                f"Douban anti-bot blocked /mine request for {media_type} page {page_cursor}. "
                "Please wait a few minutes and retry, or re-capture cookie."
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Douban /mine fetch failed ({response.status_code}) for {media_type} page {page_cursor}")

        if not _is_valid_collection_page(response.text):
            logger.warning(
                "Response from /mine for %s page %d may not be a valid collection page (len=%d)",
                media_type, page_cursor, len(response.text),
            )

        return parse_history_page(response.text, media_type=media_type, current_cursor=page_cursor)

    def _fetch_via_people(
        self, domain: str, username: str, cookie: Optional[str], page_cursor: int, media_type: str,
    ) -> HistoryPage:
        url = f"https://{domain}.douban.com/people/{username}/collect"
        params = {
            "start": page_cursor,
            "sort": "time",
            "rating": "all",
            "filter": "all",
            "mode": "grid",
        }
        cookie_headers = self._cookie_headers(cookie)
        cookie_headers["Referer"] = f"https://{domain}.douban.com/people/{username}/"
        response = self._throttled_get(url, params=params, headers=cookie_headers)
        request_url = f"{url}?{urlencode(params)}"

        if response.status_code == 403 and cookie:
            curl_page = self._fetch_people_collect_via_curl(
                domain=domain,
                username=username,
                cookie=cookie,
                page_cursor=page_cursor,
                media_type=media_type,
                target_url=request_url,
            )
            if curl_page is not None:
                return curl_page
            mine_fallback = self._try_mine_fallback(
                domain=domain, cookie=cookie, page_cursor=page_cursor, media_type=media_type,
            )
            if mine_fallback is not None:
                return mine_fallback

        if response.status_code == 404:
            if cookie:
                cookie_username = self._detect_cookie_username(cookie)
                if cookie_username and cookie_username != username:
                    logger.info(
                        "User '%s' not found on %s.douban.com, retrying with cookie user '%s'",
                        username, domain, cookie_username,
                    )
                    return self._fetch_via_people(
                        domain=domain, username=cookie_username, cookie=cookie,
                        page_cursor=page_cursor, media_type=media_type,
                    )
            raise RuntimeError(
                "Douban user page not found (404). "
                "Use the username from /people/<username>/ or paste the full profile URL."
            )

        if response.status_code >= 400:
            if response.status_code == 403:
                raise RuntimeError(self._format_403_error(response, media_type=media_type, page_cursor=page_cursor))
            raise RuntimeError(f"Douban fetch failed ({response.status_code}) for {media_type} page {page_cursor}")

        if _is_anti_bot_page(response.text, str(response.url)):
            if cookie:
                curl_page = self._fetch_people_collect_via_curl(
                    domain=domain,
                    username=username,
                    cookie=cookie,
                    page_cursor=page_cursor,
                    media_type=media_type,
                    target_url=request_url,
                )
                if curl_page is not None:
                    return curl_page
                logger.warning("Anti-bot detected on /people/ page, falling back to /mine")
                mine_fallback = self._try_mine_fallback(
                    domain=domain, cookie=cookie, page_cursor=page_cursor, media_type=media_type,
                )
                if mine_fallback is not None:
                    return mine_fallback
            raise RuntimeError(
                f"Douban anti-bot blocked request for {media_type} page {page_cursor}. "
                "Please provide a login cookie or wait and retry."
            )

        if _is_login_redirect(response.text, str(response.url)):
            if cookie:
                curl_page = self._fetch_people_collect_via_curl(
                    domain=domain,
                    username=username,
                    cookie=cookie,
                    page_cursor=page_cursor,
                    media_type=media_type,
                    target_url=request_url,
                )
                if curl_page is not None:
                    return curl_page
            logger.warning("Login redirect detected for /people/%s/collect", username)

        if not _is_valid_collection_page(response.text) and page_cursor == 0:
            logger.warning(
                "Response for /people/%s/collect %s page 0 does not look like a collection page (len=%d). "
                "Data may be inaccurate.",
                username, media_type, len(response.text),
            )

        return parse_history_page(response.text, media_type=media_type, current_cursor=page_cursor)

    def _fetch_people_collect_via_curl(
        self,
        domain: str,
        username: str,
        cookie: str,
        page_cursor: int,
        media_type: str,
        target_url: str,
    ) -> Optional[HistoryPage]:
        html = self._fetch_page_via_curl(
            cookie=cookie,
            target_url=target_url,
            referer=f"https://{domain}.douban.com/people/{username}/",
        )
        if not html:
            return None
        parsed = parse_history_page(html, media_type=media_type, current_cursor=page_cursor)
        if parsed.records:
            return parsed
        # treat empty parse as an invalid fallback page, so caller can continue normal error path
        return None

    def fetch_candidate_pool(
        self,
        seed_items: Sequence[CandidateItem],
        cookie: Optional[str] = None,
    ) -> List[CandidateItem]:
        candidates: List[CandidateItem] = []
        seen = set()

        for seed in list(seed_items)[:8]:
            if seed.subject_id in seen:
                continue
            try:
                page = self.client.get(seed.douban_url, headers=self._cookie_headers(cookie))
                if page.status_code >= 400:
                    continue
                parsed = parse_subject_candidates(page.text, default_type=seed.type)
                for candidate in parsed:
                    if candidate.subject_id in seen:
                        continue
                    seen.add(candidate.subject_id)
                    candidate.score = max(candidate.score, seed.score * 0.9)
                    candidates.append(candidate)
            except Exception:
                continue

        if len(candidates) < 20:
            candidates.extend(self._top250_candidates("movie", "movie", seen))
            candidates.extend(self._top250_candidates("book", "book", seen))

        return candidates

    def fetch_friend_usernames(
        self,
        username: str,
        cookie: Optional[str],
        max_count: int = 20,
    ) -> List[str]:
        profiles = self.fetch_friend_profiles(username=username, cookie=cookie, max_count=max_count)
        return [profile["username"] for profile in profiles]

    def fetch_friend_profiles(
        self,
        username: str,
        cookie: Optional[str],
        max_count: int = 20,
    ) -> List[dict]:
        if max_count <= 0:
            return []

        results: List[dict] = []
        seen_order: dict[str, int] = {}
        blocked = {username}
        start = 0
        page_guard = 0
        contacts_url = f"https://www.douban.com/people/{username}/contacts"
        current_url = contacts_url
        current_params: Optional[dict] = {"start": start}
        visited_requests = set()
        while len(results) < max_count and page_guard < 50:
            page_guard += 1
            request_url = current_url
            if current_params:
                request_url = f"{current_url}?{urlencode(current_params)}"
            if request_url in visited_requests:
                break
            visited_requests.add(request_url)

            headers = self._cookie_headers(cookie)
            headers["Referer"] = f"https://www.douban.com/people/{username}/"
            response = self._throttled_get(current_url, params=current_params, headers=headers)

            if response.status_code == 404:
                break
            use_curl_fallback = (
                response.status_code >= 400
                or _is_login_redirect(response.text, str(response.url))
                or _is_anti_bot_page(response.text, str(response.url))
            )

            page_html = response.text
            page_url = str(response.url)
            if use_curl_fallback:
                fallback_html = self._fetch_contacts_via_curl(
                    username=username,
                    cookie=cookie,
                    start=start,
                    target_url=request_url,
                )
                if fallback_html:
                    page_html = fallback_html
                    page_url = request_url
                else:
                    if _is_anti_bot_page(response.text, str(response.url)):
                        raise RuntimeError(
                            "Douban contacts was blocked by anti-bot. "
                            "Please wait and retry, or manually paste friend usernames/URLs."
                        )
                    if response.status_code >= 400:
                        raise RuntimeError(f"Douban contacts fetch failed ({response.status_code}) for {username}")
                    if _is_login_redirect(response.text, str(response.url)):
                        raise RuntimeError("Douban contacts requires login. Please recapture cookie and retry.")
            if _is_anti_bot_page(page_html, page_url):
                raise RuntimeError(
                    "Douban contacts was blocked by anti-bot. "
                    "Please wait and retry, or manually paste friend usernames/URLs."
                )
            if _is_login_redirect(page_html, page_url):
                raise RuntimeError("Douban contacts requires login. Please recapture cookie and retry.")

            page_profiles = self._parse_friend_profiles(page_html)
            for profile in page_profiles:
                friend_username = profile["username"]
                if friend_username in blocked:
                    continue
                existing_idx = seen_order.get(friend_username)
                if existing_idx is not None:
                    existing = results[existing_idx]
                    if self._display_name_quality(profile["display_name"], friend_username) > self._display_name_quality(
                        existing["display_name"],
                        friend_username,
                    ):
                        existing["display_name"] = profile["display_name"]
                        existing["profile_url"] = profile["profile_url"]
                    continue
                seen_order[friend_username] = len(results)
                blocked.add(friend_username)
                results.append(profile)
                if len(results) >= max_count:
                    break

            next_href = self._extract_contacts_next_href(page_html)
            if next_href:
                next_url = urljoin("https://www.douban.com", next_href)
                if "/contacts/list" in next_url:
                    current_url = next_url
                    current_params = None
                    next_start = self._extract_contacts_next_start(page_html, current_start=start)
                    if next_start is not None:
                        start = next_start
                    continue

            next_start = self._extract_contacts_next_start(page_html, current_start=start)
            if next_start is None or next_start <= start:
                break
            start = next_start
            current_url = contacts_url
            current_params = {"start": start}

        return results[:max_count]

    def _fetch_contacts_via_curl(
        self,
        username: str,
        cookie: Optional[str],
        start: int,
        target_url: Optional[str] = None,
    ) -> Optional[str]:
        normalized_cookie = normalize_cookie_text(cookie or "")
        if not normalized_cookie:
            return None

        if not target_url:
            base_url = f"https://www.douban.com/people/{username}/contacts"
            target_url = f"{base_url}?{urlencode({'start': start})}"
        return self._fetch_page_via_curl(
            cookie=normalized_cookie,
            target_url=target_url,
            referer=f"https://www.douban.com/people/{username}/",
        )

    def _fetch_page_via_curl(
        self,
        cookie: str,
        target_url: str,
        referer: str,
    ) -> Optional[str]:
        normalized_cookie = normalize_cookie_text(cookie or "")
        if not normalized_cookie:
            return None

        cmd = [
            "curl",
            "-sS",
            "-L",
            "--compressed",
            "--max-time",
            str(self.settings.request_timeout),
            "-A",
            _REALISTIC_UA,
            "-H",
            f"Cookie: {normalized_cookie}",
            "-H",
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "-H",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            "-H",
            f"Referer: {referer}",
            target_url,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None

        text = proc.stdout or ""
        if not text:
            return None
        if _is_login_redirect(text, target_url) or _is_anti_bot_page(text, target_url):
            return None
        return text

    @classmethod
    def _extract_contacts_next_href(cls, html: str) -> Optional[str]:
        match = cls._CONTACT_NEXT_HREF_RE.search(html)
        if not match:
            return None
        href = (match.group(1) or "").strip()
        return href or None

    @classmethod
    def _parse_friend_usernames(cls, html: str) -> List[str]:
        profiles = cls._parse_friend_profiles(html)
        return [profile["username"] for profile in profiles]

    @classmethod
    def _parse_friend_profiles(cls, html: str) -> List[dict]:
        profiles: List[dict] = []
        seen = {}
        for match in cls._CONTACT_FRIEND_LINK_RE.finditer(html):
            username = (match.group(3) or "").strip()
            if not username:
                continue
            attrs = f"{match.group(1) or ''} {match.group(4) or ''}"
            title_match = cls._TITLE_ATTR_RE.search(attrs)
            title_text = cls._clean_html_text(title_match.group(1)) if title_match else ""
            inner_text = cls._clean_html_text(match.group(5))
            display_name = title_text or inner_text or username
            profile = {
                "username": username,
                "display_name": display_name,
                "profile_url": f"https://www.douban.com/people/{username}/",
            }
            existing_idx = seen.get(username)
            if existing_idx is None:
                seen[username] = len(profiles)
                profiles.append(profile)
                continue
            existing = profiles[existing_idx]
            if cls._display_name_quality(display_name, username) > cls._display_name_quality(
                existing["display_name"],
                username,
            ):
                existing["display_name"] = display_name
                existing["profile_url"] = profile["profile_url"]
        return profiles

    @staticmethod
    def _clean_html_text(raw: str) -> str:
        if not raw:
            return ""
        no_tags = re.sub(r"<[^>]+>", " ", raw)
        compact = re.sub(r"\s+", " ", no_tags).strip()
        return unescape(compact)

    @staticmethod
    def _display_name_quality(display_name: str, username: str) -> int:
        compact_name = (display_name or "").strip().lower()
        compact_username = (username or "").strip().lower()
        if not compact_name:
            return 0
        if compact_name == compact_username:
            return 1
        return 2

    @classmethod
    def _extract_contacts_next_start(cls, html: str, current_start: int) -> Optional[int]:
        candidates = []
        for match in cls._CONTACT_NEXT_START_RE.finditer(html):
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            if value > current_start:
                candidates.append(value)
        if not candidates:
            return None
        return min(candidates)

    _DBCL2_RE = re.compile(r'dbcl2="?(\d+):')

    def _detect_cookie_username(self, cookie: str) -> Optional[str]:
        cache_key = normalize_cookie_text(cookie or "")[:64]
        if cache_key in self._cookie_username_cache:
            return self._cookie_username_cache[cache_key]

        uid = self._extract_dbcl2_uid(cookie)
        if uid:
            canonical = self._resolve_canonical_username(uid, cookie)
            result = canonical or uid
            logger.info("Detected cookie username from dbcl2: %s (uid=%s)", result, uid)
            self._cookie_username_cache[cache_key] = result
            return result

        self._cookie_username_cache[cache_key] = None
        return None

    def _extract_dbcl2_uid(self, cookie: str) -> Optional[str]:
        match = self._DBCL2_RE.search(cookie)
        return match.group(1) if match else None

    def _resolve_canonical_username(self, uid: str, cookie: str) -> Optional[str]:
        try:
            headers = self._cookie_headers(cookie)
            headers["Referer"] = "https://www.douban.com/"
            response = self.client.get(
                f"https://www.douban.com/people/{uid}/", headers=headers,
            )
            final_url = str(response.url)
            match = self._PEOPLE_RE.search(final_url)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        return None

    def _try_mine_fallback(
        self,
        domain: str,
        cookie: str,
        page_cursor: int,
        media_type: str,
    ) -> Optional[HistoryPage]:
        try:
            return self._fetch_via_mine(
                domain=domain, cookie=cookie, page_cursor=page_cursor, media_type=media_type,
            )
        except Exception as exc:
            logger.warning("Mine fallback failed: %s", exc)
            return None

    def _format_403_error(self, response: httpx.Response, media_type: str, page_cursor: int) -> str:
        url_text = str(response.url)
        if "sec.douban.com" in url_text:
            return (
                f"Douban anti-bot blocked request (403) for {media_type} page {page_cursor}. "
                "Please recapture login cookie and retry."
            )
        return f"Douban fetch failed (403) for {media_type} page {page_cursor}"

    def _top250_candidates(self, domain: str, item_type: str, seen: set) -> List[CandidateItem]:
        try:
            url = f"https://{domain}.douban.com/top250?start=0"
            response = self.client.get(url)
            if response.status_code >= 400:
                return []
            parsed = parse_top250_page(response.text, default_type=item_type)
            results = []
            for candidate in parsed:
                if candidate.subject_id in seen:
                    continue
                seen.add(candidate.subject_id)
                results.append(candidate)
                if len(results) >= 40:
                    break
            return results
        except Exception:
            return []
