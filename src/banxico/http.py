"""Cliente HTTP com retry, throttling e tratamento de encoding do site do Banxico."""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import HttpConfig

log = logging.getLogger(__name__)


def decode_html(content: bytes) -> str:
    """O CMS declara utf-8 no <meta>, mas serve bytes em cp1252. Tenta utf-8 e cai para cp1252."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def safe_url(url: str) -> str:
    """Escapa caracteres como { } dos GUIDs sem mexer em ':' e '/'."""
    return quote(url, safe=":/?&=%#")


class HttpClient:
    def __init__(self, cfg: HttpConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers["User-Agent"] = cfg.user_agent
        retry = Retry(
            total=cfg.max_retries,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.cfg.delay_seconds - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str) -> requests.Response:
        self._throttle()
        log.debug("GET %s", url)
        resp = self.session.get(safe_url(url), timeout=self.cfg.timeout_seconds)
        resp.raise_for_status()
        return resp

    def get_html(self, url: str) -> str:
        return decode_html(self.get(url).content)
