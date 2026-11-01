"""Verifies your Gemini key and model against the real API in about 10 seconds.

    GEMINI_API_KEY=... python scripts/check_gemini.py
Exit code 0 means enrichment works end to end.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.auditor import audit_pdf
from app.llm import LLMError

if not config.GEMINI_API_KEY:
    sys.exit("Set GEMINI_API_KEY first.")
try:
    r = audit_pdf(str(config.SAMPLE_PDF), "sample_contract.pdf", engine="gemini")
except LLMError as e:
    sys.exit(f"FAILED: {e}\nIf this is HTTP 404, the model name is probably retired: set GEMINI_MODEL.")
n = sum(f["source"] == "rules+gemini" for f in r["findings"])
print(r["engine_note"])
print(f"{n} findings enriched. First rewrite:\n  {next(f for f in r['findings'] if f['source'] == 'rules+gemini')['suggested_revision']}" if n else "No findings were enriched; check the model name and quota.")
sys.exit(0 if n else 1)
