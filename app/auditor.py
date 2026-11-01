"""Orchestrates parse -> rules -> (optional) Gemini -> aggregate."""
import time
from collections import Counter
from typing import Optional

from app import config, parser, rules
from app.llm import GeminiClient, LLMError
from app.models import RISK_ORDER, band


def _overall(findings, gaps) -> dict:
    scores = sorted((f.score for f in findings), reverse=True)
    top = scores[:5]
    worst = scores[0] if scores else 0
    avg_top = sum(top) / len(top) if top else 0
    gap_pts = sum(g["score"] for g in gaps) / 10
    value = min(100, round(0.5 * worst + 0.35 * avg_top + gap_pts))
    label = "HIGH_RISK" if value >= 65 else "MODERATE_RISK" if value >= 35 else "SAFE"
    return {"score": value, "label": label}


def _summary(report) -> str:
    c = report["counts"]
    parts = [f"{report['total_clauses_analyzed']} clauses across {report['pages']} pages were screened; "
             f"{c['HIGH']} high, {c['MEDIUM']} medium and {c['LOW']} low-risk findings."]
    top = [f for f in report["findings"] if f["risk"] == "HIGH"][:3]
    if top:
        parts.append("Biggest concerns: " + "; ".join(f"{f['category']} ({f['heading']}, p.{f['page']})" for f in top) + ".")
    if report["gaps"]:
        parts.append("Missing protections: " + ", ".join(g["category"] for g in report["gaps"]) + ".")
    return " ".join(parts)


def audit_pdf(path: str, filename: str, engine: str = "auto", gemini: Optional[GeminiClient] = None) -> dict:
    t0 = time.time()
    clauses, pages = parser.parse_pdf(path, config.MAX_PAGES)

    findings = []
    for cl in clauses:
        findings.extend(rules.analyze_clause(cl))
    findings.sort(key=lambda f: (-f.score, f.clause_id))
    gaps = rules.find_gaps(" ".join(c.text for c in clauses))

    used, llm_note = "rules", None
    if engine not in ("auto", "rules", "gemini"):
        raise ValueError("engine must be auto, rules or gemini")
    wants_llm = engine == "gemini" or (engine == "auto" and (gemini is not None or config.GEMINI_API_KEY))
    if wants_llm:
        client = gemini or GeminiClient(config.GEMINI_API_KEY)   # raises LLMError if no key
        try:
            n = client.enrich(findings)
            used = "rules+gemini"
            llm_note = f"Gemini ({client.model}) enriched {n} findings."
        except LLMError as e:
            llm_note = f"Gemini unavailable ({e}); showing rule-based results."

    counts = Counter({"HIGH": 0, "MEDIUM": 0, "LOW": 0})
    counts.update(f.risk for f in findings)
    flagged_clause_ids = {f.clause_id for f in findings}
    report = {
        "document_name": filename,
        "pages": pages,
        "total_clauses_analyzed": len(clauses),
        "clauses_with_findings": len(flagged_clause_ids),
        "overall": _overall(findings, gaps),
        "overall_risk_score": None,
        "high_risk_count": counts["HIGH"],
        "counts": dict(counts),
        "engine": used,
        "engine_note": llm_note,
        "pdf_backend": parser.backend_name(),
        "categories": sorted({f.category for f in findings}),
        "clause_map": [{"id": c.id, "heading": c.heading, "page": c.page,
                        "risk": max((f.risk for f in findings if f.clause_id == c.id),
                                    key=lambda r: RISK_ORDER[r], default="NONE")} for c in clauses],
        "findings": [f.to_dict() for f in findings],
        "gaps": gaps,
    }
    report["overall_risk_score"] = report["overall"]["label"]
    report["summary"] = _summary(report)
    report["duration_ms"] = round((time.time() - t0) * 1000, 1)
    return report
