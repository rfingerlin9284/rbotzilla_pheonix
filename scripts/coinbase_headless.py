#!/usr/bin/env python3
"""Headless Coinbase runtime process.

Keeps Coinbase connector active as a standalone service process so it can run
independently from OANDA.
"""

from __future__ import annotations

import argparse
import signal
import time

from brokers.coinbase_connector import CoinbaseConnector


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone Coinbase headless process")
    parser.add_argument("--env", choices=["sandbox", "live"], default="sandbox")
    args = parser.parse_args()

    connector = CoinbaseConnector(environment=args.env)
    print(f"Coinbase headless process started ({connector.environment}).")

    running = True

    def _stop(_sig, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        stats = connector.get_performance_stats()
        print(
            f"heartbeat env={connector.environment} total_requests={stats.get('total_requests', 0)} "
            f"avg_latency_ms={stats.get('avg_latency_ms', 0):.2f}"
        )
        time.sleep(30)

    print("Coinbase headless process stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
