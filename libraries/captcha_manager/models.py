from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime



@dataclass
class CaptchaMatch:

    name: str

    confidence: int = 0

    reasons: List[str] = field(
        default_factory=list
    )



@dataclass
class CaptchaResult:

    detected: bool = False

    solved: bool = False

    remaining: bool = False

    solver_attempted: bool = False

    manual_required: bool = False


    types: List[str] = field(
        default_factory=list
    )


    matches: List[CaptchaMatch] = field(
        default_factory=list
    )


    confidence: int = 0


    url_before: str = ""

    url_after: str = ""


    duration: float = 0


    timestamp: datetime = field(
        default_factory=datetime.now
    )


    metadata: Dict = field(
        default_factory=dict
    )


    def add_match(
        self,
        name,
        confidence,
        reasons
    ):

        self.matches.append(
            CaptchaMatch(
                name=name,
                confidence=confidence,
                reasons=reasons
            )
        )


        if name not in self.types:
            self.types.append(name)


        self.confidence = max(
            self.confidence,
            confidence
        )


    def blocked(self):

        return (
            self.detected
            and self.remaining
        )


    def success(self):

        return (
            self.detected
            and self.solved
            and not self.remaining
        )
