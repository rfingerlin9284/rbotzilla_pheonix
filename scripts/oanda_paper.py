#!/usr/bin/env python3
"""Launch the real OANDA engine in PAPER mode.

This uses the exact same trading engine codepath as LIVE mode, with only API
credentials/environment changing by mode.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, "oanda_trading_engine.py", "--env", "practice"]
    env = os.environ.copy()
    env["ENABLE_DASHBOARD"] = "0"
    print("Starting OANDA engine in PAPER mode (headless)...")
    return subprocess.call(cmd, cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
