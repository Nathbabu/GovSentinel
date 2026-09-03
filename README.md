# GovSentinel

A GenLayer Intelligent Contract that validates DAO proposals by cross-examining human-readable voting intent against raw on-chain EVM execution calldata.

DAO members vote on prose, while the blockchain executes raw bytecode. GovSentinel acts as a zero-trust governance gatekeeper, sitting in front of execution to block discrepancies, stealth ownership takeovers, and unauthorized treasury drains before transactions execute.

---

## Key Attack Vectors Blocked

- **Trojan Treasury Drains:** Proposals claiming modest community grants while secretly encoding multi-million dollar transfers to attacker wallets.
- **Stealth Ownership Hijacks:** Proposals claiming routine parameter adjustments while calling `transferOwnership()` to seize contract admin rights.
- **Unlimited Approvals:** Proposals requesting standard operational allowances while encoding `MAX_UINT256` token approvals to enable future treasury drains.
- **Unapproved Targets:** Calls targeting unverified smart contracts not on the DAO's approved whitelist.
- **Opaque Bytecode:** Obfuscated payloads with unrecognised function selectors that cannot be verified.

---

## How It Works

1. **EVM Calldata Decoding:** Pure Python ABI parser extracts selectors, recipient addresses, and amounts from raw execution bytecode without external dependencies.
2. **AI Multi-Validator Cross-Examination:** GenLayer validators execute the audit inside `gl.eq_principle.strict_eq()`, comparing intent text against execution parameters under strict consensus.
3. **Deterministic Policy Guard:** Enforces DAO spending caps, contract whitelists, and privileged role protections to veto malicious payloads.

---

## Project Structure

```
GovSentinel/
├── contracts/
│   ├── gov_sentinel.py       # Core GenLayer Intelligent Contract
│   ├── calldata_decoder.py   # Pure Python EVM ABI decoder
│   ├── policy.py             # Deterministic rules & consensus canonicalization
│   └── schemas.py            # Data models and schemas
├── frontend/
│   ├── index.html            # Light-mode web console
│   ├── styles/main.css       # Design system styles
│   └── src/
│       ├── app.js            # DOM events & consensus simulator
│       ├── contract.js       # Client ABI decoder & policy engine
│       └── scenarios.js      # Benchmark attack scenarios
├── scripts/
│   ├── simulate_eval.py      # Multi-validator consensus simulator
│   └── crosscheck_frontend.js# Python/JS parity validation
├── tests/
│   ├── scenarios.json        # Pinned benchmark test vectors
│   └── test_gov_sentinel.py  # 37 automated unit tests
└── EXPLORER_SUBMISSION.md    # GenLayer ecosystem submission package
```

---

## Reproducible Testing Guide

### 1. Run Automated Unit Tests (37 Tests)
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### 2. Run Multi-Validator Consensus Simulation
```bash
python scripts/simulate_eval.py
```

### 3. Run Frontend/Python Crosscheck Parity
```bash
node scripts/crosscheck_frontend.js
```

### 4. Run the Web Console
```bash
python -m http.server 8000 --directory frontend
```
Then open [http://localhost:8000](http://localhost:8000) in your browser.

---

## License
MIT License. See [LICENSE](LICENSE) for details.
