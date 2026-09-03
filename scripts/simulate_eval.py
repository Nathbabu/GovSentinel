"""Replay the GovSentinel benchmark without a chain under it.

Two things get simulated. First the strict_eq round: each pinned auditor verdict is
re-serialised the way different validators' models would plausibly emit it, pushed
back through the same canonicaliser the contract uses, and compared byte for byte.
Then the deterministic policy runs on the decoded calldata and the agreed verdict.

Exits non-zero if any scenario lands outside its expected status, so it works as a
CI gate as well as something to read.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contracts.calldata_decoder import MALFORMED_METHOD, UNKNOWN_METHOD, decode_calldata
from contracts.policy import PolicyConfig, apply_policy, norm_address, parse_auditor_reply
from contracts.schemas import ProposalEvaluation

DEFAULT_SCENARIOS = REPO_ROOT / "tests" / "scenarios.json"
RULE = "-" * 78


def short(address: str) -> str:
    address = norm_address(address)
    if len(address) < 14:
        return address or "(none)"
    return f"{address[:8]}...{address[-6:]}"


def validator_replies(verdict: dict) -> list[str]:
    """Three surface forms of the same judgement, as different validators would emit it.

    A model that answers in a different key order, wraps the JSON in a fence, or
    picks a risk number a few points off the band must still land on identical
    canonical bytes, otherwise strict_eq never reaches consensus.
    """
    fence = "`" * 3
    plain = json.dumps(verdict)
    shuffled = json.dumps(
        {
            "findings": list(reversed(verdict["findings"])),
            "risk_band": max(0, verdict["risk_band"] - 3),
            "intent_match": verdict["intent_match"].lower(),
        }
    )
    return [plain, f"{fence}json\n{plain}\n{fence}", shuffled]


def run_consensus(verdict: dict) -> tuple[dict, bool, int]:
    canonical = [parse_auditor_reply(reply) for reply in validator_replies(verdict)]
    encoded = {json.dumps(v, sort_keys=True) for v in canonical}
    agreed = len(encoded) == 1
    return canonical[0], agreed, len(canonical)


def load_config(dao: dict) -> PolicyConfig:
    allowed = {norm_address(t) for t in dao["whitelisted_targets"]}
    return PolicyConfig(
        dao_name=dao["name"],
        constitution_rules=dao["constitution_rules"],
        max_single_spend=int(dao["max_single_spend"]),
        treasury_token=norm_address(dao["treasury_token"]),
        whitelisted=allowed.__contains__,
    )


def report(index: int, total: int, scenario: dict, call, evaluation: ProposalEvaluation,
           verdict: dict, agreed: bool, validators: int, config: PolicyConfig) -> None:
    expected = scenario["expected_status"]
    matched = evaluation.status in expected
    calldata = scenario["calldata_hex"]

    print()
    print(f"[{index}/{total}] {scenario['id']}")
    print(RULE)
    print(f"  proposal    {scenario['title']}")
    print(f"  target      {short(call.target)}  "
          f"({'whitelisted' if config.whitelisted(call.target) else 'NOT whitelisted'})")
    print(f"  calldata    {calldata[:12]}... {(len(calldata) - 2) // 2} bytes")
    print(f"  decodes to  {call.signature or call.method_name}")
    if call.method_name not in (UNKNOWN_METHOD, MALFORMED_METHOD):
        print(f"  text says   {scenario['claimed_amount']} to {short(scenario['claimed_recipient'])}")
        print(f"  bytes do    {call.amount} to {short(call.recipient)}")
    if call.extra_params:
        print(f"  also        {'; '.join(call.extra_params)}")

    findings = ", ".join(verdict["findings"]) or "none"
    quorum = f"{validators}/{validators} agree" if agreed else "NO CONSENSUS"
    print(f"  auditor     {verdict['intent_match']} at band {verdict['risk_band']}, "
          f"findings: {findings}")
    print(f"  strict_eq   {quorum}")
    print(f"  verdict     {evaluation.status}  (expected {' or '.join(expected)})  "
          f"risk {evaluation.risk_score}  [{'ok' if matched else 'MISMATCH'}]")

    if evaluation.discrepancies:
        print("  discrepancies")
        for line in evaluation.discrepancies:
            print(f"    - {line}")
    else:
        print("  discrepancies  none")


def summarise(rows: list[tuple]) -> None:
    print()
    print("Summary")
    print(RULE)
    print(f"  {'scenario':<31}{'expected':<18}{'actual':<10}{'risk':>5}   result")
    for scenario_id, expected, actual, risk, ok in rows:
        print(f"  {scenario_id:<31}{'/'.join(expected):<18}{actual:<10}{risk:>5}   "
              f"{'ok' if ok else 'MISMATCH'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the GovSentinel benchmark scenarios.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS,
                        help=f"benchmark dataset to run (default: {DEFAULT_SCENARIOS})")
    parser.add_argument("--only", metavar="ID", help="run a single scenario by id")
    parser.add_argument("--json", action="store_true", help="emit results as JSON instead of a report")
    args = parser.parse_args()

    doc = json.loads(args.scenarios.read_text(encoding="utf-8"))
    config = load_config(doc["dao"])
    scenarios = doc["scenarios"]
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]
        if not scenarios:
            parser.error(f"no scenario with id {args.only!r} in {args.scenarios}")

    if not args.json:
        dao = doc["dao"]
        print(f"GovSentinel simulation: {dao['name']}")
        print(f"cap {dao['max_single_spend']}  treasury {short(dao['treasury_token'])}  "
              f"whitelist {len(dao['whitelisted_targets'])} targets  "
              f"scenarios {len(scenarios)}")

    rows, payload, failures = [], [], 0
    for position, scenario in enumerate(scenarios, start=1):
        call = decode_calldata(scenario["target_contract"], scenario["calldata_hex"])
        verdict, agreed, validators = run_consensus(scenario["auditor_verdict"])
        evaluation = apply_policy(
            config,
            call,
            proposal_id=scenario["id"],
            title=scenario["title"],
            claimed_recipient=scenario["claimed_recipient"],
            claimed_amount=int(scenario["claimed_amount"]),
            verdict=verdict,
        )
        ok = evaluation.status in scenario["expected_status"] and agreed
        failures += not ok
        rows.append((scenario["id"], scenario["expected_status"], evaluation.status,
                     evaluation.risk_score, ok))

        if args.json:
            payload.append({
                "id": scenario["id"],
                "expected_status": scenario["expected_status"],
                "actual_status": evaluation.status,
                "risk_score": evaluation.risk_score,
                "consensus": agreed,
                "decoded_method": call.method_name,
                "discrepancies": evaluation.discrepancies,
                "matched": ok,
            })
        else:
            report(position, len(scenarios), scenario, call, evaluation,
                   verdict, agreed, validators, config)

    if args.json:
        print(json.dumps({"results": payload, "failures": failures}, indent=2))
        return 1 if failures else 0

    summarise(rows)
    print()
    print(f"{len(rows) - failures}/{len(rows)} scenarios matched their expected verdict.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
