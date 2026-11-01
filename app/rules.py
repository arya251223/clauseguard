"""Deterministic clause-risk rules.

Each rule has:
  topic       - regex deciding whether a clause is about this subject
  flags       - risky language; each adds `weight` points and is highlighted in the UI
  mitigators  - protective language; each subtracts `weight` points
A clause starts at BASE points once its topic matches. Score bands: >=60 HIGH,
>=35 MEDIUM, otherwise LOW. Because every point is traceable to a phrase, a reviewer
can always see exactly why a clause was flagged. This is the audit trail an LLM
alone cannot give.

These are screening heuristics, not legal advice.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.models import Clause, Finding, band

BASE = 20
F = re.I | re.S


@dataclass(frozen=True)
class Signal:
    pattern: "re.Pattern"
    weight: int
    label: str


def S(pattern: str, weight: int, label: str) -> Signal:
    return Signal(re.compile(pattern, F), weight, label)


@dataclass(frozen=True)
class Rule:
    key: str
    name: str
    topic: "re.Pattern"
    flags: Tuple[Signal, ...]
    mitigators: Tuple[Signal, ...]
    explanation: str
    revision: str


def R(key, name, topic, flags, mitigators, explanation, revision) -> Rule:
    return Rule(key, name, re.compile(topic, F), tuple(flags), tuple(mitigators), explanation, revision)


RULES: List[Rule] = [
    R("indemnification", "Indemnification",
      r"indemnif|hold harmless",
      [S(r"regardless of (?:fault|negligence|cause)|whether or not[^.]{0,60}negligen", 45, "indemnity applies regardless of fault"),
       S(r"any and all (?:claims|losses|liabilit|damages)", 30, "covers \"any and all\" claims"),
       S(r"unlimited|without (?:limit|cap)|uncapped", 35, "no cap on indemnity"),
       S(r"sole negligence|own negligence", 30, "covers the other party's own negligence"),
       S(r"attorneys?['’]? fees", 10, "includes attorneys' fees")],
      [S(r"\bmutual|each party shall indemnify|reciprocal", 25, "mutual indemnity"),
       S(r"to the extent (?:caused|arising|attributable)", 25, "limited to the extent of the indemnitor's fault"),
       S(r"shall not exceed|subject to (?:the )?(?:cap|limitation)", 20, "indemnity is capped")],
      "Indemnification shifts the cost of third-party claims between the parties. Broad or one-sided wording can make you pay for losses you did not cause.",
      "Make the indemnity mutual, limit it to losses \"to the extent caused by\" the indemnifying party's breach or negligence, exclude the other party's own negligence, and subject it to the liability cap in this agreement."),

    R("liability", "Limitation of liability",
      r"limitation of liabilit|limit(?:s|ed|ation)?[^.]{0,40}liabilit|consequential damages|not be liable|no liabilit|aggregate liabilit|liability (?:shall|will) not exceed",
      [S(r"unlimited liabilit|uncapped|shall not be limited|not subject to (?:any )?(?:cap|limit)", 45, "liability is uncapped"),
       S(r"(?:gross negligence|wilful|willful)[^.]{0,60}(?:excluded|not (?:be )?limited)|exclud\w+[^.]{0,60}(?:gross negligence|wilful|willful)", 25, "excludes liability even for gross negligence"),
       S(r"in no event[^.]{0,120}(?:only|solely)[^.]{0,60}(?:customer|client|contractor|consultant|supplier|vendor)", 35, "protection runs to one party only"),
       S(r"\b(?:customer|client|contractor|consultant|you)\b[^.]{0,40}\bshall be (?:fully |solely )?liable for all", 30, "one party bears all liability")],
      [S(r"shall not exceed|capped at|aggregate liabilit[^.]{0,80}(?:fees|amounts?) (?:paid|payable)", 20, "liability cap tied to fees"),
       S(r"\bmutual|each party|neither party", 15, "applies to both parties")],
      "A limitation-of-liability clause decides how much either side can recover when things go wrong. Missing caps, one-way protection or carve-outs for serious misconduct create open-ended exposure.",
      "Add a mutual cap (for example, fees paid in the prior 12 months), keep carve-outs for fraud, gross negligence and wilful misconduct, and make the exclusion of indirect damages apply to both parties."),

    R("non_compete", "Non-compete / non-solicit",
      r"non-?compet|not (?:to )?compete|non-?solicit|restrictive covenant|shall not (?:directly or indirectly )?(?:engage|solicit)|shall not (?:work|be employed|provide services|consult) (?:for|with|to)[^.]{0,40}competitor",
      [S(r"\b(?:two|three|four|five|ten|[2-9]|10)\s*(?:\(\d+\)\s*)?years?\b", 35, "restriction lasts 2+ years"),
       S(r"worldwide|globally|any geograph|anywhere in the world|entire world", 30, "no geographic limit"),
       S(r"any (?:business|industry|activit)[^.]{0,40}(?:similar|competi|related)|directly or indirectly", 20, "broad scope of restricted activity"),
       S(r"even if[^.]{0,40}terminated without cause|regardless of (?:the )?(?:reason|cause) for termination", 25, "applies even after termination without cause")],
      [S(r"\b(?:six|6|three|3|twelve|12)\s*(?:\(\d+\)\s*)?months?\b", 20, "short duration (12 months or less)"),
       S(r"limited to|within (?:a |the )?(?:\d+|fifty|hundred)[- ]?(?:mile|km|kilomet)", 15, "narrow scope or geography"),
       S(r"reasonable (?:in|and)", 5, "reasonableness language")],
      "Restrictive covenants limit who you may work with or for after the contract ends. Long duration, unlimited geography or a vague scope may be unenforceable in some jurisdictions yet still chill your business.",
      "Limit the restriction to 6-12 months, to named competitors or a defined territory, and to the specific services provided under this agreement. Make it fall away if termination is without cause."),

    R("auto_renewal", "Auto-renewal / lock-in",
      r"auto(?:matic(?:ally)?)?[- ]?renew|renew(?:s|ed)? automatically|evergreen|successive (?:[\w-]+ )?(?:renewal )?(?:terms|periods)",
      [S(r"\b(?:ninety|90|one hundred (?:and )?twenty|120|180)\s*(?:\(\d+\)\s*)?days", 35, "90+ day cancellation notice window"),
       S(r"successive (?:[\w-]+ )?(?:renewal )?(?:terms|periods)|renew(?:s|ed)? for (?:an )?additional (?:one|1|two|2|three|3)[- ]year", 20, "renews for full-length terms"),
       S(r"price (?:increase|adjust)|increase[^.]{0,40}(?:fees|price)", 15, "fees may rise at renewal")],
      [S(r"cancel[^.]{0,40}at any time|terminat\w+ for convenience upon (?:thirty|30)", 25, "can cancel at any time"),
       S(r"written (?:reminder|notice of renewal)[^.]{0,60}(?:prior|before)", 15, "renewal reminder is required")],
      "Auto-renewal clauses lock you into another full term unless you give notice inside a window you may easily miss.",
      "Require a written renewal reminder 30-60 days before the notice deadline, shorten the opt-out window to 30 days, cap renewal price increases, and allow termination for convenience on 30 days' notice."),

    R("termination", "Termination",
      r"(?:may|shall|right to|entitled to|can|will) terminat|terminat\w+ (?:this|the) (?:agreement|contract)|termination (?:fee|for |of this)|early termination",
      [S(r"terminat\w+[^.]{0,100}(?:without cause|for convenience|at its sole discretion|in its sole discretion|at any time)", 25, "termination without cause"),
       S(r"no refund|non-?refundable|forfeit", 25, "no refund or forfeiture on termination"),
       S(r"immediate(?:ly)?[^.]{0,40}terminat\w+[^.]{0,80}(?:without (?:prior )?notice|no (?:cure|opportunity))", 25, "immediate termination with no cure period"),
       S(r"early termination (?:fee|charge)|termination fee|liquidated damages", 25, "termination fee")],
      [S(r"either party|mutual", 15, "right is mutual"),
       S(r"\b(?:thirty|30|sixty|60)\s*(?:\(\d+\)\s*)?days?[^.]{0,40}cure|opportunity to cure|cure period", 20, "cure period"),
       S(r"(?<!no )(?<!not )pro[- ]?rata refund|(?<!no )(?<!not )refund (?:of )?(?:any )?prepaid", 15, "refund of unused fees")],
      "Termination terms decide how and when each side can exit and what it costs. One-sided exits, fees or missing cure periods are a common source of disputes.",
      "Make termination rights mutual, add a 30-day written cure period for breaches, and provide a pro-rata refund of prepaid fees when you terminate for the other party's breach."),

    R("ip", "Intellectual property",
      r"intellectual property|work made for hire|work for hire|assigns?\b[^.]{0,60}(?:right|invention)|ownership of|moral rights|work product[^.]{0,60}(?:owned|assign|ownership)",
      [S(r"all (?:right|title)[^.]{0,80}(?:past|present|future|pre-?existing)|including[^.]{0,40}pre-?existing", 45, "assigns pre-existing or future IP"),
       S(r"irrevocabl\w+[^.]{0,40}assign|assign\w*[^.]{0,40}irrevocabl", 25, "irrevocable assignment"),
       S(r"perpetual[^.]{0,30}irrevocable|worldwide[^.]{0,30}royalty-free[^.]{0,40}license", 20, "broad perpetual licence"),
       S(r"moral rights|waive\w*[^.]{0,30}attribution", 15, "waives moral rights")],
      [S(r"background (?:ip|intellectual property|technology)|pre-?existing[^.]{0,40}(?:remain|retain|excluded)", 30, "your pre-existing IP is carved out"),
       S(r"retain\w*[^.]{0,30}(?:all )?(?:right|ownership|title)|license[- ]back", 25, "you retain ownership or a licence-back")],
      "IP clauses decide who owns what is created. Assigning pre-existing or unrelated IP can hand over tools and know-how you rely on for other clients.",
      "Limit assignment to deliverables created specifically for this engagement and paid for in full, expressly exclude each party's background IP, and grant a licence-back for reusable tools and know-how."),

    R("confidentiality", "Confidentiality",
      r"confidential|non-?disclosure",
      [S(r"in perpetuity|perpetual|indefinite(?:ly)?|survive[^.]{0,40}(?:indefinitely|forever)", 25, "confidentiality never expires"),
       S(r"all information[^.]{0,60}(?:whether or not|regardless of)[^.]{0,40}(?:marked|designated|labell?ed)", 20, "all information is covered, marked or not"),
       S(r"(?:only|solely)\s+(?:the )?(?:recipient|you|customer|client|contractor)[^.]{0,40}(?:bound|obligat)", 25, "obligation binds one party only")],
      [S(r"publicly available|independently developed|already known|required by law", 20, "standard exclusions present"),
       S(r"\b(?:two|three|five|2|3|5)\s*(?:\(\d+\)\s*)?years", 20, "fixed confidentiality period"),
       S(r"\bmutual|each party", 15, "mutual obligation")],
      "Confidentiality terms govern what you may share and for how long. Perpetual, one-way or exclusion-free obligations are hard to comply with.",
      "Make obligations mutual, add standard exclusions (public, independently developed, already known, legally compelled), and limit the term to 3-5 years after termination, except for trade secrets."),

    R("payment", "Payment & penalties",
      r"late (?:fee|payment|charge)|accrue[sd]? interest|interest (?:rate|at \d|of \d)|payment terms|invoice|\bnet\s*\d+|fees? (?:are|shall be) (?:due|payable)",
      [S(r"\b(?:1\.5|2|3|4|5)(?:\.\d+)?\s*%\s*(?:per|a|each)\s*month", 40, "late interest of 1.5%+ per month"),
       S(r"non-?refundable", 20, "fees are non-refundable"),
       S(r"set-?off|withhold", 20, "right to withhold or set off payments"),
       S(r"accelerat\w+|entire (?:remaining |unpaid |outstanding )?(?:balance|amount)[^.]{0,60}(?:immediately )?due", 25, "acceleration of remaining fees"),
       S(r"\bnet\s*(?:7|10|15)\b|within (?:five|seven|ten|5|7|10) days", 15, "short payment window")],
      [S(r"good[- ]faith (?:dispute|disagree)|disputed (?:amount|invoice|fees)|dispute (?:any )?(?:invoices?|charges?)[^.]{0,20}good faith", 20, "right to dispute invoices"),
       S(r"\bnet\s*(?:30|45|60)\b|within (?:thirty|forty-five|sixty|30|45|60) days", 10, "standard payment window")],
      "Payment terms drive cash flow and cost. High late-payment interest, acceleration and set-off rights can quickly turn a small delay into a large bill.",
      "Cap late interest at a modest annual rate, allow good-faith invoice disputes without penalty, move to net-30 terms, and remove acceleration and unilateral set-off rights."),

    R("modification", "Unilateral changes",
      r"amend|modif|change[^.]{0,30}(?:terms|agreement|fees|pricing|policy|policies)|may update",
      [S(r"sole (?:and absolute )?discretion|absolute discretion", 35, "changes at sole discretion"),
       S(r"at any time[^.]{0,60}without (?:prior )?notice|without (?:prior )?notice", 30, "changes without notice"),
       S(r"unilateral", 30, "explicitly unilateral"),
       S(r"continued use[^.]{0,60}(?:constitutes|shall constitute|deemed)[^.]{0,30}(?:acceptance|consent)", 25, "continued use counts as acceptance")],
      [S(r"mutual(?:ly)? agree|signed by (?:both|each|all)|written (?:agreement|amendment) (?:signed|executed)", 30, "changes need both parties' signature"),
       S(r"(?:thirty|30|sixty|60)\s*(?:\(\d+\)\s*)?days['’]? (?:prior )?(?:written )?notice", 20, "advance notice required")],
      "A clause that lets one side change the contract alone means you can be bound by terms you never agreed to.",
      "Require every amendment to be in writing and signed by both parties; if a unilateral change is unavoidable, require 30 days' prior notice and a right to terminate without penalty."),

    R("disputes", "Disputes & governing law",
      r"governing law|arbitrat|jurisdiction|venue|jury|class action|dispute resolution",
      [S(r"waive\w*[^.]{0,50}(?:jury|class action|class-action)", 35, "waives jury trial or class action"),
       S(r"exclusive (?:jurisdiction|venue)", 20, "exclusive venue"),
       S(r"(?:bear|pay) all (?:costs|fees|expenses)[^.]{0,60}arbitrat|arbitrat[^.]{0,80}(?:costs|fees)[^.]{0,40}(?:borne|paid) by (?:the )?(?:customer|client|contractor|you)", 30, "you pay all arbitration costs"),
       S(r"prevailing party[^.]{0,40}(?:attorney|legal) fees", 10, "loser-pays attorneys' fees")],
      [S(r"each party (?:shall )?bears? its own|equally (?:share|split)", 20, "costs are shared"),
       S(r"\bAAA\b|\bJAMS\b|\bICC\b|\bLCIA\b|\bUNCITRAL\b", 10, "recognised neutral arbitral body"),
       S(r"mutual|either party", 10, "applies to both parties")],
      "Dispute clauses decide where, how and at whose expense disagreements are resolved. Waivers and distant exclusive venues can make it impractical to enforce your rights.",
      "Choose a neutral venue and recognised arbitral institution, split costs equally, avoid blanket waivers of statutory rights, and allow court action for injunctive relief."),

    R("warranty", "Warranties & disclaimers",
      r"warrant|\bas[- ]is\b|disclaim",
      [S(r"\"?as[- ]is\"?(?:\s+and\s+\"?as[- ]available\"?)?", 25, "provided \"as is\""),
       S(r"disclaim\w*[^.]{0,40}all (?:express|implied|other)?\s*warrant", 30, "disclaims all warranties"),
       S(r"no warrant\w+|makes no (?:representation|warranty)", 25, "no warranty given")],
      [S(r"warrants? (?:and represents )?that|represents and warrants", 25, "affirmative warranties given"),
       S(r"(?:thirty|30|sixty|60|ninety|90)[- ]day warranty|re-?perform|repair or replace", 20, "remedy for defects")],
      "Warranty disclaimers remove your recourse when deliverables or services do not work as promised.",
      "Require express warranties that services will be performed professionally and deliverables will conform to the specification, with a repair, re-performance or refund remedy."),

    R("exclusivity", "Exclusivity & minimum commitments",
      r"(?<!non-)exclusive(?:ly)?\b(?!\s+(?:venue|jurisdiction|remed))|sole supplier|minimum (?:purchase|commitment|volume|spend)|take[- ]or[- ]pay|most favou?red",
      [S(r"(?<!non-)(?<!non )\bexclusive(?:ly)?\b(?!\s+(?:venue|jurisdiction|remed))", 30, "exclusivity obligation"),
       S(r"minimum (?:purchase|commitment|volume|spend)|take[- ]or[- ]pay|shortfall", 30, "minimum spend or take-or-pay"),
       S(r"sole supplier|solely from", 20, "single-source obligation")],
      [S(r"non-?exclusive", 30, "non-exclusive"),
       S(r"may (?:also )?(?:purchase|engage|source)[^.]{0,40}(?:third part|other)", 20, "free to use other providers")],
      "Exclusivity and minimum-commitment terms lock you to one counterparty regardless of price or performance.",
      "Make the arrangement non-exclusive, drop or lower minimum commitments, and add a right to benchmark pricing and exit if service levels are missed."),
]

INJECTION_RE = re.compile(
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above) instructions|disregard (?:the |all )?(?:above|previous)|"
    r"system prompt|you are (?:now )?an? (?:ai|assistant|language model)|as an ai (?:model|assistant)|rate this (?:contract|clause) as (?:low|safe)",
    re.I)

# Document-level gaps: protections whose absence is itself a risk.
GAPS = [
    ("liability", "Limitation of liability", "MEDIUM", 45,
     r"limitation of liabilit|limit(?:s|ed|ation)?[^.]{0,40}liabilit|consequential damages",
     "No limitation-of-liability clause was found, so exposure may be unlimited.",
     "Add a mutual cap on liability and an exclusion of indirect damages."),
    ("termination", "Termination rights", "MEDIUM", 40, r"terminat",
     "No termination clause was found, so there may be no clean way to exit.",
     "Add mutual termination for breach with a 30-day cure period and termination for convenience on notice."),
    ("disputes", "Governing law / dispute resolution", "LOW", 25, r"governing law|jurisdiction|arbitrat|laws of",
     "No governing-law or dispute-resolution clause was found.",
     "Specify governing law, venue and the dispute process."),
    ("confidentiality", "Confidentiality", "LOW", 20, r"confidential|non-?disclosure",
     "No confidentiality clause was found.", "Add a mutual confidentiality clause with standard exclusions."),
]


def _spans(text: str, sig: Signal) -> Optional[Tuple[int, int]]:
    m = sig.pattern.search(text)
    return m.span() if m else None


def evaluate(clause: Clause, rule: Rule) -> Optional[Finding]:
    if not rule.topic.search(clause.heading + " " + clause.text):
        return None
    score, triggers, mitigations, highlights = BASE, [], [], []
    for sig in rule.flags:
        sp = _spans(clause.text, sig)
        if sp:
            score += sig.weight
            triggers.append(sig.label)
            highlights.append(sp)
    for sig in rule.mitigators:
        sp = _spans(clause.text, sig)
        if sp:
            score -= sig.weight
            mitigations.append(sig.label)
    score = max(0, min(100, score))
    risk = band(score)
    why = ""
    if triggers:
        why += " Flagged because: " + "; ".join(triggers) + "."
    if mitigations:
        why += " Reduced by: " + "; ".join(mitigations) + "."
    if not triggers and not mitigations:
        why += " No specific red flags detected."
    return Finding(
        clause_id=clause.id, heading=clause.heading, page=clause.page, category=rule.name,
        risk=risk, score=score, explanation=rule.explanation + why, suggested_revision=rule.revision,
        text=clause.text, triggers=triggers, mitigations=mitigations,
        highlights=sorted(set(highlights)),
    )


def analyze_clause(clause: Clause) -> List[Finding]:
    out = []
    if INJECTION_RE.search(clause.text):
        m = INJECTION_RE.search(clause.text)
        out.append(Finding(
            clause_id=clause.id, heading=clause.heading, page=clause.page, category="Document integrity",
            risk="HIGH", score=90, text=clause.text, highlights=[m.span()],
            triggers=["text addressed to an AI system, not to the parties"],
            explanation="This clause contains wording that looks like an instruction to an AI reviewer (a prompt-injection attempt). It has no legal purpose and may be an attempt to manipulate automated review.",
            suggested_revision="Remove the text and ask the sender why it was included. Have counsel review the document by hand."))
    for rule in RULES:
        f = evaluate(clause, rule)
        if f:
            out.append(f)
    return out


def find_gaps(full_text: str):
    gaps = []
    for key, name, risk, score, pattern, why, fix in GAPS:
        if not re.search(pattern, full_text, F):
            gaps.append({"category": name, "risk": risk, "score": score, "explanation": why, "suggested_revision": fix})
    return gaps
