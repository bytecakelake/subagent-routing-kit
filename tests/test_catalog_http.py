"""수집기의 HTTP 계층(httpx)이 이전 urllib 동작을 유지하는지 로컬 서버로 확인한다. 외부 네트워크는 쓰지 않는다."""
import concurrent.futures
import http.server
import pathlib
import tempfile
import threading
import unittest
from unittest import mock

import httpx
from typer.testing import CliRunner

from core import jsonio
from core.catalog import _http, build_capabilities, inspect_endpoints


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path
        if p == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/models")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif "missing" in p:
            self._send(404, b'{"error":"not found"}')
        elif p.endswith("/endpoints"):
            self._send(200, jsonio.dumps({"data": {"endpoints": [{"tag": p}]}}).encode())
        elif p in ("/models", "/models-slow"):
            self._send(200, jsonio.dumps({"data": [{"id": "x/한글"}, {"id": "y"}]}).encode())
        else:
            self._send(500, b"boom")

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()


class HttpHelper(LocalServer):
    def test_follows_redirects_like_urllib(self):
        with _http.new_client(5) as c:
            self.assertEqual(jsonio.loads(_http.get_bytes(c, self.base + "/redirect"))["data"][1]["id"], "y")

    def test_http_errors_raise_like_urllib(self):
        with _http.new_client(5) as c:
            with self.assertRaises(httpx.HTTPStatusError):
                _http.get_bytes(c, self.base + "/missing")
            with self.assertRaises(httpx.HTTPStatusError):
                _http.get_bytes(c, self.base + "/other")

    def test_describe_is_short_and_never_empty(self):
        with _http.new_client(5) as c:
            try:
                _http.get_bytes(c, self.base + "/missing")
            except Exception as e:
                self.assertEqual(_http.describe(e), "HTTP 404")
        self.assertEqual(_http.describe(httpx.ReadTimeout("")), "ReadTimeout")
        self.assertEqual(_http.describe(ValueError("bad")), "ValueError: bad")


class InspectEndpoints(LocalServer):
    def test_fetch_records_success_and_per_item_errors(self):
        with mock.patch.object(inspect_endpoints, "BASE", self.base + "/api/"), _http.new_client(5) as c:
            ok = inspect_endpoints.fetch(c, "openai/gpt:free")
            bad = inspect_endpoints.fetch(c, "vendor/missing-model")
        self.assertEqual(ok["response"]["data"]["endpoints"][0]["tag"], "/api/openai/gpt:free/endpoints")
        self.assertNotIn("error", ok)
        self.assertEqual(bad["error"], "HTTP 404")
        self.assertNotIn("response", bad)

    def test_one_client_is_safe_across_threads(self):
        ids = [f"v/m{i}" for i in range(24)] + ["v/missing"]
        with mock.patch.object(inspect_endpoints, "BASE", self.base + "/api/"), _http.new_client(5) as c, \
                concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            results = list(ex.map(lambda m: inspect_endpoints.fetch(c, m), ids))
        self.assertEqual([r["id"] for r in results], ids)
        self.assertEqual(sum("error" in r for r in results), 1)


class InspectEndpointsCli(LocalServer):
    """명령줄 진입점부터 로컬 서버까지의 종단 경로. 반복한 --ids 가 모두 수집되고 실패는 종료 코드 1로 드러난다."""

    def invoke(self, *args):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(inspect_endpoints, "BASE", self.base + "/api/"):
            out = pathlib.Path(d) / "o.json"
            r = CliRunner().invoke(inspect_endpoints.app, [*args, "--out", str(out)])
            return r, (jsonio.load_path(out) if out.exists() else None)

    def test_repeated_ids_are_all_fetched_in_order(self):
        r, records = self.invoke("--ids", "v/a", "--ids", "v/b:free", "--ids", "w/c")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertEqual([x["id"] for x in records], ["v/a", "v/b:free", "w/c"])
        self.assertIn("records=3 successful=3", r.output)

    def test_a_failed_item_is_recorded_and_exits_nonzero(self):
        r, records = self.invoke("--ids", "v/a", "--ids", "v/missing")
        self.assertEqual(r.exit_code, 1)
        self.assertEqual([("error" in x) for x in records], [False, True])
        self.assertEqual(records[1]["error"], "HTTP 404")
        self.assertIn("successful=1", r.output)

    def test_from_specs_collects_each_model_once(self):
        with tempfile.TemporaryDirectory() as d:
            specs = pathlib.Path(d) / "s.json"
            specs.write_text(jsonio.dumps([{"model": "v/a"}, {"model": "v/b"}, {"model": "v/a"}]), encoding="utf-8")
            r, records = self.invoke("--from-specs", str(specs))
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertEqual([x["id"] for x in records], ["v/a", "v/b"])


class BuildCapabilities(LocalServer):
    def test_load_models_over_http(self):
        with mock.patch.object(build_capabilities, "MODELS_URL", self.base + "/models"):
            models, source = build_capabilities.load_models(None, 5)
        self.assertEqual(set(models), {"x/한글", "y"})
        self.assertEqual(source, {"url": self.base + "/models"})

    def test_load_models_http_error_propagates(self):
        with mock.patch.object(build_capabilities, "MODELS_URL", self.base + "/other"):
            with self.assertRaises(httpx.HTTPStatusError):
                build_capabilities.load_models(None, 5)


if __name__ == "__main__":
    unittest.main()
