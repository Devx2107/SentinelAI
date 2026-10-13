"""CLI entrypoint for SentinelAI node agents."""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

# Make the repo root importable whether this file is run as a module or script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from node_agent.agent import build_default_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    agent = build_default_agent()

    def _shutdown(_signum, _frame) -> None:
        agent.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    agent.start()
    logger.info("Node agent running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    finally:
        agent.stop()


if __name__ == "__main__":
    main()
