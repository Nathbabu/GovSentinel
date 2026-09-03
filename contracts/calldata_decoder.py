"""Minimal EVM ABI decoder for the handful of calls a DAO treasury actually signs.

web3.py is not available inside GenVM and pulling a general-purpose ABI decoder in
would be overkill anyway: six selectors, four argument types, no tuples, no arrays.
Everything here is stdlib and deterministic, which matters because validators must
agree on the decode before the LLM ever sees it.
"""

from dataclasses import dataclass

from schemas import DecodedCall

SELECTOR_HEX = 8
WORD_HEX = 64
ZERO_ADDRESS = "0x" + "0" * 40
MAX_UINT256 = (1 << 256) - 1

UNKNOWN_METHOD = "unknown"
MALFORMED_METHOD = "malformed"


@dataclass(frozen=True)
class _Method:
    signature: str
    arg_types: tuple[str, ...]
    recipient_arg: int | None = None
    amount_arg: int | None = None

    @property
    def name(self) -> str:
        return self.signature.split("(", 1)[0]


METHODS = {
    "0xa9059cbb": _Method("transfer(address,uint256)", ("address", "uint256"), 0, 1),
    "0x095ea7b3": _Method("approve(address,uint256)", ("address", "uint256"), 0, 1),
    "0xf2fde38b": _Method("transferOwnership(address)", ("address",), 0),
    "0x2f2ff15d": _Method("grantRole(bytes32,address)", ("bytes32", "address"), 1),
    "0x3659cfe6": _Method("upgradeTo(address)", ("address",), 0),
    "0x4f1ef286": _Method("upgradeToAndCall(address,bytes)", ("address", "bytes"), 0),
}

# These hand over control of the target instead of moving value, so no amount check
# will ever catch them. They need their own rule upstream.
PRIVILEGED_METHODS = frozenset({"transferOwnership", "grantRole", "upgradeTo", "upgradeToAndCall"})

VALUE_METHODS = frozenset({"transfer", "approve"})


def _strip_prefix(calldata_hex: str) -> str:
    body = calldata_hex.strip()
    if body[:2].lower() == "0x":
        body = body[2:]
    return body.lower()


def _is_hex(body: str) -> bool:
    try:
        bytes.fromhex(body)
    except ValueError:
        return False
    return True


def _word(body: str, index: int) -> str:
    start = index * WORD_HEX
    word = body[start:start + WORD_HEX]
    if len(word) < WORD_HEX:
        raise ValueError(f"calldata ends mid-word at argument slot {index}")
    return word


def _dynamic_bytes(body: str, offset: int) -> str:
    head = offset * 2
    if head + WORD_HEX > len(body):
        raise ValueError(f"bytes offset {offset} points past the end of the payload")
    size = int(body[head:head + WORD_HEX], 16) * 2
    start = head + WORD_HEX
    if start + size > len(body):
        raise ValueError(f"bytes payload at offset {offset} is truncated")
    return "0x" + body[start:start + size]


def _decode_args(body: str, arg_types: tuple[str, ...]) -> list:
    values = []
    for slot, kind in enumerate(arg_types):
        word = _word(body, slot)
        if kind == "address":
            # The EVM ignores the upper 12 bytes of an address word, so we do too;
            # normalising here keeps whitelist comparisons honest.
            values.append("0x" + word[-40:])
        elif kind == "uint256":
            values.append(int(word, 16))
        elif kind == "bytes32":
            values.append("0x" + word)
        elif kind == "bytes":
            values.append(_dynamic_bytes(body, int(word, 16)))
        else:
            raise ValueError(f"no decoder for argument type {kind!r}")
    return values


def _failure(method_name: str, signature: str, target: str, raw: str, note: str) -> DecodedCall:
    return DecodedCall(
        signature=signature,
        method_name=method_name,
        target=target,
        recipient=ZERO_ADDRESS,
        amount=0,
        extra_params=[note],
        raw_calldata=raw,
    )


def decode_calldata(target: str, calldata_hex: str) -> DecodedCall:
    """Decode governance calldata into its arguments.

    Never raises. Calldata that cannot be parsed comes back tagged `malformed` or
    `unknown` so the caller can veto it, which is the safe reading: a payload no
    auditor can read is not a payload anyone should execute.
    """
    raw = calldata_hex.strip()
    target = target.strip().lower()
    body = _strip_prefix(raw)

    if len(body) < SELECTOR_HEX or not _is_hex(body):
        return _failure(MALFORMED_METHOD, "", target, raw, "calldata is not a well-formed hex payload")

    selector = "0x" + body[:SELECTOR_HEX]
    args = body[SELECTOR_HEX:]

    method = METHODS.get(selector)
    if method is None:
        call = _failure(UNKNOWN_METHOD, selector, target, raw, f"unrecognised selector {selector}")
        call.extra_params.append(f"{len(args) // WORD_HEX} argument word(s) supplied")
        return call

    try:
        values = _decode_args(args, method.arg_types)
    except ValueError as err:
        return _failure(MALFORMED_METHOD, method.signature, target, raw, str(err))

    recipient = values[method.recipient_arg] if method.recipient_arg is not None else ZERO_ADDRESS
    amount = values[method.amount_arg] if method.amount_arg is not None else 0

    consumed = {method.recipient_arg, method.amount_arg}
    extra = [f"{method.arg_types[i]}={v}" for i, v in enumerate(values) if i not in consumed]

    # Trailing words are ignored by the EVM on a static-argument call, but their
    # presence usually means the payload was built for a different ABI, or for a
    # fallback that reads past the declared arguments.
    if "bytes" not in method.arg_types and len(args) > len(method.arg_types) * WORD_HEX:
        extra.append("trailing bytes past the declared arguments")

    return DecodedCall(
        signature=method.signature,
        method_name=method.name,
        target=target,
        recipient=recipient,
        amount=amount,
        extra_params=extra,
        raw_calldata=raw,
    )
