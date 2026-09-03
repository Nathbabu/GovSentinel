"""Makes the contract modules importable as a package without breaking GenVM.

GenVM loads a contract as one flat module, so these files import each other by
bare name (`from schemas import ...`). Putting this directory on the path and
aliasing the loaded modules into the package namespace lets tests and tooling say
`contracts.schemas` and get the same module object the decoder is already using,
rather than a second copy whose dataclasses fail identity checks against the first.

gov_sentinel is deliberately absent: importing it needs a GenVM runtime.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import calldata_decoder
import policy
import schemas

sys.modules[f"{__name__}.schemas"] = schemas
sys.modules[f"{__name__}.calldata_decoder"] = calldata_decoder
sys.modules[f"{__name__}.policy"] = policy

__all__ = ["calldata_decoder", "policy", "schemas"]
