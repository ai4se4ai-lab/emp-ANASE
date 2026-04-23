#!/usr/bin/env python3
"""CLI entrypoint for the analogical reasoning crawler."""

import sys

from core.orchestrator import main


if __name__ == "__main__":
    sys.exit(main())
