import json
import unittest
from tests.helpers import make_pdf, tmp, RISKY, SAFE
from app import auditor, config
from app.llm import GeminiClient, LLMError


def fake_transport(fn):
    calls = []

    def t(url, headers, body, timeout):
        calls.append((url, headers, body))
        return fn(len(calls), body)
    t.calls = calls
    return t


def ok_reply(body, risk="HIGH"):
    items = json.loads(body["contents"][0]["parts"][0]["text"])
    out = [{"id": i["id"], "risk": risk, "explanation": "Plain-English risk.", "suggested_revision": "Safer text."} for i in items]
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}]}


class AuditorTests(unittest.TestCase):
    def audit(self, spec, **kw):
        with tmp() as d:
            return auditor.audit_pdf(make_pdf(spec, d), "x.pdf", **kw)

    def test_risky_contract_scores_high(self):
        r = self.audit(RISKY, engine="rules")
        self.assertEqual(r["overall_risk_score"], "HIGH_RISK")
        self.assertGreaterEqual(r["high_risk_count"], 8)
        self.assertEqual(r["engine"], "rules")
        cats = set(r["categories"])
        for c in ("Indemnification", "Non-compete / non-solicit", "Document integrity"):
            self.assertIn(c, cats)

    def test_golden_sample_risk_map(self):
        """Locks in the sample contract's findings so rule changes are deliberate."""
        r = self.audit(RISKY, engine="rules")
        got = {(f["heading"].split(" ")[0], f["category"]): f["risk"] for f in r["findings"]}
        expected = {
            ("3.", "Payment & penalties"): "HIGH", ("4.", "Auto-renewal / lock-in"): "HIGH",
            ("5.", "Termination"): "MEDIUM", ("6.", "Intellectual property"): "HIGH",
            ("7.", "Confidentiality"): "MEDIUM", ("8.", "Indemnification"): "HIGH",
            ("9.", "Limitation of liability"): "HIGH", ("10.", "Non-compete / non-solicit"): "HIGH",
            ("11.", "Warranties & disclaimers"): "MEDIUM", ("12.", "Unilateral changes"): "HIGH",
            ("13.", "Disputes & governing law"): "HIGH", ("14.", "Exclusivity & minimum commitments"): "HIGH",
            ("15.", "Disputes & governing law"): "LOW", ("16.", "Document integrity"): "HIGH",
        }
        self.assertEqual(got, expected)
        self.assertEqual(r["overall"]["score"], 85)

    def test_balanced_contract_is_safe(self):
        r = self.audit(SAFE, engine="rules")
        self.assertEqual(r["overall_risk_score"], "SAFE")
        self.assertEqual(r["high_risk_count"], 0)

    def test_report_shape(self):
        r = self.audit(RISKY, engine="rules")
        for k in ("summary", "clause_map", "findings", "gaps", "counts", "duration_ms", "pages"):
            self.assertIn(k, r)
        json.dumps(r)
        self.assertEqual(r["findings"], sorted(r["findings"], key=lambda f: (-f["score"], f["clause_id"])))

    def test_missing_clauses_become_gaps(self):
        r = self.audit(("Thin", [("1. Services", "Provider will deliver the services described in the order form to the client."),
                                 ("2. Fees", "Client will pay the invoice amounts shown in the order form each month.")]), engine="rules")
        self.assertGreaterEqual(len(r["gaps"]), 3)

    def test_gemini_enriches_and_flags_disagreement(self):
        t = fake_transport(lambda n, b: ok_reply(b, risk="LOW"))
        r = self.audit(RISKY, engine="auto", gemini=GeminiClient("k", transport=t))
        self.assertEqual(r["engine"], "rules+gemini")
        enriched = [f for f in r["findings"] if f["source"] == "rules+gemini"]
        self.assertTrue(enriched)
        self.assertTrue(any(f["disagreement"] for f in enriched))
        # risk and score still come from the rules engine
        self.assertEqual(r["overall_risk_score"], "HIGH_RISK")
        self.assertTrue(all(f["risk"] != "LOW" for f in enriched))

    def test_gemini_only_sees_medium_and_high(self):
        t = fake_transport(lambda n, b: ok_reply(b))
        self.audit(RISKY, engine="auto", gemini=GeminiClient("k", transport=t))
        sent = [i for _, _, b in t.calls for i in json.loads(b["contents"][0]["parts"][0]["text"])]
        self.assertTrue(sent)
        self.assertTrue(all(i["rules_risk"] in ("HIGH", "MEDIUM") for i in sent))

    def test_request_is_schema_constrained_and_keyed_by_header(self):
        t = fake_transport(lambda n, b: ok_reply(b))
        self.audit(RISKY, engine="auto", gemini=GeminiClient("secret", transport=t))
        url, headers, body = t.calls[0]
        self.assertNotIn("secret", url)
        self.assertEqual(headers["x-goog-api-key"], "secret")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("UNTRUSTED", body["system_instruction"]["parts"][0]["text"])

    def test_gemini_failure_falls_back_to_rules(self):
        def boom(n, b):
            raise LLMError("HTTP 500")
        r = self.audit(RISKY, engine="auto", gemini=GeminiClient("k", transport=fake_transport(boom), sleep=lambda s: None))
        self.assertEqual(r["engine"], "rules")
        self.assertIn("unavailable", r["engine_note"])
        self.assertEqual(r["overall_risk_score"], "HIGH_RISK")

    def test_retry_then_success_on_429(self):
        def flaky(n, b):
            if n < 3:
                raise LLMError("HTTP 429")
            return ok_reply(b)
        t = fake_transport(flaky)
        r = self.audit(("One", [("1. Indemnification", "Client shall indemnify Provider against any and all claims regardless of fault.")]),
                       engine="auto", gemini=GeminiClient("k", transport=t, sleep=lambda s: None))
        self.assertEqual(r["engine"], "rules+gemini")
        self.assertEqual(len(t.calls), 3)

    def test_bad_llm_items_are_dropped(self):
        def junk(n, b):
            items = json.loads(b["contents"][0]["parts"][0]["text"])
            bad = [{"id": "nope", "risk": "HIGH", "explanation": "x", "suggested_revision": "y"},
                   {"id": items[0]["id"], "risk": "CATASTROPHIC", "explanation": "x", "suggested_revision": "y"},
                   {"id": items[0]["id"], "risk": "HIGH", "explanation": "", "suggested_revision": "y"}]
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(bad)}]}}]}
        r = self.audit(RISKY, engine="auto", gemini=GeminiClient("k", transport=fake_transport(junk)))
        self.assertTrue(all(f["source"] == "rules" for f in r["findings"]))

    def test_non_json_reply_does_not_crash(self):
        t = fake_transport(lambda n, b: {"candidates": [{"content": {"parts": [{"text": "sure! here you go"}]}}]})
        r = self.audit(RISKY, engine="auto", gemini=GeminiClient("k", transport=t, sleep=lambda s: None))
        self.assertEqual(r["engine"], "rules")

    def test_gemini_engine_without_key_raises(self):
        old, config.GEMINI_API_KEY = config.GEMINI_API_KEY, ""
        try:
            with self.assertRaises(LLMError):
                self.audit(RISKY, engine="gemini")
        finally:
            config.GEMINI_API_KEY = old

    def test_auto_without_key_silently_uses_rules(self):
        old, config.GEMINI_API_KEY = config.GEMINI_API_KEY, ""
        try:
            r = self.audit(RISKY, engine="auto")
            self.assertEqual((r["engine"], r["engine_note"]), ("rules", None))
        finally:
            config.GEMINI_API_KEY = old


if __name__ == "__main__":
    unittest.main()
