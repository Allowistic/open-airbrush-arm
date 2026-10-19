import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from airbrush_sim.server import make_server

SIM_DIR = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "airbrush_sim", *args], cwd=SIM_DIR,
                          capture_output=True, text=True, timeout=300)


class TestCLI(unittest.TestCase):
    def test_run_writes_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            p = run_cli("run", "--shape", "square", "--size", "60", "--json", str(out / "r.json"),
                        "--csv", str(out / "r.csv"), "--html", str(out / "r.html"), "--check")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            data = json.loads((out / "r.json").read_text())
            self.assertIn("samples", data["result"])
            self.assertIsNotNone(data["reach"])
            header = (out / "r.csv").read_text().splitlines()[0]
            self.assertTrue(header.startswith("t_s,phase,air,needle,shoulder_pan_deg"))
            html = (out / "r.html").read_text()
            self.assertIn("window.SIM_DATA = {", html)
            self.assertNotIn("<!--SIM_DATA-->", html)
            self.assertEqual(html.count("</script>"), 2)  # data block + app, nothing closed early

    def test_check_fails_when_gate_blocks(self):
        p = run_cli("run", "--shape", "line", "--standoff", "20", "--size", "40", "--check")
        self.assertEqual(p.returncode, 1)
        self.assertIn("WARNING", p.stdout)


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = make_server(port=0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=120) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_and_api(self):
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Open Airbrush Arm simulator", body)
        code, body = self.get("/api/simulate?shape=line&size=40")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["config"]["shape"]["kind"], "line")
        code, body = self.get("/api/reach?standoff=40&step=60")
        self.assertEqual(code, 200)
        self.assertIn("status", json.loads(body))

    def test_errors(self):
        self.assertEqual(self.get("/api/simulate?standoff=abc")[0], 400)
        self.assertEqual(self.get("/api/simulate?shape=spiral")[0], 400)
        self.assertEqual(self.get("/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
