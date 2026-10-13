import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app.catalogue import ROOT_PART, load_catalogue
from app.server import make_server
from tests.helpers import worked_example

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ServerTests(unittest.TestCase):
    """Runs the real HTTP server on a free port and calls it like a grader would."""

    @classmethod
    def setUpClass(cls):
        cls.catalogue = load_catalogue(DATA_DIR, ROOT_PART)
        cls.server = make_server(cls.catalogue, host="127.0.0.1", port=0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as res:
                return res.status, res.headers.get("Content-Type"), res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers.get("Content-Type"), err.read()

    def get_json(self, path):
        status, _, body = self.get(path)
        return status, json.loads(body)

    def test_health(self):
        self.assertEqual(self.get_json("/health"), (200, {"status": "ok"}))

    def test_page_is_served_at_root(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"parts catalogue", body)

    def test_validation_endpoint(self):
        status, body = self.get_json("/api/validation")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"parts", "ready", "missing", "not_replaceable"})
        self.assertEqual(body["parts"], 875)

    def test_part_endpoint_shape(self):
        status, body = self.get_json("/api/parts/AS-40003")
        self.assertEqual(status, 200)
        self.assertEqual(
            set(body),
            {"part_number", "description", "revision", "status", "total_quantity",
             "parents", "children"},
        )
        for child in body["children"]:
            self.assertEqual(set(child), {"part_number", "quantity"})

    def test_part_endpoint_accepts_any_typing(self):
        self.assertEqual(self.get_json("/api/parts/fa-30019")[1]["part_number"], "FA-30019")
        self.assertEqual(self.get_json("/api/parts/%20fa-30019%20")[1]["part_number"], "FA-30019")
        self.assertEqual(self.get_json("/api/parts/fa-30019/")[1]["part_number"], "FA-30019")

    def test_part_outside_machine_is_404_from_both_part_endpoints(self):
        self.assertEqual(self.get_json("/api/parts/AS-40210")[0], 404)
        self.assertEqual(self.get_json("/api/parts/AS-40210/paths")[0], 404)
        self.assertEqual(self.get_json("/api/parts/NOPE-1")[0], 404)

    def test_paths_endpoint(self):
        status, body = self.get_json("/api/parts/FA-30012/paths")
        self.assertEqual(status, 200)
        self.assertEqual(body["part_number"], "FA-30012")
        self.assertEqual(body["paths"], sorted(body["paths"]))

    def test_serial_endpoint(self):
        status, body = self.get_json("/api/serial/2500")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"serial": 2500, "applicable_parts": self.catalogue.applicable_parts(2500)})

    def test_serial_that_is_not_a_whole_number_is_4xx(self):
        for bad in ["25.5", "abc", "2500.0", "1e3"]:
            status, body = self.get_json(f"/api/serial/{bad}")
            self.assertEqual(status, 400, bad)
            self.assertIn("error", body)

    def test_unknown_route_and_method(self):
        self.assertEqual(self.get_json("/api/unknown")[0], 404)
        req = urllib.request.Request(self.base + "/api/validation", data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 405)

    def test_answers_are_fast(self):
        import time
        start = time.perf_counter()
        for _ in range(20):
            self.get_json("/api/parts/FA-30019/paths")
            self.get_json("/api/serial/2500")
        per_request = (time.perf_counter() - start) / 40
        self.assertLess(per_request, 1.0)


if __name__ == "__main__":
    unittest.main()
