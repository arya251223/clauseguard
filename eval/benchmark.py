"""Latency benchmark on synthetic contracts of increasing length.   python eval/benchmark.py"""
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "samples"))
from generate_sample import build, RISKY  # noqa: E402
from app import auditor, parser  # noqa: E402

print(f"PDF backend: {parser.backend_name()}")
print(f"{'pages':>6} {'clauses':>8} {'findings':>9} {'median ms':>10} {'min ms':>8} {'max ms':>8}")
with tempfile.TemporaryDirectory() as d:
    for reps in (1, 8, 20, 40):
        sections = [(f"{i * 16 + n + 1}. {h.split('. ', 1)[1]}", b) for i in range(reps) for n, (h, b) in enumerate(RISKY[1])]
        p = Path(d) / f"b{reps}.pdf"
        build(p, ("Benchmark", sections))
        times = []
        for _ in range(5):
            t = time.perf_counter(); r = auditor.audit_pdf(str(p), "b.pdf", engine="rules"); times.append((time.perf_counter() - t) * 1000)
        print(f"{r['pages']:>6} {r['total_clauses_analyzed']:>8} {len(r['findings']):>9} {statistics.median(times):>10.0f} {min(times):>8.0f} {max(times):>8.0f}")
