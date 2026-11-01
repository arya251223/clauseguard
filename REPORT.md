# ClauseGuard: Project Report

**Project 4: Hybrid Contract Clause Auditor.** Rules engine plus optional Gemini, Flask API, browser UI.

## 1. Summary

ClauseGuard reads a contract PDF, splits it into clauses, scores each one for risk with a deterministic and explainable rules engine, detects missing protections, and optionally asks Gemini for plain-English explanations and tailored redlines. The result is a 0-100 score, a per-clause review with the trigger phrases highlighted, and an exportable report.

It upgrades the original Project 4 spec in four ways: the score is reproducible instead of depending on LLM output, the LLM cost is cut by batching and filtering, the system keeps working when the LLM fails, and it is hardened against hostile PDFs (including prompt injection hidden in contract text).

## 2. How it works, step by step

1. **Upload and validate.** The browser posts the PDF to `POST /api/audit`. The server checks the extension, the `%PDF-` magic bytes and the size limit (10 MB), then writes the bytes to a temporary directory that is deleted when the request ends.
2. **Extract text.** `parser.py` extracts text page by page with PyMuPDF if installed, otherwise pdfplumber. Encrypted files, files over 80 pages and image-only PDFs are rejected with a specific message (422).
3. **Segment into clauses.** A heading regex (`4.`, `4.2`, `ARTICLE V`, `Section 7`) finds clause boundaries. Each clause keeps its heading and its start page. A heading with no body of its own ("3. Fees") becomes a prefix for its children ("3. Fees and Payment › 3.1 Invoices"). Wrapped lines such as "30 days" are not mistaken for headings. Unnumbered documents fall back to paragraph splitting.
4. **Score each clause (`rules.py`).** For each of 12 rules, a topic regex decides whether the clause is about that subject. A matching clause starts at 20 points. Each risky phrase adds its weight and is recorded with its character span for highlighting. Each protective phrase subtracts points. Bands: HIGH ≥ 60, MEDIUM ≥ 35, otherwise LOW. Every point is traceable to a phrase.
5. **Check integrity and gaps.** Clauses that talk to an AI reviewer ("ignore previous instructions…") become a HIGH "Document integrity" finding. Across the whole document, the absence of a liability limit, a termination right, governing law or confidentiality is reported as a gap.
6. **Optional Gemini enrichment (`llm.py`).** Only MEDIUM and HIGH findings (max 40) are sent, in batches of 10, in parallel. The request carries a system instruction that marks clause text as untrusted data and forces a JSON schema. Each returned item is validated (known id, valid risk value, non-empty text). Valid items replace the explanation and suggested wording and add a second-opinion risk. If Gemini's risk differs from the rules, the finding is marked as a disagreement for a human to review; the rule score is never silently changed. Retries use exponential backoff on 429 and 5xx. Any failure keeps the rule-based result and records why.
7. **Aggregate (`auditor.py`).** Overall score = `0.5 × worst finding + 0.35 × mean(top 5) + gap penalty`, capped at 100: 65+ is HIGH_RISK, 35+ is MODERATE_RISK, below is SAFE. The report also contains counts, a clause map for the UI and an executive summary sentence.
8. **Store and serve.** The JSON report is saved under a random 32-hex ID. The UI fetches it and renders the summary ring, the contract map (blocks sized by clause length), filters by risk and category, and the finding cards with highlighted phrases. Exports: Markdown (`/report.md`), JSON, print.

## 3. Output on the two bundled contracts

Measured on this build with the rules engine (no API key in the sandbox).

| Document | Pages | Clauses | Overall | Findings (H / M / L) |
|---|---|---|---|---|
| `sample_contract.pdf` (one-sided MSA) | 2 | 16 | **85/100, HIGH_RISK** | 10 / 3 / 1 |
| `safe_contract.pdf` (balanced consulting agreement) | 1 | 10 | **3/100, SAFE** | 0 / 0 / 10 |

Flags on the risky sample (excerpt; full output in `docs/output_sample_contract.md` and `.json`):

| Clause | Category | Risk | Score | Why it was flagged |
|---|---|---|---|---|
| 3.1 Invoices | Payment & penalties | HIGH | 100 | 2% per month interest, non-refundable fees, right to withhold, acceleration of remaining balance, net 7 |
| 4. Term and Renewal | Auto-renewal | HIGH | 90 | 120-day notice window, successive one-year terms, price rises at renewal |
| 6. Intellectual Property | IP | HIGH | 100 | assigns pre-existing and future IP, irrevocable, waives moral rights |
| 8. Indemnification | Indemnification | HIGH | 100 | regardless of fault, "any and all" claims, unlimited, covers the other party's negligence |
| 9. Limitation of Liability | Liability | HIGH | 65 | uncapped liability |
| 10. Non-Competition | Non-compete | HIGH | 100 | 3 years, worldwide, broad scope, applies even if terminated without cause |
| 16. General | Document integrity | HIGH | 90 | text addressed to an AI system |
| 5. Termination | Termination | MEDIUM | 55 | termination for convenience, no refund of prepaid fees; the mutual right softens it |
| 7. Confidentiality | Confidentiality | MEDIUM | 45 | never expires |
| 11. Warranties | Warranties | MEDIUM | 45 | provided "as is" |
| 15. Governing Law | Disputes | LOW | 20 | topic present, no red flags |

The balanced contract scores 0 on nine clauses because mitigators (mutual indemnity, liability cap, cure period, background-IP carve-out, standard confidentiality exclusions) cancel the base score.

## 4. Verification results

| Check | Result |
|---|---|
| Automated tests (`unittest`) | **59 passed**, about 2 s |
| Mutation check: 5 deliberate rule bugs injected | **5 of 5 caught** (after strengthening 3 tests that initially missed them) |
| Live server + headless Chromium (Playwright) | Upload by file picker, sample button, risk and category filters, map jump with focus, Markdown and JSON downloads, error message on a fake PDF: all behaved as expected |
| Hostile PDF containing `<img onerror=…>` | Rendered as inert text; 0 injected elements; script did not run |
| Mobile viewport (390 px) | No horizontal overflow |
| Labelled-clause evaluation (36 clauses) | First run: 81% exact, 94% needs-attention recall, 100% precision. After fixing three phrasing gaps: **92% exact, 100% recall, 100% precision, HIGH recall 11/12** |
| Latency, rules + pdfplumber | 2 pages 0.09 s; 13 pages 0.7 s; 33 pages 1.9 s; 65 pages 4.0 s. Rules cost about 1.4 ms per clause; extraction is the bottleneck |

Evaluation caveat: the labelled set was written by the author, and the rules were tuned on its misses, so the 92% is not a held-out figure. The 81% first-run number is the more honest estimate of unseen-phrasing performance.

## 5. Bugs found during testing (and fixed)

| Found by | Bug | Fix |
|---|---|---|
| Screenshot | Intro and loading spinner both visible: `display:grid` overrode the `hidden` attribute (DOM assertions had passed while the page looked wrong) | Global `[hidden]{display:none!important}` |
| Sample run | "right, title and interest" triggered the payment rule; "work product" in a Services clause triggered IP; "after termination" triggered Termination; "exclusive venue" double-counted as exclusivity | Tightened topic regexes; added negative tests |
| Sample run | Heading-only parents ("3. Fees") were dropped and labels were ugly | Parent prefix and title extraction |
| Mutation check | 3 of 5 injected bugs survived the first test suite | Added tests on trigger labels, base score, band boundaries, non-exclusive handling and a golden-file regression |
| Eval | "shall not work for any competitor", "successive one-year terms" and "dispute invoices in good faith" missed | New patterns plus regression tests |
| Report cross-check | A negated phrase ("no refund of prepaid fees") earned mitigation points from a "refund of prepaid fees" pattern | Negative lookbehind plus test |
| Code review of my own fix | A doubled backslash made `\w` match a literal backslash | Corrected; found by inspecting bytes rather than trusting the diff |
| Benchmark | Clause numbers of 100 or more were not recognised as headings | `\d{1,3}` |
| Benchmark | Extraction, not analysis, dominates runtime | Documented; PyMuPDF auto-selected when available |

## 6. Changes from the original spec, and why

| Original Project 4 | ClauseGuard | Reason |
|---|---|---|
| One Gemini call per clause | Rules first; one batched call per 10 MEDIUM/HIGH findings | Lower cost and latency |
| Described as "deterministic" while the score came from the LLM | Score comes from rules; LLM adds explanations | The original claim was not true; this version actually is |
| "100% compliance with the Pydantic model" | Schema-constrained request plus per-item validation plus fallback | A schema reduces malformed output but cannot guarantee it |
| `gemini-1.5-flash` hard-coded | `GEMINI_MODEL`, default `gemini-2.5-flash` | Older model names are retired over time |
| Google SDK | Plain REST with an injectable transport | Fewer dependencies and testable offline |
| FastAPI + Pydantic | Flask + dataclasses | FastAPI, Pydantic and PyMuPDF could not be installed in the offline build sandbox, so they could not have been tested; Flask and pdfplumber could |
| Split on blank lines | Heading-aware segmentation with page numbers | Real contracts are numbered |
| No UI | Browser UI with contract map, highlights, filters, exports | Requested |

## 7. What was and was not exercised here

Run and verified in the build sandbox: parser, rules, auditor, Flask API, frontend in Chromium, all tests, evaluation, benchmark.

Not executed in the sandbox because it was offline:
- **PyMuPDF backend.** The code path exists and is selected automatically, but only pdfplumber ran.
- **Real Gemini calls.** The client was tested against a fake transport. Run `python scripts/check_gemini.py` with your key to confirm the endpoint, model name and schema work end to end.
- **Docker image.** The Dockerfile is straightforward but was not built.

## 8. Limitations

English only; no OCR; heuristic rules can miss unusual phrasing; risk is party-dependent and the rules assume you bear the obligation; whether a clause is enforceable (for example a non-compete) varies by jurisdiction and is not assessed. This is screening support, not legal advice.

## 9. Resume material

Pick the bullets you can defend. Every number below was measured in this build.

- Built **ClauseGuard**, a hybrid contract-risk auditor (Python, Flask, PyMuPDF/pdfplumber, Gemini API) that segments PDFs into clauses, scores them with a deterministic, explainable rules engine across 12 risk categories, and flags missing protections.
- Designed a rules-first, LLM-second architecture: Gemini adds tailored redlines via schema-constrained, validated batch calls on MEDIUM/HIGH findings only, with automatic fallback to rule-based results on quota, network or malformed-output failures.
- Hardened the pipeline against untrusted documents: prompt-injection detection, XSS-safe rendering, upload validation, temp-file deletion, CSP headers; verified with a hostile-PDF test in headless Chromium.
- Built a browser UI with a clause-level "contract map", highlighted trigger phrases, risk and category filters, and Markdown/JSON export.
- Shipped **59 automated tests**, validated test strength with mutation checks (5/5 injected bugs caught), and measured **92% four-class accuracy and 100% recall on needs-attention clauses** on an internal 36-clause labelled set; audited a 65-page contract in about 4 s.

**Interview Q&A**

- *Why not just use the LLM for everything?* Reproducibility and trust. A rules score is the same every run, free, works offline, and can point at the exact phrase behind each flag. The LLM adds wording quality where it is genuinely better.
- *What if the contract tries to manipulate the AI?* The text is treated as data: quoted, under a system instruction that forbids following it, output forced into a schema and validated, and the score never depends on the LLM. Separately, a rule flags clauses addressed to an AI reviewer.
- *How do you know the tests are good?* I injected five deliberate bugs. Three survived at first, which showed gaps; I added tests until all five were caught.
- *How accurate is it?* 92% on my own 36-clause set, but I tuned on its misses; the first-run 81% is the fairer unseen-wording estimate. A proper next step is an independent, lawyer-labelled set.
- *What would you do next?* OCR, side selection (client or vendor), jurisdiction-specific rule packs, and DOCX redline export.

## 10. Reproduce

```bash
python -m unittest discover -s tests -t . -v
python eval/run_eval.py
python eval/benchmark.py
python -m app.server        # http://127.0.0.1:8000
```
