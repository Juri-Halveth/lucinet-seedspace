#!/usr/bin/env python3
"""Zero-install NOVA launcher.

Runs directly from a repository checkout without pip or third-party packages.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from halveth_nova.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
