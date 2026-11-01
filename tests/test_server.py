import io
import unittest
from pathlib import Path
from tests.helpers import make_pdf, tmp, RISKY, ROOT
from app.server import create_app


class ServerTests(unittest.TestCase):
    def setUp(self):
        self._d = tmp()
        self.client = create_app(Path(self._d.name) / "results").test_client()
        self.pdf = Path(make_pdf(RISKY, self._d.name)).read_bytes()

    def tearDown(self):
        self._d.cleanup()

    def post(self, data, name="c.pdf", **form):
        return self.client.post("/api/audit", data={"file": (io.BytesIO(data), name), **form}, content_type="multipart/form-data")

    def test_health_and_frontend(self):
        self.assertEqual(self.client.get("/api/health").json["status"], "ok")
        with self.client.get("/") as r:
            self.assertIn(b"ClauseGuard", r.data)
        with self.client.get("/static/app.js") as r:
            self.assertEqual(r.status_code, 200)

    def test_upload_audit_roundtrip(self):
        r = self.post(self.pdf, engine="rules")
        self.assertEqual(r.status_code, 200)
        rid = r.json["id"]
        self.assertEqual(r.json["overall_risk_score"], "HIGH_RISK")
        self.assertEqual(self.client.get(f"/api/audits/{rid}").json["id"], rid)
        md = self.client.get(f"/api/audits/{rid}/report.md")
        self.assertEqual(md.status_code, 200)
        self.assertIn("Contract risk report", md.get_data(as_text=True))
        self.assertIn("attachment", md.headers["Content-Disposition"])

    def test_rejects_wrong_extension(self):
        self.assertEqual(self.post(self.pdf, name="c.txt").status_code, 415)

    def test_rejects_fake_pdf(self):
        self.assertEqual(self.post(b"MZ\x90 not a pdf", name="evil.pdf").status_code, 415)

    def test_rejects_missing_file(self):
        self.assertEqual(self.client.post("/api/audit", data={}).status_code, 400)

    def test_corrupt_pdf_is_422(self):
        r = self.post(b"%PDF-1.4 corrupt")
        self.assertEqual(r.status_code, 422)
        self.assertIn("error", r.json)

    def test_oversize_rejected(self):
        from app import config
        old, config.MAX_UPLOAD_BYTES = config.MAX_UPLOAD_BYTES, 1000
        try:
            self.assertEqual(self.post(b"%PDF-" + b"0" * 5000).status_code, 413)
        finally:
            config.MAX_UPLOAD_BYTES = old

    def test_unknown_and_malicious_ids(self):
        self.assertEqual(self.client.get("/api/audits/" + "0" * 32).status_code, 404)
        self.assertEqual(self.client.get("/api/audits/..%2F..%2Fetc%2Fpasswd").status_code, 404)

    def test_path_traversal_on_static(self):
        self.assertEqual(self.client.get("/static/../app/config.py").status_code, 404)

    def test_bad_engine_is_400(self):
        self.assertEqual(self.post(self.pdf, engine="magic").status_code, 400)

    def test_gemini_engine_without_key_is_400(self):
        from app import config
        old, config.GEMINI_API_KEY = config.GEMINI_API_KEY, ""
        try:
            self.assertEqual(self.post(self.pdf, engine="gemini").status_code, 400)
        finally:
            config.GEMINI_API_KEY = old

    def test_sample_endpoint(self):
        r = self.client.get("/api/sample?engine=rules")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["document_name"], "sample_contract.pdf")

    def test_security_headers_and_no_upload_retained(self):
        r = self.post(self.pdf, engine="rules")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        stored = list((Path(self._d.name) / "results").iterdir())
        self.assertTrue(all(p.suffix == ".json" for p in stored))


if __name__ == "__main__":
    unittest.main()
