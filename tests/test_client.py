"""The client against a local server that answers like the API."""
import json
import os
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import klinelens  # noqa: E402
from klinelens import AuthError, BadRequestError, Client, PlanError, RateLimitError, ServiceError  # noqa: E402

SEEN = []          # (path, query, headers) of every request
SCRIPT = {}        # path -> list of (status, body) answered in turn; the last repeats


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        SEEN.append((u.path, parse_qs(u.query), dict(self.headers)))
        queue = SCRIPT.get(u.path) or [(200, {"data": {"path": u.path}, "meta": {"version": "v1"}})]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Quota-Limit", "100")
        self.send_header("X-Quota-Remaining", "97")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        SEEN.clear()
        SCRIPT.clear()
        klinelens._client._pause = lambda attempt: None   # no waiting between retries here
        self.kl = Client("kll_live_test", base_url=self.base)

    def test_key_in_the_header_never_the_url(self):
        self.kl.read()
        path, query, headers = SEEN[0]
        self.assertEqual(path, "/v1/read")
        self.assertEqual(headers["Authorization"], "Bearer kll_live_test")
        self.assertNotIn("key", query)
        self.assertTrue(headers["User-Agent"].startswith("klinelens-python/"))

    def test_key_from_the_environment_or_a_clear_error(self):
        os.environ["KLINELENS_API_KEY"] = "kll_live_env"
        try:
            Client(base_url=self.base).snapshot()
            self.assertEqual(SEEN[0][2]["Authorization"], "Bearer kll_live_env")
        finally:
            del os.environ["KLINELENS_API_KEY"]
        with self.assertRaises(AuthError):
            Client(base_url=self.base)

    def test_each_method_asks_its_endpoint_with_its_parameters(self):
        calls = [
            (lambda: self.kl.forecast("1h"), "/v1/forecast", {"tf": ["1h"]}),
            (lambda: self.kl.flow("7d", "4h"), "/v1/flow", {"window": ["7d"], "interval": ["4h"]}),
            (lambda: self.kl.liquidations("1h", "15m", 10), "/v1/liquidations", {"window": ["1h"], "interval": ["15m"], "limit": ["10"]}),
            (lambda: self.kl.whales(min_usd=250000), "/v1/whales", {"window": ["24h"], "interval": ["4h"], "min": ["250000"]}),
            (lambda: self.kl.book(), "/v1/book", {"levels": ["20"]}),
            (lambda: self.kl.book(5, "2h", "1h"), "/v1/book", {"levels": ["5"], "window": ["2h"], "interval": ["1h"]}),
            (lambda: self.kl.derivatives(), "/v1/derivatives", {}),
            (lambda: self.kl.setup(), "/v1/setup", {}),
            (lambda: self.kl.ledger(5), "/v1/ledger", {"limit": ["5"]}),
        ]
        for call, path, query in calls:
            SEEN.clear()
            call()
            self.assertEqual((SEEN[0][0], SEEN[0][1]), (path, query), path)

    def test_result_data_meta_and_quota(self):
        SCRIPT["/v1/liquidations"] = [(200, {"data": {"totals": {"count": 3}}, "meta": {"interval": "4h"}})]
        r = self.kl.liquidations()
        self.assertEqual(r["totals"]["count"], 3)
        self.assertEqual(r.meta["interval"], "4h")
        self.assertEqual(r.quota, {"limit": 100, "remaining": 97})

    def test_null_data_is_kept(self):
        SCRIPT["/v1/setup"] = [(200, {"data": None, "meta": {"reason": "No trade is open right now."}})]
        r = self.kl.setup()
        self.assertIsNone(r.data)
        self.assertEqual(r.meta["reason"], "No trade is open right now.")
        self.assertIsNone(r.get("entry"))

    def test_errors_by_status(self):
        for status, cls in [(400, BadRequestError), (401, AuthError), (403, PlanError), (429, RateLimitError)]:
            SCRIPT["/v1/flow"] = [(status, {"error": f"said {status}"})]
            with self.assertRaises(cls) as ctx:
                self.kl.flow()
            self.assertEqual((ctx.exception.status, ctx.exception.message), (status, f"said {status}"))

    def test_a_restart_is_retried_then_answers(self):
        SCRIPT["/v1/read"] = [(503, {"error": "restarting"}), (503, {"error": "restarting"}), (200, {"data": {"ok": 1}, "meta": {}})]
        self.assertEqual(self.kl.read()["ok"], 1)
        self.assertEqual(len(SEEN), 3)

    def test_a_quota_refusal_is_not_retried(self):
        SCRIPT["/v1/read"] = [(429, {"error": "used up"})]
        with self.assertRaises(RateLimitError):
            self.kl.read()
        self.assertEqual(len(SEEN), 1)

    def test_retries_run_out(self):
        SCRIPT["/v1/read"] = [(503, {"error": "down"})]
        with self.assertRaises(ServiceError):
            self.kl.read()
        self.assertEqual(len(SEEN), 3)

    def test_no_server(self):
        kl = Client("kll_live_test", base_url="http://127.0.0.1:9", retries=0, timeout=2)
        with self.assertRaises(ServiceError):
            kl.read()

    def test_to_pandas(self):
        frames = []

        class FakeFrame:
            def __init__(self, rows, columns=None):
                self.rows, self.columns = rows, columns or (list(rows[0]) if rows else [])
                frames.append(self)

            def __setitem__(self, k, v):
                self.converted = k

            def __getitem__(self, k):
                return k

        fake = types.ModuleType("pandas")
        fake.DataFrame = FakeFrame
        fake.to_datetime = lambda col, utc: ("utc", col)
        sys.modules["pandas"] = fake
        try:
            SCRIPT["/v1/flow"] = [(200, {"data": {"points": [{"at": "2026-11-12T12:00:00Z", "deltaUsd": 1}], "totals": {}}, "meta": {}})]
            f = self.kl.flow().to_pandas()
            self.assertEqual(f.rows[0]["deltaUsd"], 1)
            self.assertEqual(f.converted, "at")
            SCRIPT["/v1/book"] = [(200, {"data": {"now": {"bids": [[1, 2]], "asks": [[3, 4]]}, "history": None}, "meta": {}})]
            b = self.kl.book().to_pandas()
            self.assertEqual(b.rows, [{"side": "bids", "price": 1, "qty": 2}, {"side": "asks", "price": 3, "qty": 4}])
            SCRIPT["/v1/read"] = [(200, {"data": {"direction": "long"}, "meta": {}})]
            with self.assertRaises(ValueError):
                self.kl.read().to_pandas()
        finally:
            del sys.modules["pandas"]
        try:
            import pandas  # noqa: F401
        except ImportError:
            SCRIPT["/v1/flow"] = [(200, {"data": {"points": []}, "meta": {}})]
            with self.assertRaises(ImportError):
                self.kl.flow().to_pandas()


if __name__ == "__main__":
    unittest.main()
