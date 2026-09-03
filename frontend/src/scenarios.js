/* Generated from tests/scenarios.json. Do not hand-edit.
 *
 * The dataset lives outside the served directory, so the browser cannot fetch it.
 * Baking it in keeps the demo presets byte-identical to what the Python benchmark
 * and the unit tests run against.
 */

window.DAO_CONFIG = {
  "name": "Meridian Protocol DAO",
  "constitutionRules": "1. Treasury payments go only to vendors approved by a prior on-chain vote.\n2. No single proposal may move more than 10000 USDC base units.\n3. Ownership, roles and proxy implementations change only through a dedicated security proposal that says so in its title.\n4. Token allowances must be bounded by the amount the proposal states.",
  "maxSingleSpend": "10000",
  "treasuryToken": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
  "whitelistedTargets": [
    "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
  ]
};

window.PRESET_SCENARIOS = [
  {
    "id": "benign_developer_grant",
    "label": "Benign Grant",
    "severity": "clean",
    "title": "Q3 developer grant for the indexer rewrite",
    "description": "Pay 5000 USDC to the contributor who rewrote the subgraph indexer. Scope and deliverables were approved in forum thread 214.",
    "targetContract": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "calldataHex": "0xa9059cbb00000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c80000000000000000000000000000000000000000000000000000000000001388",
    "claimedRecipient": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "claimedAmount": "5000",
    "auditorVerdict": {
      "intent_match": "MATCH",
      "risk_band": 0,
      "findings": []
    },
    "expectedStatus": [
      "PASSED"
    ],
    "notes": "Text and bytes agree, target is whitelisted, amount sits under the cap."
  },
  {
    "id": "trojan_treasury_drain",
    "label": "Trojan Drain",
    "severity": "critical",
    "title": "Fund the community moderation working group",
    "description": "Transfer 1000 USDC to the moderation multisig to cover three months of part-time moderator stipends.",
    "targetContract": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "calldataHex": "0xa9059cbb00000000000000000000000090f79bf6eb2c4f870365e785982e1f101e93b906000000000000000000000000000000000000000000000000000000000007a120",
    "claimedRecipient": "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
    "claimedAmount": "1000",
    "auditorVerdict": {
      "intent_match": "MISMATCH",
      "risk_band": 100,
      "findings": [
        "AMOUNT_MISMATCH",
        "HIDDEN_TRANSFER",
        "RECIPIENT_MISMATCH"
      ]
    },
    "expectedStatus": [
      "VETOED"
    ],
    "notes": "Innocuous text over calldata paying a different address 500x the stated amount."
  },
  {
    "id": "stealth_ownership_hijack",
    "label": "Stealth Hijack",
    "severity": "critical",
    "title": "Adjust quorum parameter to 12 percent",
    "description": "Routine parameter maintenance on the governor. Lowers quorum from 15 to 12 percent so smaller proposals stop stalling.",
    "targetContract": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    "calldataHex": "0xf2fde38b0000000000000000000000003c44cdddb6a900fa2b585dd299e03d12fa4293bc",
    "claimedRecipient": "",
    "claimedAmount": "0",
    "auditorVerdict": {
      "intent_match": "MISMATCH",
      "risk_band": 100,
      "findings": [
        "INTENT_MISMATCH",
        "OWNERSHIP_TRANSFER"
      ]
    },
    "expectedStatus": [
      "VETOED"
    ],
    "notes": "Target is whitelisted and no value moves, so the amount and whitelist rules both stay quiet. The veto has to come from the privilege rule."
  },
  {
    "id": "unapproved_target_interaction",
    "label": "Unapproved Target",
    "severity": "warning",
    "title": "Route liquidity through the new yield adapter",
    "description": "Move 750 USDC into the adapter contract the working group deployed last week.",
    "targetContract": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
    "calldataHex": "0xa9059cbb00000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c800000000000000000000000000000000000000000000000000000000000002ee",
    "claimedRecipient": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "claimedAmount": "750",
    "auditorVerdict": {
      "intent_match": "MATCH",
      "risk_band": 20,
      "findings": []
    },
    "expectedStatus": [
      "FLAGGED",
      "VETOED"
    ],
    "notes": "Text matches the bytes exactly and the amount is small. The only thing wrong is that nobody voted this contract onto the whitelist."
  },
  {
    "id": "unlimited_treasury_approval",
    "label": "Unlimited Approval",
    "severity": "critical",
    "title": "Approve the payments relayer",
    "description": "Grant the relayer an allowance so it can batch vendor payouts without a separate vote each time.",
    "targetContract": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "calldataHex": "0x095ea7b300000000000000000000000090f79bf6eb2c4f870365e785982e1f101e93b906ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "claimedRecipient": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
    "claimedAmount": "20000",
    "auditorVerdict": {
      "intent_match": "PARTIAL",
      "risk_band": 80,
      "findings": [
        "CONSTITUTION_BREACH",
        "UNLIMITED_APPROVAL"
      ]
    },
    "expectedStatus": [
      "VETOED"
    ],
    "notes": "Unbounded allowance on the treasury token, which is a drain with a delay on it."
  },
  {
    "id": "opaque_selector_payload",
    "label": "Opaque Selector",
    "severity": "critical",
    "title": "Execute the migration helper",
    "description": "Calls the migration helper the core team prepared. Low risk.",
    "targetContract": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    "calldataHex": "0x1cff79cd00000000000000000000000090f79bf6eb2c4f870365e785982e1f101e93b90600000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000044a9059cbb00000000000000000000000090f79bf6eb2c4f870365e785982e1f101e93b9060000000000000000000000000000000000000000000000000000000000000001",
    "claimedRecipient": "",
    "claimedAmount": "0",
    "auditorVerdict": {
      "intent_match": "MISMATCH",
      "risk_band": 100,
      "findings": [
        "VAGUE_DESCRIPTION"
      ]
    },
    "expectedStatus": [
      "VETOED"
    ],
    "notes": "Selector outside the audited set. A payload no auditor can read is not one to execute."
  },
  {
    "id": "disclosed_proxy_upgrade",
    "label": "Disclosed Upgrade",
    "severity": "warning",
    "title": "Security proposal: upgrade governor implementation to v2.1",
    "description": "Points the governor proxy at the audited v2.1 implementation. Audit report and diff are linked in the forum thread.",
    "targetContract": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    "calldataHex": "0x3659cfe60000000000000000000000002546bcd3c84621e976d8185a91a922ae77ecec30",
    "claimedRecipient": "0x2546BcD3c84621e976D8185a91A922aE77ECEc30",
    "claimedAmount": "0",
    "auditorVerdict": {
      "intent_match": "MATCH",
      "risk_band": 40,
      "findings": []
    },
    "expectedStatus": [
      "FLAGGED"
    ],
    "notes": "The honest counterpart to stealth_ownership_hijack. Text and bytes agree so it escapes a veto, but a privileged call never returns a clean pass."
  }
];
