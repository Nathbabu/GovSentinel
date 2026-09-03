# GenLayer Ecosystem Explorer Submission

Copy-ready form fields, followed by a reproducible testing guide for stewards.

---

## Form fields

**Project Name**

```
GovSentinel
```

**One-Liner**

```
On-chain AI security gatekeeper that decodes EVM execution calldata and cross-examines DAO
proposal text against bytecode using multi-validator consensus under the Equivalence
Principle to prevent Trojan treasury drains and unauthorized admin takeovers.
```

**Category**

```
Security / Governance & DAOs
```

**Tags**

```
Security, DAO, EVM Calldata, Multi-Validator Consensus, Governance
```

**Description**

DAO members vote on prose. The chain executes calldata. Nothing in a normal governance
stack checks that the two describe the same transaction. GovSentinel sits in front of
execution, decodes the payload a proposal would actually run, and refuses the ones whose
bytes contradict their description.

A proposal titled "Fund the community moderation working group" that carries
`transfer(0x90f7â€¦b906, 500000)` instead of the 1,000 it claims is vetoed on three counts.
A proposal titled "Adjust quorum parameter to 12 percent" that carries
`transferOwnership(0x3c44â€¦93bc)` moves no value and targets a whitelisted contract, so
neither a spending cap nor an allowlist would catch it; the privilege rule does.

The LLM judgement runs inside `gl.eq_principle.strict_eq()` and returns a canonicalised
verdict rather than prose, so independent validators reach byte-identical output. Above
that sits a deterministic override layer decided from the calldata alone, which outranks
the model. A persuasive description is the part an attacker controls, so a confident
`MATCH` cannot rescue a payload that breaks a hard rule.

Seven benchmark attack vectors ship with the project, with real ABI-encoded calldata and
expected verdicts. The whole suite runs offline in under a second.

---

## Contract details

**Dependency header** (line one of the deployed module)

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Standard library only beyond that. No web3, no external ABI decoder, nothing to vendor.

**Constructor**

```python
GovSentinel(dao_name: str, constitution_rules: str, max_single_spend: u256, treasury_token: str)
```

The deploying address is recorded as `admin`.

### Storage design

| Field | Type | Purpose |
| --- | --- | --- |
| `dao_name` | `str` | Identifies the DAO in the audit prompt |
| `constitution_rules` | `str` | Plain-text rules the model judges the proposal against |
| `max_single_spend` | `u256` | Per-proposal spending cap, enforced deterministically |
| `treasury_token` | `str` | Token address that triggers the treasury-specific rules |
| `whitelisted_targets` | `TreeMap[str, bool]` | Approved contract addresses, keyed lowercase |
| `evaluations` | `DynArray[EvaluationRecord]` | Append-only audit history |
| `evaluation_count` | `u32` | Length mirror for cheap reads |
| `admin` | `Address` | The only address that may change the whitelist |

`EvaluationRecord` holds `proposal_id`, `title`, `status`, `risk_score` (`u32`), `summary`,
`discrepancies_json` (`str`), three boolean breach flags, `decoded_method`,
`decoded_recipient`, and `decoded_amount` (`u256`).

Two notes on the shape. `TreeMap` and `DynArray` keep the footprint inside the 256 MiB
budget without preallocating. The discrepancy list is stored as a JSON string rather than a
nested `DynArray` because it is small, written once, and always read whole, so a second
dynamic allocation per record buys nothing.

### Public methods

| Method | Kind | Notes |
| --- | --- | --- |
| `evaluate_proposal(...)` | `@gl.public.write` | Decodes, runs the `strict_eq` round, applies overrides, appends a record, returns the verdict as JSON |
| `add_whitelisted_target(target)` | `@gl.public.write` | Admin only |
| `remove_whitelisted_target(target)` | `@gl.public.write` | Admin only, raises if absent |
| `is_target_whitelisted(target)` | `@gl.public.view` | Case-insensitive |
| `get_dao_config()` | `@gl.public.view` | Amounts returned as strings so JS clients cannot round them |
| `get_evaluation(index)` | `@gl.public.view` | 0-based, raises with the recorded count on overrun |

### Decoded selectors

`0xa9059cbb` transfer Â· `0x095ea7b3` approve Â· `0xf2fde38b` transferOwnership Â·
`0x2f2ff15d` grantRole Â· `0x3659cfe6` upgradeTo Â· `0x4f1ef286` upgradeToAndCall

The decoder never raises. Malformed and unrecognised payloads return tagged rather than
throwing, so the policy vetoes them instead of the transaction reverting.

### Deterministic override guardrails

These run on the decoded bytes alone and take precedence over the model's verdict.

| Condition | Effect |
| --- | --- |
| Calldata does not decode to a known selector | VETO |
| Target absent from the whitelist | VETO |
| `transfer` or `approve` amount above `max_single_spend` | VETO |
| Decoded recipient differs from the claimed recipient | VETO |
| Decoded amount differs from the claimed amount | VETO |
| Unbounded (`2^256 - 1`) allowance on the treasury token | VETO |
| Privileged call on an unwhitelisted target, or with a model `MISMATCH` | VETO |
| Privileged call, otherwise | FLAG at minimum, never PASSED |
| Unbounded allowance on a non-treasury token | FLAG |
| Treasury spend above half the cap in one proposal | FLAG |
| Any model finding, or intent other than `MATCH` | FLAG |

Risk floors: any blocking condition pins the score to at least 90, any warning or model
finding to at least 50. The score reports severity; the rules decide the verdict.

Two behaviours reviewers should expect rather than treat as bugs. An empty whitelist blocks
every proposal, because fail-closed is the correct default for a gatekeeper and the admin
is meant to configure it before use. And a privileged call never returns PASSED even when
the proposal describes it honestly.

---

## Steward testing guide

Roughly ten minutes. Everything runs offline. There is no chain interaction, no API key,
and no build step.

**Prerequisites:** Python 3.12 or newer. Node 18 or newer for step 3 only.

Verified on Python 3.12.10 and Node v24.18.1.

### Step 1: unit tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Expect `Ran 37 tests` and `OK`. The 37 break down as:

| Class | Tests | Covers |
| --- | --- | --- |
| `TestHexNormalization` | 4 | `0x` prefix optional, case and whitespace, selector extraction, address word masking |
| `TestKnownSelectors` | 7 | All six decoders including the dynamic `bytes` tail of `upgradeToAndCall` |
| `TestHostileCalldata` | 2 | Twelve junk payloads asserted never to raise, and all vetoed |
| `TestAuditorReply` | 5 | Band snapping, fence stripping, invented codes discarded, key-order stability |
| `TestPolicyBreaches` | 13 | Every branch that can block a proposal |
| `TestScenarioFile` | 5 | Dataset schema, required ids, calldata matches the pinned ground truth |
| `TestBenchmarkOutcomes` | 1 | All seven scenarios through the real policy |

The dataset states each payload's decoded method, recipient, and amount independently of
the decoder, so a decoder regression surfaces as a mismatch rather than both sides quietly
agreeing on the wrong answer.

### Step 2: consensus simulation

```bash
python scripts/simulate_eval.py
```

Expect this summary, and exit code 0:

```
  scenario                       expected          actual     risk   result
  benign_developer_grant         PASSED            PASSED        0   ok
  trojan_treasury_drain          VETOED            VETOED      100   ok
  stealth_ownership_hijack       VETOED            VETOED      100   ok
  unapproved_target_interaction  FLAGGED/VETOED    VETOED       90   ok
  unlimited_treasury_approval    VETOED            VETOED       90   ok
  opaque_selector_payload        VETOED            VETOED      100   ok
  disclosed_proxy_upgrade        FLAGGED           FLAGGED      50   ok

7/7 scenarios matched their expected verdict.
```

Each scenario's detail block prints a `strict_eq` line. All seven should read
`3/3 agree`. That is the simulation re-emitting the same judgement in three surface forms
a validator's model might plausibly produce (plain JSON, fence-wrapped, reversed key order
with a risk number three points off the band) and confirming they canonicalise to identical
bytes. That property is what makes `strict_eq` viable over an LLM call.

To confirm the harness fails when it should, plant a wrong expectation in a throwaway copy
and point the simulator at it. This leaves `tests/scenarios.json` untouched:

```bash
python -c "import json,pathlib,tempfile; d=json.loads(pathlib.Path('tests/scenarios.json').read_text()); d['scenarios'][1]['expected_status']=['PASSED']; p=pathlib.Path(tempfile.gettempdir())/'broken_scenarios.json'; p.write_text(json.dumps(d)); print(p)"
```

Run the simulator against the path that prints:

```bash
python scripts/simulate_eval.py --scenarios <printed path>
```

Expect `MISMATCH` on `trojan_treasury_drain` in both the detail block and the summary
table, and exit code 1.

### Step 3: frontend crosscheck

```bash
node scripts/crosscheck_frontend.js
```

Expect `7/7 scenarios agree with the Python implementation.` This shells out to the Python
simulator and compares its output against the browser port field by field: status, risk
score, decoded method, decoded recipient, decoded amount, consensus flag, and the full
discrepancy list.

### Step 4: audit console

```bash
python -m http.server 8000 --directory frontend
```

Open http://localhost:8000. The left column holds seven preset buttons. Click each, then
**Run Multi-Validator Consensus Audit**, and confirm against this table:

| Preset | Verdict | Risk | What it demonstrates |
| --- | --- | --- | --- |
| Benign Grant | PASSED (green) | 0 | Text and bytes agree, amount under the cap, target approved |
| Trojan Drain | VETOED (red) | 100 | Innocuous text over calldata paying a different address 500x the stated amount |
| Stealth Hijack | VETOED (red) | 100 | `transferOwnership` behind a quorum-tweak description; no value moves and the target is whitelisted |
| Unapproved Target | VETOED (red) | 90 | Text and bytes agree perfectly; the only defect is an unwhitelisted target |
| Unlimited Approval | VETOED (red) | 90 | `approve` for `2^256 - 1` on the treasury token |
| Opaque Selector | VETOED (red) | 100 | Selector outside the audited set, vetoed as unreadable |
| Disclosed Upgrade | FLAGGED (amber) | 50 | Same call class as Stealth Hijack, honestly described |

Worth reading side by side: **Stealth Hijack** and **Disclosed Upgrade** are the same kind
of privileged call against the same whitelisted proxy. One is vetoed and one is flagged,
and the only difference is whether the proposal text matches the bytes.

Each result shows the verdict banner, a risk gauge, the decoded calldata table, the
discrepancy list, and the three-stage consensus pipeline. In the discrepancy list, red
items were decided from the bytes and are what actually moved the verdict; amber items are
advisory findings from the auditor.

### Step 5: confirm the verdicts are not canned

The presets ship with pinned model verdicts so their numbers match CI exactly. To confirm
the decoder is genuinely running rather than replaying stored answers, edit the calldata by
hand.

Load **Benign Grant** and note the result: PASSED, 0 discrepancies, amount 5,000.

Now change the last four hex characters of the calldata from `1388` to `ffff`. That is the
`uint256` amount word, and `0xffff` is 65,535, above the 10,000 cap. Rerun:

```
VETOED, 4 discrepancies, amount 65,535
```

Reload the preset, then replace the 40 hex characters of the recipient address word with
`de` repeated 20 times. Rerun:

```
VETOED, 2 discrepancies, amount 5,000
```

The amount is unchanged and the method still decodes; the veto is the recipient mismatch
alone. Editing any field also drops the pinned verdict, which the **Auditor** row reports as
`Simulated locally` instead of `Pinned benchmark verdict`.

### A note on the LLM stage

The browser cannot run `gl.eq_principle.strict_eq`, and the project does not pretend
otherwise. Presets replay the verdict pinned in `tests/scenarios.json`, which is why their
figures match the Python simulator exactly. Hand-edited proposals fall through to a local
stand-in auditor that reads the same evidence in the same closed vocabulary; it reaches the
same status as the pinned model answer on all seven benchmark scenarios. The UI labels
which one produced any given result, and the deterministic policy underneath is the real
one, ported line for line and verified by step 3.

---

## Repository

```
contracts/    Intelligent Contract, policy rules, ABI decoder, schemas
tests/        7 benchmark vectors and 37 unit tests
scripts/      Consensus simulator and the browser-port crosscheck
frontend/     Static audit console, no build step
```

Deployment note: GenVM loads a contract as a single module. The four files under
`contracts/` are concatenated in dependency order (`schemas`, `calldata_decoder`, `policy`,
`gov_sentinel`) with cross-module imports stripped and the dependency header kept as line
one, producing roughly 630 lines. The split exists so the policy stays testable off chain.

