from __future__ import annotations

import subprocess
from pathlib import Path

from ..jsonutil import strict_loads


def lagefaden(*, node: str = "node") -> dict:
    root = Path(__file__).resolve().parent / "_integrations" / "lagefaden"
    process = subprocess.run([node, str(root / "run.mjs")], capture_output=True, timeout=25, shell=False)
    if process.returncode:
        raise RuntimeError("BOUND_LAGEFADEN_ADAPTER_FAILED")
    value = strict_loads(process.stdout.decode("utf-8"))
    if value.get("contract") != "nova.lagefaden-integration.v1":
        raise ValueError("LAGEFADEN_OUTPUT_CONTRACT")
    return value
