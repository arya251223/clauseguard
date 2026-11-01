"""Markdown export of an audit report."""

ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


def to_markdown(r: dict) -> str:
    o = r["overall"]
    out = [f"# Contract risk report: {r['document_name']}", "",
           f"**Overall: {o['label'].replace('_', ' ')} ({o['score']}/100)**  ",
           f"Engine: {r['engine']} | Pages: {r['pages']} | Clauses: {r['total_clauses_analyzed']} | "
           f"Analysis time: {r['duration_ms']} ms", "", r["summary"], ""]
    if r["gaps"]:
        out += ["## Missing protections", ""]
        out += [f"- {ICON[g['risk']]} **{g['category']}**: {g['explanation']} _Fix:_ {g['suggested_revision']}" for g in r["gaps"]]
        out.append("")
    out += ["## Findings", ""]
    for f in r["findings"]:
        if f["risk"] == "LOW":
            continue
        out += [f"### {ICON[f['risk']]} {f['category']}: {f['heading']} (page {f['page']}, score {f['score']})", "",
                f"> {f['text'][:500]}{'…' if len(f['text']) > 500 else ''}", "",
                f"**Why:** {f['explanation']}", "", f"**Suggested revision:** {f['suggested_revision']}", ""]
        if f.get("disagreement"):
            out += [f"_Note: Gemini rated this {f['llm_risk']} versus {f['risk']} from the rules engine; review manually._", ""]
    low = sum(1 for f in r["findings"] if f["risk"] == "LOW")
    out += [f"_{low} low-risk findings omitted. See the app or JSON export._", "",
            "---", "_Automated screening, not legal advice._"]
    return "\n".join(out)
