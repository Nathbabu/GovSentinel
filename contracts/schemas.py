"""Data shapes shared by the calldata decoder, the contract, and off-chain tooling.

Deliberately free of genlayer imports: the decoder and any test harness should be
runnable without a GenVM around them.
"""

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Literal

Status = Literal["PASSED", "VETOED", "FLAGGED"]

VALID_STATUSES = ("PASSED", "VETOED", "FLAGGED")


def _known_fields(cls, payload: dict) -> dict:
    """Drop keys the current schema has never heard of.

    Evaluation records outlive the code that wrote them. A node running an older
    build should still be able to read a record written by a newer one instead of
    dying on an unexpected key.
    """
    accepted = {f.name for f in fields(cls)}
    return {k: v for k, v in payload.items() if k in accepted}


@dataclass
class DecodedCall:
    signature: str
    method_name: str
    target: str
    recipient: str
    amount: int
    extra_params: list[str] = field(default_factory=list)
    raw_calldata: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "DecodedCall":
        return cls(**_known_fields(cls, json.loads(payload)))


@dataclass
class ProposalEvaluation:
    proposal_id: str
    title: str
    status: Status
    risk_score: int
    summary: str
    discrepancies: list[str] = field(default_factory=list)
    spending_limit_exceeded: bool = False
    unwhitelisted_target: bool = False
    privilege_escalation_detected: bool = False
    decoded_method: str = ""
    decoded_recipient: str = ""
    decoded_amount: int = 0

    def __post_init__(self):
        # risk_score originates from an LLM often enough that the declared range
        # is a suggestion rather than a guarantee.
        self.risk_score = max(0, min(100, int(self.risk_score)))
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status {self.status!r} is not one of {VALID_STATUSES}")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "ProposalEvaluation":
        return cls(**_known_fields(cls, json.loads(payload)))
