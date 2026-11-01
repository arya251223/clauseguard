import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "samples"))
from generate_sample import build, RISKY, SAFE  # noqa: E402


def make_pdf(spec, tmpdir) -> str:
    p = Path(tmpdir) / "t.pdf"
    build(p, spec)
    return str(p)


def tmp():
    return tempfile.TemporaryDirectory()
