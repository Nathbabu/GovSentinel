# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import json
from dataclasses import dataclass

from calldata_decoder import decode_calldata
from policy import (
    PolicyConfig,
    apply_policy,
    build_audit_prompt,
    norm_address,
    parse_auditor_reply,
)


@allow_storage
@dataclass
class EvaluationRecord:
    proposal_id: str
    title: str
    status: str
    risk_score: u32
    summary: str
    # Held as a JSON string rather than a nested DynArray: the list is small,
    # written once, and always read whole, so a second dynamic allocation per
    # record buys nothing.
    discrepancies_json: str
    spending_limit_exceeded: bool
    unwhitelisted_target: bool
    privilege_escalation_detected: bool
    decoded_method: str
    decoded_recipient: str
    decoded_amount: u256


class GovSentinel(gl.Contract):
    dao_name: str
    constitution_rules: str
    max_single_spend: u256
    treasury_token: str
    whitelisted_targets: TreeMap[str, bool]
    evaluations: DynArray[EvaluationRecord]
    evaluation_count: u32
    admin: Address

    def __init__(self, dao_name: str, constitution_rules: str, max_single_spend: u256, treasury_token: str):
        self.dao_name = dao_name
        self.constitution_rules = constitution_rules
        self.max_single_spend = max_single_spend
        self.treasury_token = norm_address(treasury_token)
        self.evaluation_count = u32(0)
        self.admin = gl.message.sender_address

    def _require_admin(self) -> None:
        if gl.message.sender_address != self.admin:
            raise PermissionError("only the deploying address can change the target whitelist")

    def _whitelisted(self, target: str) -> bool:
        return target in self.whitelisted_targets and self.whitelisted_targets[target]

    def _policy(self) -> PolicyConfig:
        return PolicyConfig(
            dao_name=self.dao_name,
            constitution_rules=self.constitution_rules,
            max_single_spend=int(self.max_single_spend),
            treasury_token=self.treasury_token,
            whitelisted=self._whitelisted,
        )

    @gl.public.write
    def add_whitelisted_target(self, target: str) -> None:
        self._require_admin()
        self.whitelisted_targets[norm_address(target)] = True

    @gl.public.write
    def remove_whitelisted_target(self, target: str) -> None:
        self._require_admin()
        key = norm_address(target)
        if key not in self.whitelisted_targets:
            raise ValueError(f"{key} is not on the whitelist")
        del self.whitelisted_targets[key]

    @gl.public.view
    def is_target_whitelisted(self, target: str) -> bool:
        return self._whitelisted(norm_address(target))

    @gl.public.view
    def get_dao_config(self) -> dict:
        return {
            "dao_name": self.dao_name,
            "constitution_rules": self.constitution_rules,
            # Sent as a string so a JS client reading this back cannot round a
            # token amount through a float.
            "max_single_spend": str(int(self.max_single_spend)),
            "treasury_token": self.treasury_token,
            "admin": self.admin.as_hex,
            "evaluation_count": int(self.evaluation_count),
        }

    @gl.public.view
    def get_evaluation(self, index: u32) -> dict:
        position = int(index)
        if position < 0 or position >= len(self.evaluations):
            raise IndexError(f"no evaluation at index {position}; {len(self.evaluations)} recorded so far")

        record = self.evaluations[position]
        return {
            "proposal_id": record.proposal_id,
            "title": record.title,
            "status": record.status,
            "risk_score": int(record.risk_score),
            "summary": record.summary,
            "discrepancies": json.loads(record.discrepancies_json),
            "spending_limit_exceeded": record.spending_limit_exceeded,
            "unwhitelisted_target": record.unwhitelisted_target,
            "privilege_escalation_detected": record.privilege_escalation_detected,
            "decoded_method": record.decoded_method,
            "decoded_recipient": record.decoded_recipient,
            "decoded_amount": str(int(record.decoded_amount)),
        }

    @gl.public.write
    def evaluate_proposal(
        self,
        proposal_id: str,
        title: str,
        description: str,
        target_contract: str,
        calldata_hex: str,
        claimed_recipient: str,
        claimed_amount: u256,
    ) -> str:
        config = self._policy()
        call = decode_calldata(target_contract, calldata_hex)
        prompt = build_audit_prompt(
            config, proposal_id, title, description, call, claimed_recipient, claimed_amount
        )

        def audit() -> str:
            return json.dumps(parse_auditor_reply(gl.nondet.exec_prompt(prompt)), sort_keys=True)

        verdict = json.loads(gl.eq_principle.strict_eq(audit))

        evaluation = apply_policy(
            config,
            call,
            proposal_id=proposal_id,
            title=title,
            claimed_recipient=claimed_recipient,
            claimed_amount=claimed_amount,
            verdict=verdict,
        )

        self.evaluations.append(
            EvaluationRecord(
                proposal_id=evaluation.proposal_id,
                title=evaluation.title,
                status=evaluation.status,
                risk_score=u32(evaluation.risk_score),
                summary=evaluation.summary,
                discrepancies_json=json.dumps(evaluation.discrepancies),
                spending_limit_exceeded=evaluation.spending_limit_exceeded,
                unwhitelisted_target=evaluation.unwhitelisted_target,
                privilege_escalation_detected=evaluation.privilege_escalation_detected,
                decoded_method=evaluation.decoded_method,
                decoded_recipient=evaluation.decoded_recipient,
                decoded_amount=u256(evaluation.decoded_amount),
            )
        )
        self.evaluation_count = u32(len(self.evaluations))

        return evaluation.to_json()
