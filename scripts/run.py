#!/usr/bin/env python3
"""Entry point for the Supervisor Agent.

Run with:
    python run.py --tasks example_tasks.json [--mock]
"""

import sys
from pathlib import Path

# Make the local `agent` package importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
