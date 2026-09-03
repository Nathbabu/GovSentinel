"""The deterministic half of a GovSentinel verdict.

Split out of the contract so the rules that actually block a proposal can be run,
tested and benchmarked without a GenVM around them. Everything here is pure: the
contract owns storage and the non-deterministic call, this module owns the policy.
"""

import json
from dataclasses import dataclass
from typing import Callable

from calldata_decoder import (
    MALFORMED_METHOD,
    MAX_UINT256,
    PRIVILEGED_METHODS,
    UNKNOWN_METHOD,
    VALUE_METHODS,
    ZERO_ADDRESS,
)
from schemas import DecodedCall, ProposalEvaluation

# The auditor answers with codes from this closed set, never free text. Two
# validators running the same prompt have to produce byte-identical output for
# strict_eq to reach consensus, and prose never will.
FINDING_CODES = {
    "AMOUNT_MISMATCH": "the amount in the proposal text differs from the amount in the calldata",
    "CONSTITUTION_BREACH": "the action breaks a rule in the DAO constitution",
    "HIDDEN_TRANSFER": "the calldata moves value the proposal text never mentions",
    "INTENT_MISMATCH": "the written proposal does not describe what the calldata executes",
    "OWNERSHIP_TRANSFER": "the call hands ownership of the target contract to another address",
    "PROXY_UPGRADE": "the call repoints a proxy at a new implementation",
    "RECIPIENT_MISMATCH": "the beneficiary named in the text is not the address being paid",
    "ROLE_GRANT": "the call grants a privileged role",
    "UNLIMITED_APPROVAL": "an unbounded allowance would let the spender drain the treasury later",
    "VAGUE_DESCRIPTION": "the proposal is too vague to audit against its own calldata",
}

RISK_BANDS = (0, 20, 40, 60, 80, 100)
INTENT_VALUES = ("MATCH", "PARTIAL", "MISMATCH")

VETO_RISK_FLOOR = 90
FLAG_RISK_FLOOR = 50


@dataclass(frozen=True)
class PolicyConfig:
    dao_name: str
    constitution_rules: str
    max_single_spend: int
    treasury_token: str
    whitelisted: Callable[[str], bool]


def norm_address(address: str) -> str:
    return address.strip().lower()


def _band(value) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 100
    return min(RISK_BANDS, key=lambda band: abs(band - max(0, min(100, score))))


def canonical_verdict(payload: dict) -> dict:
    """Collapse the model's answer onto a small fixed lattice.

    Anything unreadable resolves to the pessimistic end, so a validator that got
    garbage back still agrees with one that got nothing back.
    """
    intent = str(payload.get("intent_match", "")).strip().upper()
    if intent not in INTENT_VALUES:
        intent = "MISMATCH"

    reported = payload.get("findings")
    if not isinstance(reported, list):
        reported = []
    findings = sorted({str(code).strip().upper() for code in reported} & FINDING_CODES.keys())

    return {
        "intent_match": intent,
        "risk_band": _band(payload.get("risk_band", 100)),
        "findings": findings,
    }


def parse_auditor_reply(raw: str) -> dict:
    """Turn whatever the model said into a canonical verdict.

    An empty payload canonicalises to MISMATCH at risk 100, so a model that
    rambles instead of answering costs the proposal its pass rather than
    reverting the evaluation outright.
    """
    fence = "`" * 3
    cleaned = raw.replace(fence + "json", "").replace(fence, "").strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return canonical_verdict(payload)


def build_audit_prompt(
    config: PolicyConfig,
    proposal_id: str,
    title: str,
    description: str,
    call: DecodedCall,
    claimed_recipient: str,
    claimed_amount: int,
) -> str:
    catalogue = "\n".join(f"  {code}: {text}" for code, text in FINDING_CODES.items())
    arguments = "; ".join(call.extra_params) if call.extra_params else "none"
    shape = '{"intent_match": "MATCH" | "PARTIAL" | "MISMATCH", "risk_band": <number>, "findings": ["CODE"]}'

    return f"""You audit governance proposals for {config.dao_name}. Decide whether the written
proposal honestly describes the transaction it would execute.

DAO constitution:
{config.constitution_rules}

Proposal {proposal_id}: {title}
{description}

The proposal claims it sends {int(claimed_amount)} to {claimed_recipient}.

Decoded execution payload, read from the raw calldata and treated as ground truth:
  target contract: {call.target}
  method: {call.signature or "unrecognised selector"}
  address argument: {call.recipient}
  amount argument: {call.amount}
  other arguments: {arguments}
  DAO treasury token: {config.treasury_token}

Judge the text against this payload, not against what the payload should have been.
Report findings only as codes from this list:
{catalogue}

Reply with JSON and nothing else. No prose, no code fences:
{shape}

risk_band must be exactly one of {list(RISK_BANDS)}. Independent validators run this
same prompt and their answers are compared byte for byte, so pick the band the
evidence plainly supports rather than a precise-looking number in between."""


def apply_policy(
    config: PolicyConfig,
    call: DecodedCall,
    *,
    proposal_id: str,
    title: str,
    claimed_recipient: str,
    claimed_amount: int,
    verdict: dict,
) -> ProposalEvaluation:
    claimed_to = norm_address(claimed_recipient)
    claimed = int(claimed_amount)
    cap = int(config.max_single_spend)
    treasury = norm_address(config.treasury_token)

    moves_value = call.method_name in VALUE_METHODS
    touches_treasury = call.target == treasury
    unreadable = call.method_name in (UNKNOWN_METHOD, MALFORMED_METHOD)

    spending_limit_exceeded = moves_value and call.amount > cap
    unwhitelisted_target = not config.whitelisted(call.target)
    privilege_escalation = call.method_name in PRIVILEGED_METHODS
    unlimited_approval = call.method_name == "approve" and call.amount == MAX_UINT256
    recipient_mismatch = bool(claimed_to) and call.recipient != ZERO_ADDRESS and claimed_to != call.recipient
    amount_mismatch = moves_value and claimed != call.amount

    # Hard overrides, decided from the bytes alone. They outrank whatever the model
    # concluded, because the persuasive description is exactly the part an attacker
    # controls.
    blocking = []
    if unreadable:
        blocking.append("calldata does not decode to a known governance action: " + "; ".join(call.extra_params))
    if unwhitelisted_target:
        blocking.append(f"target {call.target} is not on the approved contract whitelist")
    if spending_limit_exceeded:
        blocking.append(f"{call.method_name} moves {call.amount}, over the per-proposal cap of {cap}")
    if recipient_mismatch:
        blocking.append(f"proposal names {claimed_to} but the calldata addresses {call.recipient}")
    if amount_mismatch:
        blocking.append(f"proposal claims {claimed} but the calldata moves {call.amount}")
    if unlimited_approval and touches_treasury:
        blocking.append(f"unbounded allowance on the treasury token for {call.recipient}")
    if privilege_escalation and (unwhitelisted_target or verdict["intent_match"] == "MISMATCH"):
        blocking.append(f"{call.signature} takes control of {call.target} without a matching mandate in the text")

    warnings = []
    if privilege_escalation and not blocking:
        warnings.append(f"{call.signature} changes who controls {call.target}")
    if unlimited_approval and not touches_treasury:
        warnings.append(f"unbounded allowance granted to {call.recipient}")
    if touches_treasury and moves_value and not spending_limit_exceeded and call.amount > cap // 2:
        warnings.append(f"spends {call.amount}, over half the per-proposal cap in one go")

    discrepancies = blocking + warnings + [FINDING_CODES[code] for code in verdict["findings"]]

    risk_score = verdict["risk_band"]
    if blocking:
        status = "VETOED"
        risk_score = max(risk_score, VETO_RISK_FLOOR)
    elif warnings or verdict["findings"] or verdict["intent_match"] != "MATCH" or risk_score >= FLAG_RISK_FLOOR:
        status = "FLAGGED"
        risk_score = max(risk_score, FLAG_RISK_FLOOR)
    else:
        status = "PASSED"

    if discrepancies:
        summary = f"{status}: " + "; ".join(discrepancies[:3])
    else:
        summary = f"{status}: calldata matches the proposal text and stays inside the whitelist and spending cap"

    return ProposalEvaluation(
        proposal_id=proposal_id,
        title=title,
        status=status,
        risk_score=risk_score,
        summary=summary,
        discrepancies=discrepancies,
        spending_limit_exceeded=spending_limit_exceeded,
        unwhitelisted_target=unwhitelisted_target,
        privilege_escalation_detected=privilege_escalation,
        decoded_method=call.method_name,
        decoded_recipient=call.recipient,
        decoded_amount=call.amount,
    )
