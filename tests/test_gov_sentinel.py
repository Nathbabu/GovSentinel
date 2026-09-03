"""Unit and benchmark tests for the deterministic half of GovSentinel.

The contract module itself needs a GenVM to import, so these exercise the pieces it
delegates to: the calldata decoder and the policy that decides the verdict. Between
them they cover every branch that can block a proposal.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contracts.calldata_decoder import (  # noqa: E402
    MALFORMED_METHOD,
    MAX_UINT256,
    METHODS,
    PRIVILEGED_METHODS,
    UNKNOWN_METHOD,
    ZERO_ADDRESS,
    decode_calldata,
)
from contracts.policy import (  # noqa: E402
    FINDING_CODES,
    RISK_BANDS,
    PolicyConfig,
    apply_policy,
    build_audit_prompt,
    canonical_verdict,
    norm_address,
    parse_auditor_reply,
)
from contracts.schemas import VALID_STATUSES, DecodedCall, ProposalEvaluation  # noqa: E402

SCENARIOS_PATH = REPO_ROOT / "tests" / "scenarios.json"

TREASURY = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
PROXY = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
VENDOR = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
ATTACKER = "0x90f79bf6eb2c4f870365e785982e1f101e93b906"


def word(value: int) -> str:
    return format(value, "064x")


def addr_word(address: str) -> str:
    return "0" * 24 + address[2:].lower()


def clean_verdict(band: int = 0) -> dict:
    return {"intent_match": "MATCH", "risk_band": band, "findings": []}


def make_config(whitelist=(TREASURY, PROXY), cap: int = 10_000) -> PolicyConfig:
    allowed = {norm_address(target) for target in whitelist}
    return PolicyConfig(
        dao_name="Test DAO",
        constitution_rules="Payments go to approved vendors only.",
        max_single_spend=cap,
        treasury_token=TREASURY,
        whitelisted=allowed.__contains__,
    )


def evaluate(calldata, *, target=TREASURY, claimed_recipient="", claimed_amount=0,
             verdict=None, config=None) -> ProposalEvaluation:
    config = config or make_config()
    return apply_policy(
        config,
        decode_calldata(target, calldata),
        proposal_id="P-TEST",
        title="Test proposal",
        claimed_recipient=claimed_recipient,
        claimed_amount=claimed_amount,
        verdict=verdict or clean_verdict(),
    )


class TestHexNormalization(unittest.TestCase):
    def test_prefix_is_optional(self):
        payload = "a9059cbb" + addr_word(VENDOR) + word(42)
        with_prefix = decode_calldata(TREASURY, "0x" + payload)
        without = decode_calldata(TREASURY, payload)
        self.assertEqual(with_prefix.method_name, without.method_name)
        self.assertEqual(with_prefix.recipient, without.recipient)
        self.assertEqual(with_prefix.amount, without.amount)

    def test_uppercase_and_whitespace_are_absorbed(self):
        call = decode_calldata(
            TREASURY.upper().replace("0X", "0x"),
            "  0X" + ("a9059cbb" + addr_word(VENDOR) + word(1)).upper() + "  ",
        )
        self.assertEqual(call.method_name, "transfer")
        self.assertEqual(call.target, TREASURY)
        self.assertEqual(call.recipient, VENDOR)

    def test_selector_extraction_ignores_the_argument_block(self):
        for selector, method in METHODS.items():
            with self.subTest(selector=selector):
                filler = word(0) * len(method.arg_types)
                call = decode_calldata(TREASURY, selector + filler)
                self.assertEqual(call.signature, method.signature)
                self.assertEqual(call.method_name, method.signature.split("(")[0])

    def test_address_words_ignore_the_upper_twelve_bytes(self):
        # The EVM masks an address word down to its low 20 bytes. A decoder that did
        # not would read a dirtied word as a different, unwhitelisted address.
        dirty = "de" * 12 + VENDOR[2:]
        call = decode_calldata(TREASURY, "0xa9059cbb" + dirty + word(7))
        self.assertEqual(call.recipient, VENDOR)


class TestKnownSelectors(unittest.TestCase):
    def test_transfer(self):
        call = decode_calldata(TREASURY, "0xa9059cbb" + addr_word(VENDOR) + word(5000))
        self.assertEqual(call.signature, "transfer(address,uint256)")
        self.assertEqual(call.recipient, VENDOR)
        self.assertEqual(call.amount, 5000)
        self.assertEqual(call.extra_params, [])

    def test_approve(self):
        call = decode_calldata(TREASURY, "0x095ea7b3" + addr_word(ATTACKER) + word(MAX_UINT256))
        self.assertEqual(call.method_name, "approve")
        self.assertEqual(call.recipient, ATTACKER)
        self.assertEqual(call.amount, MAX_UINT256)

    def test_transfer_ownership(self):
        call = decode_calldata(PROXY, "0xf2fde38b" + addr_word(ATTACKER))
        self.assertEqual(call.signature, "transferOwnership(address)")
        self.assertEqual(call.recipient, ATTACKER)
        self.assertEqual(call.amount, 0)
        self.assertIn(call.method_name, PRIVILEGED_METHODS)

    def test_grant_role_reads_the_account_not_the_role(self):
        role = "ff" * 32
        call = decode_calldata(PROXY, "0x2f2ff15d" + role + addr_word(ATTACKER))
        self.assertEqual(call.recipient, ATTACKER)
        self.assertEqual(call.extra_params, ["bytes32=0x" + role])

    def test_upgrade_to_and_call_reads_the_nested_payload(self):
        inner = "0xa9059cbb" + addr_word(ATTACKER) + word(1)
        body = bytes.fromhex(inner[2:])
        calldata = (
            "0x4f1ef286"
            + addr_word(ATTACKER)
            + word(0x40)
            + word(len(body))
            + body.hex().ljust(64, "0")
        )
        call = decode_calldata(PROXY, calldata)
        self.assertEqual(call.recipient, ATTACKER)
        self.assertEqual(call.extra_params, ["bytes=" + inner])

    def test_trailing_words_are_reported(self):
        call = decode_calldata(TREASURY, "0xa9059cbb" + addr_word(VENDOR) + word(1) + word(9))
        self.assertEqual(call.extra_params, ["trailing bytes past the declared arguments"])

    def test_round_trips_through_json(self):
        call = decode_calldata(TREASURY, "0xa9059cbb" + addr_word(VENDOR) + word(5000))
        self.assertEqual(DecodedCall.from_json(call.to_json()), call)


class TestHostileCalldata(unittest.TestCase):
    """Nothing a proposer can put in the calldata field may raise out of the decoder."""

    JUNK = {
        "empty": "",
        "prefix only": "0x",
        "short selector": "0xa905",
        "odd length": "0xa9059cbb0",
        "not hex": "0xzzzzzzzz",
        "unicode": "0xa9059cbbéé",
        "unknown selector": "0xdeadbeef" + word(1),
        "truncated argument": "0xa9059cbb" + addr_word(VENDOR) + "00ff",
        "missing second argument": "0xa9059cbb" + addr_word(VENDOR),
        "dynamic offset past end": "0x4f1ef286" + addr_word(ATTACKER) + word(0xDEAD),
        "dynamic length past end": "0x4f1ef286" + addr_word(ATTACKER) + word(0x40) + word(1 << 32),
        "huge payload claim": "0x4f1ef286" + addr_word(ATTACKER) + word(0x40) + word(MAX_UINT256),
    }

    def test_never_raises_and_always_tags_the_failure(self):
        for label, calldata in self.JUNK.items():
            with self.subTest(label=label):
                call = decode_calldata(PROXY, calldata)
                self.assertIn(call.method_name, (UNKNOWN_METHOD, MALFORMED_METHOD))
                self.assertEqual(call.recipient, ZERO_ADDRESS)
                self.assertEqual(call.amount, 0)
                self.assertTrue(call.extra_params, "a rejection must say why")

    def test_undecodable_calldata_is_vetoed(self):
        for label, calldata in self.JUNK.items():
            with self.subTest(label=label):
                self.assertEqual(evaluate(calldata, target=PROXY).status, "VETOED")


class TestAuditorReply(unittest.TestCase):
    def test_bands_snap_to_the_fixed_lattice(self):
        for raw, expected in ((0, 0), (7, 0), (37, 40), (55, 60), (99, 100), (10, 0)):
            with self.subTest(raw=raw):
                verdict = canonical_verdict({"intent_match": "MATCH", "risk_band": raw})
                self.assertIn(verdict["risk_band"], RISK_BANDS)
                self.assertEqual(verdict["risk_band"], expected)

    def test_unreadable_replies_fail_closed(self):
        for raw in ("", "the proposal looks fine to me", "null", "[1, 2]", "{oops"):
            with self.subTest(raw=raw):
                verdict = parse_auditor_reply(raw)
                self.assertEqual(verdict["intent_match"], "MISMATCH")
                self.assertEqual(verdict["risk_band"], 100)

    def test_code_fences_are_stripped(self):
        raw = '```json\n{"intent_match":"match","risk_band":20,"findings":["ROLE_GRANT"]}\n```'
        self.assertEqual(
            parse_auditor_reply(raw),
            {"intent_match": "MATCH", "risk_band": 20, "findings": ["ROLE_GRANT"]},
        )

    def test_invented_finding_codes_are_discarded(self):
        verdict = canonical_verdict(
            {"intent_match": "MATCH", "risk_band": 0, "findings": ["ROLE_GRANT", "RUG_PULL", 7]}
        )
        self.assertEqual(verdict["findings"], ["ROLE_GRANT"])

    def test_output_is_stable_across_key_order(self):
        # strict_eq compares validator output byte for byte, so two validators whose
        # models emitted the same facts in a different order must still agree.
        first = parse_auditor_reply('{"risk_band":40,"findings":["ROLE_GRANT","PROXY_UPGRADE"],"intent_match":"PARTIAL"}')
        second = parse_auditor_reply('{"intent_match":"PARTIAL","findings":["PROXY_UPGRADE","ROLE_GRANT"],"risk_band":40}')
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


class TestPolicyBreaches(unittest.TestCase):
    def test_clean_proposal_passes(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(4000),
            claimed_recipient=VENDOR,
            claimed_amount=4000,
        )
        self.assertEqual(result.status, "PASSED")
        self.assertEqual(result.discrepancies, [])
        self.assertEqual(result.risk_score, 0)

    def test_spending_limit_exceeded(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(99_999),
            claimed_recipient=VENDOR,
            claimed_amount=99_999,
        )
        self.assertEqual(result.status, "VETOED")
        self.assertTrue(result.spending_limit_exceeded)
        self.assertGreaterEqual(result.risk_score, 90)
        self.assertTrue(any("cap of 10000" in d for d in result.discrepancies))

    def test_recipient_mismatch(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(ATTACKER) + word(1000),
            claimed_recipient=VENDOR,
            claimed_amount=1000,
        )
        self.assertEqual(result.status, "VETOED")
        self.assertEqual(result.decoded_recipient, ATTACKER)
        self.assertTrue(any(ATTACKER in d for d in result.discrepancies))

    def test_amount_mismatch(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(9000),
            claimed_recipient=VENDOR,
            claimed_amount=100,
        )
        self.assertEqual(result.status, "VETOED")
        self.assertFalse(result.spending_limit_exceeded)
        self.assertTrue(any("claims 100" in d for d in result.discrepancies))

    def test_ownership_hijack_behind_an_innocuous_description(self):
        result = evaluate(
            "0xf2fde38b" + addr_word(ATTACKER),
            target=PROXY,
            verdict={"intent_match": "MISMATCH", "risk_band": 100, "findings": ["OWNERSHIP_TRANSFER"]},
        )
        self.assertEqual(result.status, "VETOED")
        self.assertTrue(result.privilege_escalation_detected)

    def test_privileged_call_never_passes_even_when_honestly_described(self):
        result = evaluate("0x3659cfe6" + addr_word(ATTACKER), target=PROXY)
        self.assertEqual(result.status, "FLAGGED")
        self.assertTrue(result.privilege_escalation_detected)

    def test_unwhitelisted_target(self):
        rogue = "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65"
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(10),
            target=rogue,
            claimed_recipient=VENDOR,
            claimed_amount=10,
        )
        self.assertEqual(result.status, "VETOED")
        self.assertTrue(result.unwhitelisted_target)

    def test_empty_whitelist_blocks_everything(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(1),
            claimed_recipient=VENDOR,
            claimed_amount=1,
            config=make_config(whitelist=()),
        )
        self.assertEqual(result.status, "VETOED")

    def test_unlimited_treasury_allowance(self):
        result = evaluate(
            "0x095ea7b3" + addr_word(ATTACKER) + word(MAX_UINT256),
            claimed_recipient=ATTACKER,
            claimed_amount=MAX_UINT256,
        )
        self.assertEqual(result.status, "VETOED")
        self.assertTrue(any("unbounded allowance" in d for d in result.discrepancies))

    def test_bytes_outrank_a_reassuring_model(self):
        # The description is the part an attacker writes, so a confident MATCH must
        # not rescue calldata that breaks a hard rule.
        result = evaluate(
            "0xa9059cbb" + addr_word(ATTACKER) + word(500_000),
            claimed_recipient=VENDOR,
            claimed_amount=1000,
            verdict=clean_verdict(),
        )
        self.assertEqual(result.status, "VETOED")

    def test_model_findings_downgrade_an_otherwise_clean_pass(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(4000),
            claimed_recipient=VENDOR,
            claimed_amount=4000,
            verdict={"intent_match": "MATCH", "risk_band": 0, "findings": ["VAGUE_DESCRIPTION"]},
        )
        self.assertEqual(result.status, "FLAGGED")
        self.assertEqual(result.discrepancies, [FINDING_CODES["VAGUE_DESCRIPTION"]])

    def test_half_cap_spend_is_flagged_not_blocked(self):
        result = evaluate(
            "0xa9059cbb" + addr_word(VENDOR) + word(9000),
            claimed_recipient=VENDOR,
            claimed_amount=9000,
        )
        self.assertEqual(result.status, "FLAGGED")
        self.assertFalse(result.spending_limit_exceeded)

    def test_prompt_carries_the_decoded_ground_truth(self):
        call = decode_calldata(TREASURY, "0xa9059cbb" + addr_word(ATTACKER) + word(500_000))
        prompt = build_audit_prompt(
            make_config(), "P-1", "Pay the vendor", "Routine payout.", call, VENDOR, 1000
        )
        self.assertIn(ATTACKER, prompt)
        self.assertIn("500000", prompt)
        self.assertIn("transfer(address,uint256)", prompt)
        for code in FINDING_CODES:
            self.assertIn(code, prompt)


class TestScenarioFile(unittest.TestCase):
    REQUIRED_IDS = {
        "benign_developer_grant",
        "trojan_treasury_drain",
        "stealth_ownership_hijack",
        "unapproved_target_interaction",
    }
    SCENARIO_KEYS = {
        "id", "title", "description", "target_contract", "calldata_hex",
        "claimed_recipient", "claimed_amount", "expected_method",
        "expected_recipient", "expected_amount", "auditor_verdict",
        "expected_status", "expected_flags", "notes",
    }

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))

    def test_file_exists(self):
        self.assertTrue(SCENARIOS_PATH.is_file(), f"{SCENARIOS_PATH} is missing")

    def test_dao_block_is_complete(self):
        dao = self.doc["dao"]
        self.assertEqual(
            set(dao),
            {"name", "constitution_rules", "max_single_spend", "treasury_token", "whitelisted_targets"},
        )
        self.assertGreater(int(dao["max_single_spend"]), 0)
        self.assertIn(norm_address(dao["treasury_token"]),
                      {norm_address(t) for t in dao["whitelisted_targets"]})

    def test_required_scenarios_are_present(self):
        ids = {s["id"] for s in self.doc["scenarios"]}
        self.assertEqual(len(ids), len(self.doc["scenarios"]), "scenario ids must be unique")
        self.assertTrue(self.REQUIRED_IDS <= ids, f"missing: {self.REQUIRED_IDS - ids}")
        self.assertGreaterEqual(len(ids), 4)

    def test_every_scenario_matches_the_schema(self):
        for scenario in self.doc["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                self.assertEqual(set(scenario), self.SCENARIO_KEYS)
                self.assertTrue(scenario["calldata_hex"].startswith("0x"))
                int(scenario["claimed_amount"])
                self.assertTrue(scenario["expected_status"])
                for status in scenario["expected_status"]:
                    self.assertIn(status, VALID_STATUSES)
                self.assertEqual(
                    canonical_verdict(scenario["auditor_verdict"]),
                    scenario["auditor_verdict"],
                    "pinned verdicts must already be canonical",
                )

    def test_calldata_decodes_to_the_pinned_ground_truth(self):
        # The dataset states what each hex payload means independently of the decoder,
        # so a decoder regression surfaces as a mismatch instead of both sides
        # quietly agreeing on the wrong answer.
        known_signatures = {method.signature for method in METHODS.values()}
        for scenario in self.doc["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                call = decode_calldata(scenario["target_contract"], scenario["calldata_hex"])
                self.assertEqual(call.method_name, scenario["expected_method"])
                self.assertEqual(call.recipient, scenario["expected_recipient"])
                self.assertEqual(call.amount, int(scenario["expected_amount"]))
                if call.method_name not in (UNKNOWN_METHOD, MALFORMED_METHOD):
                    self.assertIn(call.signature, known_signatures)


class TestBenchmarkOutcomes(unittest.TestCase):
    """Every scenario in the dataset, run through the same policy the contract uses."""

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        dao = cls.doc["dao"]
        allowed = {norm_address(t) for t in dao["whitelisted_targets"]}
        cls.config = PolicyConfig(
            dao_name=dao["name"],
            constitution_rules=dao["constitution_rules"],
            max_single_spend=int(dao["max_single_spend"]),
            treasury_token=norm_address(dao["treasury_token"]),
            whitelisted=allowed.__contains__,
        )

    def test_verdicts_match_expectations(self):
        for scenario in self.doc["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                result = apply_policy(
                    self.config,
                    decode_calldata(scenario["target_contract"], scenario["calldata_hex"]),
                    proposal_id=scenario["id"],
                    title=scenario["title"],
                    claimed_recipient=scenario["claimed_recipient"],
                    claimed_amount=int(scenario["claimed_amount"]),
                    verdict=scenario["auditor_verdict"],
                )
                self.assertIn(result.status, scenario["expected_status"])
                for flag, expected in scenario["expected_flags"].items():
                    self.assertEqual(getattr(result, flag), expected, flag)
                if result.status != "PASSED":
                    self.assertTrue(result.discrepancies, "a non-pass must explain itself")


if __name__ == "__main__":
    unittest.main()
