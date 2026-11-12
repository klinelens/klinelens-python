# klinelens

The Python client for the [K-Line Lens API](https://klinelens.com/api): Bitcoin taker buying and selling, liquidations, large trades, the order book, funding and open interest, in a few lines.

```bash
pip install klinelens            # no dependencies
pip install "klinelens[pandas]"  # adds .to_pandas()
```

Create a key at [klinelens.com/api](https://klinelens.com/api). The free plan needs no card.

```python
from klinelens import Client

kl = Client()   # reads KLINELENS_API_KEY; or Client("kll_live_...")

snap = kl.snapshot()
print(snap["lastHour"]["liquidations"])   # {'longUsd': ..., 'shortUsd': ..., 'count': ...}

flow = kl.flow(window="24h", interval="1h").to_pandas()
print(flow[["at", "deltaUsd", "cumulativeUsd"]].tail())
```

## Methods

| Method | Endpoint | What it returns |
|---|---|---|
| `read()` | `/v1/read` | The read right now: the lean, how its readings vote, each one's side |
| `forecast(tf="15m")` | `/v1/forecast` | The forecast model's latest call and its path |
| `snapshot()` | `/v1/snapshot` | The last hour's flow, liquidations and large trades, the book and derivatives now |
| `flow(window, interval)` | `/v1/flow` | Taker buys and sells per interval, the delta and its running total (CVD) |
| `liquidations(window, interval, limit)` | `/v1/liquidations` | Longs and shorts forced closed per interval, and the latest ones |
| `whales(window, interval, min_usd, limit)` | `/v1/whales` | Trades of $50,000 and up per interval, and the latest ones |
| `book(levels, window, interval)` | `/v1/book` | The order book now, and its history with `window` |
| `derivatives(window, interval)` | `/v1/derivatives` | Funding, open interest, mark and index, and their history with `window` |
| `setup()` | `/v1/setup` | The ledger's open trade, or `None` |
| `ledger(limit)` | `/v1/ledger` | The ledger's account, totals and latest trades |

`window` is a number and `m`, `h` or `d` (`90m`, `24h`, `7d`). `interval` is one of `1m`, `5m`, `15m`, `1h`, `4h`, `1d`. How far back you can read, the smallest interval and how many events are listed depend on your plan; `result.meta["plan"]` says what yours allows.

## What you get back

Every method returns a `Result`:

- `result.data`: the answer. `result["totals"]` reads from it.
- `result.meta`: when it was made, the window, any gaps in the record, your plan's limits.
- `result.quota`: `{"limit": ..., "remaining": ...}` requests for today (UTC).
- `result.to_pandas()`: the answer's list (points, events, trades, history or path) as a DataFrame, timestamps in UTC. Name one with `to_pandas("events")`.

## Errors

Failures raise a subclass of `klinelens.KlineLensError`, with `.status` and `.message`:

| Error | When |
|---|---|
| `BadRequestError` | 400: a parameter is wrong; the message says which |
| `AuthError` | 401: no key, or not a valid one |
| `PlanError` | 403: outside your plan (more history, a smaller interval) |
| `RateLimitError` | 429: today's requests are used up; they reset at 00:00 UTC |
| `ServiceError` | 5xx or no connection, after two retries |

```python
from klinelens import Client, PlanError

try:
    Client().flow(window="30d", interval="1m")
except PlanError as e:
    print(e.message)   # "Your plan reads 1 day of history. ..."
```

## Good to know

- Order flow, liquidations, large trades and the book come from one major exchange's Bitcoin perpetual market. Totals across every exchange are larger.
- Readings describe the market; they are not financial advice. The ledger places no real orders.
- The full API reference, and the OpenAPI description at `https://klinelens.com/v1/openapi.json`, are linked from [klinelens.com/api](https://klinelens.com/api).

MIT licence.
