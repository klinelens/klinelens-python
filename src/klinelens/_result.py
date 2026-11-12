"""What every call returns: the data, its meta, today's quota, and a table."""
from __future__ import annotations

from typing import Any, Mapping, Optional

# The list in each answer that makes the natural table, in order of preference.
_TABLES = ("points", "events", "trades", "history", "path")


class Result:
    """An API answer. ``data`` and ``meta`` are the envelope's two halves;
    ``result["totals"]`` reads from ``data``."""

    def __init__(self, body: Mapping[str, Any], headers: Any = None) -> None:
        self.data: Any = body.get("data")
        self.meta: dict = dict(body.get("meta") or {})
        limit = _int(headers.get("X-Quota-Limit")) if headers is not None else None
        remaining = _int(headers.get("X-Quota-Remaining")) if headers is not None else None
        self.quota = {"limit": limit, "remaining": remaining}

    def __getitem__(self, key: str) -> Any:
        if not isinstance(self.data, Mapping):
            raise KeyError(key)
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default) if isinstance(self.data, Mapping) else default

    def __repr__(self) -> str:
        keys = list(self.data) if isinstance(self.data, Mapping) else type(self.data).__name__
        return f"Result(data={keys}, quota={self.quota})"

    def to_pandas(self, table: Optional[str] = None):
        """The answer's list as a pandas DataFrame: points, events, trades,
        history or path, whichever it has, or the one named in ``table``.
        Timestamps become UTC datetimes. Needs ``pip install klinelens[pandas]``."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("to_pandas() needs pandas: pip install klinelens[pandas]") from None
        data = self.data if isinstance(self.data, Mapping) else {}
        name = table or next((k for k in _TABLES if isinstance(data.get(k), list)), None)
        if name is None:
            # The book's two sides, as price and size.
            if isinstance(data.get("bids"), list) or isinstance((data.get("now") or {}).get("bids"), list):
                src = data if "bids" in data else data["now"]
                rows = [{"side": side, "price": p, "qty": q} for side in ("bids", "asks") for p, q in src.get(side) or []]
                return pd.DataFrame(rows, columns=["side", "price", "qty"])
            raise ValueError(f"No table in this answer. Choose one of: {', '.join(k for k, v in data.items() if isinstance(v, list)) or 'none'}")
        rows = data.get(name)
        if not isinstance(rows, list):
            raise ValueError(f"{name!r} is not a list in this answer.")
        frame = pd.DataFrame(rows)
        for col in ("at", "openedAt", "closedAt"):
            if col in frame.columns:
                frame[col] = pd.to_datetime(frame[col], utc=True)
        return frame


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
