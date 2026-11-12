"""The K-Line Lens API client: one method per /v1 endpoint."""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Optional

from ._errors import (
    AuthError,
    BadRequestError,
    KlineLensError,
    NotFoundError,
    PlanError,
    RateLimitError,
    ServiceError,
)
from ._result import Result

__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://klinelens.com"
_RETRY_STATUS = {502, 503, 504}
_ERRORS = {400: BadRequestError, 401: AuthError, 403: PlanError, 404: NotFoundError, 429: RateLimitError}


class Client:
    """A client for the K-Line Lens API.

    >>> from klinelens import Client
    >>> kl = Client()                      # reads KLINELENS_API_KEY
    >>> kl.liquidations(window="1h").data["totals"]

    Every method returns a :class:`Result`: ``.data``, ``.meta``, ``.quota``,
    and ``.to_pandas()`` when pandas is installed.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("KLINELENS_API_KEY")
        if not key:
            raise AuthError(401, "No API key. Pass api_key=... or set KLINELENS_API_KEY. Create one at https://klinelens.com/api.")
        self._key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(0, int(retries))

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r})"

    # ------------------------------------------------------------ the read

    def read(self) -> Result:
        """The read right now: the lean, how its readings vote, each one's side."""
        return self._get("/v1/read")

    def forecast(self, tf: str = "15m") -> Result:
        """The forecast model's latest call for ``tf`` (5m, 15m or 1h; Free reads 15m)."""
        return self._get("/v1/forecast", {"tf": tf})

    # ------------------------------------------------------------ market data

    def snapshot(self) -> Result:
        """The last hour's flow, liquidations and large trades, the book and derivatives now."""
        return self._get("/v1/snapshot")

    def flow(self, window: str = "24h", interval: str = "1h") -> Result:
        """Taker buying and selling per interval, with the running delta (CVD)."""
        return self._get("/v1/flow", {"window": window, "interval": interval})

    def liquidations(self, window: str = "24h", interval: str = "4h", limit: Optional[int] = None) -> Result:
        """Longs and shorts forced closed per interval, and the latest single ones."""
        return self._get("/v1/liquidations", {"window": window, "interval": interval, "limit": limit})

    def whales(
        self,
        window: str = "24h",
        interval: str = "4h",
        min_usd: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> Result:
        """Large single trades ($50,000 and up, or ``min_usd``) per interval, and the latest ones."""
        return self._get("/v1/whales", {"window": window, "interval": interval, "min": min_usd, "limit": limit})

    def book(self, levels: int = 20, window: Optional[str] = None, interval: Optional[str] = None) -> Result:
        """The order book as of the last minute; with ``window``, its history too."""
        return self._get("/v1/book", {"levels": levels, "window": window, "interval": interval})

    def derivatives(self, window: Optional[str] = None, interval: Optional[str] = None) -> Result:
        """Funding, open interest, mark and index now; with ``window``, their history too."""
        return self._get("/v1/derivatives", {"window": window, "interval": interval})

    # ------------------------------------------------------------ the ledger

    def setup(self) -> Result:
        """The ledger's open trade, or ``data`` None when none is open (``meta['reason']``)."""
        return self._get("/v1/setup")

    def ledger(self, limit: Optional[int] = None) -> Result:
        """The ledger's account, totals and latest trades, newest first."""
        return self._get("/v1/ledger", {"limit": limit})

    # ------------------------------------------------------------ transport

    def _get(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Result:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = self.base_url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Accept": "application/json",
            "User-Agent": f"klinelens-python/{__version__}",
        }
        attempt = 0
        while True:
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return Result(_decode(resp.read()), resp.headers)
            except urllib.error.HTTPError as err:
                body = _decode(err.read(), strict=False)
                message = body.get("error") if isinstance(body, dict) else None
                if err.code in _RETRY_STATUS and attempt < self.retries:
                    attempt += 1
                    _pause(attempt)
                    continue
                cls = _ERRORS.get(err.code, ServiceError if err.code >= 500 else KlineLensError)
                raise cls(err.code, message or f"HTTP {err.code}", err.headers) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                if attempt < self.retries:
                    attempt += 1
                    _pause(attempt)
                    continue
                reason = getattr(err, "reason", err)
                raise ServiceError(None, f"Could not reach {self.base_url}: {reason}") from None


def _decode(raw: bytes, strict: bool = True) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        if strict:
            raise ServiceError(None, "The API answered with something that is not JSON.") from None
        return None


def _pause(attempt: int) -> None:
    time.sleep(min(8.0, 0.5 * 2 ** (attempt - 1)) + random.random() * 0.25)
