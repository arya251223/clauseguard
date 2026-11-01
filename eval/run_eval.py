"""Clause-level evaluation of the rules engine against a small labelled set.

    python eval/run_eval.py

NONE means "no finding is expected". A clause is predicted as the highest risk among
its findings, or NONE if it has none. The labels were written by the project author, so
treat the result as a sanity check, not an independent benchmark.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.models import Clause, RISK_ORDER  # noqa: E402
from app.rules import analyze_clause  # noqa: E402

rows = json.loads((Path(__file__).parent / "labeled_clauses.json").read_text())
labels = ["HIGH", "MEDIUM", "LOW", "NONE"]
conf = {a: {b: 0 for b in labels} for a in labels}
misses = []
for i, (gold, text) in enumerate(rows):
    fs = analyze_clause(Clause(i, "1. Clause", text, 1))
    pred = max((f.risk for f in fs), key=lambda r: RISK_ORDER[r], default="NONE")
    conf[gold][pred] += 1
    if gold != pred:
        misses.append((gold, pred, text[:90]))

n = len(rows)
exact = sum(conf[l][l] for l in labels)
attn = lambda l: l in ("HIGH", "MEDIUM")
tp = sum(conf[g][p] for g in labels for p in labels if attn(g) and attn(p))
fn = sum(conf[g][p] for g in labels for p in labels if attn(g) and not attn(p))
fp = sum(conf[g][p] for g in labels for p in labels if not attn(g) and attn(p))
high_tp, high_n = conf["HIGH"]["HIGH"], sum(conf["HIGH"].values())
high_pred = sum(conf[g]["HIGH"] for g in labels)
print(f"Clauses: {n}")
print(f"Exact 4-class accuracy: {exact}/{n} = {exact / n:.0%}")
print(f"Needs-attention (MEDIUM+HIGH) recall: {tp}/{tp + fn} = {tp / (tp + fn):.0%}, precision: {tp}/{tp + fp} = {tp / (tp + fp):.0%}")
print(f"HIGH recall: {high_tp}/{high_n} = {high_tp / high_n:.0%}, HIGH precision: {high_tp}/{high_pred} = {high_tp / high_pred:.0%}")
print("\nConfusion (rows = gold, cols = predicted):")
print("        " + "".join(f"{l:>8}" for l in labels))
for g in labels:
    print(f"{g:<8}" + "".join(f"{conf[g][p]:>8}" for p in labels))
if misses:
    print("\nMisclassified:")
    for g, p, t in misses:
        print(f"  gold={g:<6} pred={p:<6} {t}")
