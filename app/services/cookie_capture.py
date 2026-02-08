import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
from uuid import uuid4

from app.config import get_settings

COOKIE_ATTR_NAMES = {
    "path",
    "domain",
    "expires",
    "max-age",
    "secure",
    "httponly",
    "samesite",
    "priority",
    "partitioned",
}


def normalize_cookie_text(cookie: str) -> str:
    if not cookie:
        return ""

    jar: Dict[str, str] = {}
    for part in cookie.split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        key = name.strip()
        val = value.strip()
        if not key or not val:
            continue
        if key.lower() in COOKIE_ATTR_NAMES:
            continue
        jar[key] = val

    return "; ".join(f"{name}={value}" for name, value in jar.items())


def extract_cookie_text(cookies: Iterable[dict]) -> str:
    pairs = []
    for cookie in cookies:
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", "")).strip()
        if not name or not value:
            continue
        pairs.append(f"{name}={value}")
    return normalize_cookie_text("; ".join(pairs))


def has_login_cookie(cookie_names: Iterable[str]) -> bool:
    lowered = {name.lower().strip() for name in cookie_names if name}
    return "dbcl2" in lowered


@dataclass
class CookieCaptureStatus:
    job_id: str
    status: str
    message: str
    has_cookie: bool


class CookieCaptureManager:
    def __init__(
        self,
        persist_path: Optional[str] = None,
        enable_persistence: Optional[bool] = None,
    ):
        settings = get_settings()
        self._cookies: Dict[str, str] = {}
        self._captures: Dict[str, CookieCaptureStatus] = {}
        self._lock = threading.Lock()
        self._persist_enabled = (
            bool(enable_persistence) if enable_persistence is not None else bool(settings.persist_cookie_on_disk)
        )
        self._persist_path = Path(persist_path or settings.cookie_store_path)
        self._load_persisted_cookies()

    def set_cookie(self, source: str, cookie: str) -> None:
        normalized = normalize_cookie_text(cookie)
        if not normalized:
            return
        with self._lock:
            self._cookies[source] = normalized
            snapshot = dict(self._cookies)
        self._persist_cookies(snapshot)

    def get_cookie(self, source: str) -> Optional[str]:
        with self._lock:
            return self._cookies.get(source)

    def clear_cookie(self, source: str) -> None:
        with self._lock:
            self._cookies.pop(source, None)
            snapshot = dict(self._cookies)
        self._persist_cookies(snapshot)

    def start_auto_capture(self, source: str) -> CookieCaptureStatus:
        job_id = str(uuid4())
        status = CookieCaptureStatus(
            job_id=job_id,
            status="running",
            message="已启动自动捕获，请在弹出的浏览器窗口登录豆瓣。",
            has_cookie=False,
        )
        with self._lock:
            self._captures[job_id] = status

        thread = threading.Thread(target=self._run_capture, args=(job_id, source), daemon=True)
        thread.start()
        return status

    def get_capture_status(self, job_id: str) -> CookieCaptureStatus:
        with self._lock:
            status = self._captures.get(job_id)
        if status is None:
            raise KeyError(job_id)
        return status

    def _run_capture(self, job_id: str, source: str) -> None:
        try:
            try:
                from playwright.sync_api import sync_playwright  # type: ignore
            except ImportError:
                self._set_capture_status(
                    job_id=job_id,
                    status="failed",
                    message=(
                        "未安装 playwright。请执行: "
                        "source .venv/bin/activate && pip install playwright && playwright install chromium"
                    ),
                    has_cookie=False,
                )
                return

            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=False)
                except Exception as exc:
                    self._set_capture_status(
                        job_id=job_id,
                        status="failed",
                        message=(
                            f"浏览器启动失败: {exc}. "
                            "请执行: source .venv/bin/activate && playwright install chromium"
                        ),
                        has_cookie=False,
                    )
                    return

                context = browser.new_context()
                page = context.new_page()
                page.goto("https://www.douban.com/", wait_until="domcontentloaded")
                self._set_capture_status(
                    job_id=job_id,
                    status="running",
                    message="请在弹出窗口完成豆瓣登录，系统会自动检测 Cookie。",
                    has_cookie=False,
                )

                timeout_seconds = 300
                start_time = time.time()
                saw_guest_cookie = False
                while time.time() - start_time < timeout_seconds:
                    cookies = context.cookies(
                        ["https://www.douban.com", "https://movie.douban.com", "https://book.douban.com"]
                    )
                    cookie_names = [str(c.get("name", "")) for c in cookies if c.get("name")]
                    cookie_text = extract_cookie_text(cookies)
                    if cookie_text and has_login_cookie(cookie_names):
                        self.set_cookie(source, cookie_text)
                        self._set_capture_status(
                            job_id=job_id,
                            status="done",
                            message="已捕获登录态 Cookie（dbcl2）。后续同步可自动使用。",
                            has_cookie=True,
                        )
                        context.close()
                        browser.close()
                        return

                    if any(name.lower().strip() == "bid" for name in cookie_names):
                        saw_guest_cookie = True
                    time.sleep(2)

                context.close()
                browser.close()
                timeout_message = "超时未检测到登录态 Cookie（dbcl2），请确认已登录豆瓣。"
                if saw_guest_cookie:
                    timeout_message = "仅检测到访客 Cookie（bid），未检测到登录态 Cookie（dbcl2）。请在弹窗完成登录后重试。"
                self._set_capture_status(
                    job_id=job_id,
                    status="failed",
                    message=timeout_message,
                    has_cookie=False,
                )
        except Exception as exc:
            self._set_capture_status(
                job_id=job_id,
                status="failed",
                message=f"自动捕获失败: {exc}",
                has_cookie=False,
            )

    def _set_capture_status(self, job_id: str, status: str, message: str, has_cookie: bool) -> None:
        with self._lock:
            self._captures[job_id] = CookieCaptureStatus(
                job_id=job_id,
                status=status,
                message=message,
                has_cookie=has_cookie,
            )

    def _load_persisted_cookies(self) -> None:
        if not self._persist_enabled:
            return
        try:
            if not self._persist_path.exists():
                return
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            loaded: Dict[str, str] = {}
            for source, cookie_text in raw.items():
                if not isinstance(source, str) or not isinstance(cookie_text, str):
                    continue
                normalized = normalize_cookie_text(cookie_text)
                if not normalized:
                    continue
                loaded[source] = normalized
            with self._lock:
                self._cookies.update(loaded)
        except Exception:
            return

    def _persist_cookies(self, cookies: Dict[str, str]) -> None:
        if not self._persist_enabled:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return


cookie_capture_manager = CookieCaptureManager()
