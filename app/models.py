from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def band(score: int) -> str:
    return "HIGH" if score >= 60 else "MEDIUM" if score >= 35 else "LOW"


@dataclass
class Clause:
    id: int
    heading: str
    text: str
    page: int


@dataclass
class Finding:
    clause_id: int
    heading: str
    page: int
    category: str
    risk: str
    score: int
    explanation: str
    suggested_revision: str
    text: str
    triggers: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)
    highlights: List[Tuple[int, int]] = field(default_factory=list)
    source: str = "rules"                 # "rules" or "rules+gemini"
    llm_risk: Optional[str] = None
    disagreement: bool = False

    def to_dict(self):
        return asdict(self)
