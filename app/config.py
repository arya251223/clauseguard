"""Central configuration. Everything is overridable through environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(os.getenv("CG_RESULTS_DIR", BASE_DIR / "storage" / "results"))
SAMPLE_PDF = BASE_DIR / "samples" / "sample_contract.pdf"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Model names are retired over time, so this is configurable instead of hard-coded.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

MAX_UPLOAD_BYTES = int(os.getenv("CG_MAX_UPLOAD_MB", "10")) * 1024 * 1024
MAX_PAGES = int(os.getenv("CG_MAX_PAGES", "80"))
LLM_BATCH_SIZE = 10          # findings per Gemini request
LLM_MAX_FINDINGS = 40        # cost guard: at most this many findings are enriched
LLM_CLAUSE_CHARS = 1800      # clause text sent to the model is truncated to this
